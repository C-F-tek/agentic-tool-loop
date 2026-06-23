#!/usr/bin/env python3
"""Read-only SQLite MCP server for Codex-side diagnostics."""

from __future__ import annotations

from collections.abc import Iterable
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from typing import Any

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    self_test,
    serve,
    string_prop,
    integer_prop,
    boolean_prop,
    safe_int,
)

SERVER_NAME = "aicarmine-sqlite-readonly-mcp"
SERVER_VERSION = "0.1.0"

DB_SUFFIXES = {".sqlite", ".sqlite3", ".db"}
MAX_SQL_CHARS = 5000
BLOCKED_SQL_RE = re.compile(
    r"\b("
    r"attach|alter|analyze|begin|commit|create|delete|detach|drop|insert|load_extension|"
    r"pragma|reindex|release|replace|rollback|savepoint|transaction|update|vacuum"
    r")\b",
    re.IGNORECASE,
)




def _path_is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        pass
    except OSError:
        return False
    child_text = str(child.resolve()).lower().rstrip("\\/")
    parent_text = str(parent.resolve()).lower().rstrip("\\/")
    return child_text == parent_text or child_text.startswith(parent_text + "\\") or child_text.startswith(parent_text + "/")


def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(resolved)
    return out


def _env_allow_roots() -> list[Path]:
    raw = os.environ.get("AICARMINE_SQLITE_READONLY_ALLOW_ROOTS", "")
    roots: list[Path] = []
    for item in raw.split(";"):
        item = item.strip()
        if not item:
            continue
        candidate = Path(item).expanduser()
        if candidate.exists():
            roots.append(candidate)
    return roots


def _allowed_roots(root: Path) -> list[Path]:
    return _dedupe_paths([root, *_env_allow_roots()])


def _known_aliases(root: Path) -> dict[str, Path]:
    return {
        "rag": root / "state" / "codex_rag" / "code_rag.sqlite3",
        "codex_rag": root / "state" / "codex_rag" / "code_rag.sqlite3",
        "agent_jobs": root / "qwen-agent-workspace" / "vulkan-broker" / "agent-jobs" / "agent_jobs.sqlite3",
        "openwebui_webui": root / "services" / "openwebui-data" / "webui.db",
        "openwebui_chroma": root / "services" / "openwebui-data" / "vector_db" / "chroma.sqlite3",
    }


def _db_from_alias(value: str, root: Path) -> Path | None:
    aliases = _known_aliases(root)
    if value in aliases:
        return aliases[value]
    if value.startswith("planner:"):
        job_id = value.split(":", 1)[1].strip()
        if re.fullmatch(r"[A-Za-z0-9_.-]+", job_id):
            return root / "qwen-agent-workspace" / "vulkan-broker" / "agent-jobs" / job_id / "planner_composer.sqlite"
    return None


def _resolve_db_path(value: Any, root: Path) -> tuple[Path | None, dict[str, Any] | None]:
    text = str(value or "").strip()
    if not text:
        return None, {"ok": False, "error": "missing_db", "expected": "db alias, relative path, or absolute path"}

    aliased = _db_from_alias(text, root)
    candidate = aliased if aliased is not None else Path(text).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate

    try:
        resolved = candidate.resolve()
    except OSError as exc:
        return None, {"ok": False, "error": "db_path_resolve_failed", "db": text, "message": str(exc)}

    allowed_roots = _allowed_roots(root)
    if not any(_path_is_under(resolved, allowed_root) for allowed_root in allowed_roots):
        return None, {
            "ok": False,
            "error": "db_path_not_allowlisted",
            "db": text,
            "resolved": str(resolved),
            "allowed_roots": [str(path) for path in allowed_roots],
        }
    if not resolved.is_file():
        return None, {"ok": False, "error": "db_file_not_found", "db": text, "resolved": str(resolved)}
    if resolved.suffix.lower() not in DB_SUFFIXES:
        return None, {
            "ok": False,
            "error": "unsupported_db_suffix",
            "db": text,
            "resolved": str(resolved),
            "allowed_suffixes": sorted(DB_SUFFIXES),
        }
    return resolved, None


def _sqlite_uri(path: Path) -> str:
    return f"file:{path.resolve().as_posix()}?mode=ro"


def _connect_readonly(path: Path, *, timeout_seconds: int) -> sqlite3.Connection:
    conn = sqlite3.connect(_sqlite_uri(path), uri=True, timeout=min(timeout_seconds, 10))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    conn.execute("PRAGMA temp_store = MEMORY")
    return conn


def _validate_select_sql(sql: Any) -> tuple[str | None, dict[str, Any] | None]:
    text = str(sql or "").strip()
    preview = text[:100]
    if not text:
        return None, {"ok": False, "error": "missing_sql", "sql_preview": preview}
    if len(text) > MAX_SQL_CHARS:
        return None, {
            "ok": False,
            "error": "sql_too_long",
            "length": len(text),
            "max_length": MAX_SQL_CHARS,
            "sql_preview": preview,
        }
    lowered = text.lower().lstrip()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        return None, {"ok": False, "error": "only_select_or_with_allowed", "sql_preview": preview}
    if ";" in text:
        return None, {"ok": False, "error": "multiple_statements_forbidden", "sql_preview": preview}
    if "--" in text or "/*" in text or "*/" in text:
        return None, {"ok": False, "error": "sql_comments_forbidden", "sql_preview": preview}
    blocked = BLOCKED_SQL_RE.search(text)
    if blocked:
        return None, {
            "ok": False,
            "error": "blocked_sql_keyword",
            "keyword": blocked.group(1).lower(),
            "sql_preview": preview,
        }
    return text, None


def _compact_value(value: Any, *, max_cell_chars: int) -> Any:
    if isinstance(value, bytes):
        digest = hashlib.sha256(value).hexdigest()
        return {"type": "bytes", "size": len(value), "sha256": digest}
    if isinstance(value, str) and len(value) > max_cell_chars:
        return value[: max_cell_chars - 80].rstrip() + f"\n...[truncated cell chars={len(value)}]"
    return value


def _row_to_dict(row: sqlite3.Row, *, max_cell_chars: int) -> dict[str, Any]:
    return {key: _compact_value(row[key], max_cell_chars=max_cell_chars) for key in row.keys()}


def _query_rows(
    conn: sqlite3.Connection,
    sql: str,
    *,
    row_limit: int,
    timeout_seconds: int,
    max_cell_chars: int,
) -> tuple[list[str], list[dict[str, Any]], bool]:
    deadline = time.monotonic() + timeout_seconds

    def progress() -> int:
        return 1 if time.monotonic() > deadline else 0

    conn.set_progress_handler(progress, 1000)
    try:
        cursor = conn.execute(sql)
        columns = [description[0] for description in (cursor.description or [])]
        fetched = cursor.fetchmany(row_limit + 1)
    finally:
        conn.set_progress_handler(None, 0)
    truncated = len(fetched) > row_limit
    return columns, [_row_to_dict(row, max_cell_chars=max_cell_chars) for row in fetched[:row_limit]], truncated


def _table_names(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT name, type, sql
        FROM sqlite_schema
        WHERE type IN ('table', 'view')
          AND name NOT LIKE 'sqlite_%'
        ORDER BY type, name
        """
    ).fetchall()
    return [{"name": row["name"], "type": row["type"], "sql": row["sql"]} for row in rows]


def _schema(args: dict[str, Any], root: Path) -> dict[str, Any]:
    db_path, problem = _resolve_db_path(args.get("db"), root)
    if problem is not None:
        return problem
    assert db_path is not None

    include_columns = bool(args.get("include_columns", True))
    include_sql = bool(args.get("include_sql", False))
    timeout_seconds = safe_int(args.get("timeout_seconds"), 5, 1, 30)

    with _connect_readonly(db_path, timeout_seconds=timeout_seconds) as conn:
        tables = _table_names(conn)
        for table in tables:
            if not include_sql:
                table.pop("sql", None)
            if not include_columns:
                continue
            quoted = '"' + str(table["name"]).replace('"', '""') + '"'
            cursor = conn.execute(f"SELECT * FROM {quoted} LIMIT 0")
            table["columns"] = [description[0] for description in (cursor.description or [])]

    return {
        "ok": True,
        "tool": "aicarmine_sqlite_readonly_schema",
        "db": str(db_path),
        "tables": tables,
        "table_count": len(tables),
        "read_only": True,
    }


def _query(args: dict[str, Any], root: Path) -> dict[str, Any]:
    db_path, problem = _resolve_db_path(args.get("db"), root)
    if problem is not None:
        return problem
    assert db_path is not None

    sql, sql_problem = _validate_select_sql(args.get("sql") or args.get("query"))
    if sql_problem is not None:
        return sql_problem
    assert sql is not None

    row_limit = safe_int(args.get("row_limit") or args.get("limit"), 100, 1, 1000)
    timeout_seconds = safe_int(args.get("timeout_seconds"), 5, 1, 30)
    max_cell_chars = safe_int(args.get("max_cell_chars"), 4000, 200, 20000)

    try:
        with _connect_readonly(db_path, timeout_seconds=timeout_seconds) as conn:
            columns, rows, truncated = _query_rows(
                conn,
                sql,
                row_limit=row_limit,
                timeout_seconds=timeout_seconds,
                max_cell_chars=max_cell_chars,
            )
    except sqlite3.Error as exc:
        return {
            "ok": False,
            "tool": "aicarmine_sqlite_readonly_query",
            "error": "sqlite_query_failed",
            "error_type": type(exc).__name__,
            "message": str(exc),
            "db": str(db_path),
        }

    return {
        "ok": True,
        "tool": "aicarmine_sqlite_readonly_query",
        "db": str(db_path),
        "sql": sql,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "row_limit": row_limit,
        "truncated": truncated,
        "read_only": True,
        "only_select": True,
    }


def _list_databases(args: dict[str, Any], root: Path) -> dict[str, Any]:
    max_results = safe_int(args.get("max_results") or args.get("limit"), 200, 1, 1000)
    max_depth = safe_int(args.get("max_depth"), 6, 1, 12)
    search_roots = _dedupe_paths(
        [
            root / "state",
            root / "qwen-agent-workspace" / "vulkan-broker" / "agent-jobs",
            root / "output",
            root / "services" / "openwebui-data",
            root / "services" / "codex_bridge",
        ]
    )
    aliases = _known_aliases(root)
    alias_by_path = {str(path.resolve()).lower(): name for name, path in aliases.items() if path.exists()}
    rows: list[dict[str, Any]] = []
    skipped_roots: list[str] = []
    blocked_dirs = {".git", ".venv", "venv", "venvs", "node_modules", "__pycache__"}

    for search_root in search_roots:
        if not search_root.is_dir():
            skipped_roots.append(str(search_root))
            continue
        stack: list[tuple[Path, int]] = [(search_root, 0)]
        while stack and len(rows) < max_results:
            current, depth = stack.pop()
            try:
                entries = list(current.iterdir())
            except OSError:
                continue
            for entry in entries:
                if len(rows) >= max_results:
                    break
                if entry.is_dir():
                    if depth + 1 <= max_depth and entry.name not in blocked_dirs:
                        stack.append((entry, depth + 1))
                    continue
                if entry.suffix.lower() not in DB_SUFFIXES:
                    continue
                try:
                    stat = entry.stat()
                    resolved = entry.resolve()
                except OSError:
                    continue
                rows.append(
                    {
                        "path": str(resolved),
                        "relative_path": str(resolved.relative_to(root)) if _path_is_under(resolved, root) else str(resolved),
                        "alias": alias_by_path.get(str(resolved).lower(), ""),
                        "size_bytes": stat.st_size,
                        "modified_unix": stat.st_mtime,
                    }
                )

    rows.sort(key=lambda item: str(item.get("path") or "").lower())
    return {
        "ok": True,
        "tool": "aicarmine_sqlite_readonly_list_databases",
        "repo_root": str(root),
        "allowed_roots": [str(path) for path in _allowed_roots(root)],
        "known_aliases": {name: str(path) for name, path in aliases.items()},
        "databases": rows[:max_results],
        "count": min(len(rows), max_results),
        "truncated": len(rows) > max_results,
        "skipped_missing_roots": skipped_roots,
    }


def _health(args: dict[str, Any], root: Path, tools: dict[str, ToolSpec]) -> dict[str, Any]:
    payload = health_payload(SERVER_NAME, list(tools))
    payload.update(
        {
            "read_only": True,
            "only_select": True,
            "path_allowlist": [str(path) for path in _allowed_roots(root)],
            "known_aliases": {name: str(path) for name, path in _known_aliases(root).items()},
            "no_user_pragmas": True,
            "no_sql_writes": True,
        }
    )
    return payload


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        return _health(args, root, tools)

    tools["aicarmine_sqlite_readonly_health"] = ToolSpec(
        name="aicarmine_sqlite_readonly_health",
        description="Report SQLite read-only MCP health, aliases, allowlist and safety guarantees.",
        input_schema=object_schema(),
        handler=health,
    )
    tools["aicarmine_sqlite_readonly_list_databases"] = ToolSpec(
        name="aicarmine_sqlite_readonly_list_databases",
        description="List allowlisted SQLite databases under known repo state and job artifact roots.",
        input_schema=object_schema(
            {
                "max_results": integer_prop(200, 1, 1000),
                "limit": integer_prop(200, 1, 1000),
                "max_depth": integer_prop(6, 1, 12),
            }
        ),
        handler=_list_databases,
    )
    tools["aicarmine_sqlite_readonly_schema"] = ToolSpec(
        name="aicarmine_sqlite_readonly_schema",
        description="Read table/view schema from an allowlisted SQLite database.",
        input_schema=object_schema(
            {
                "db": string_prop(),
                "include_columns": boolean_prop(True),
                "include_sql": boolean_prop(False),
                "timeout_seconds": integer_prop(5, 1, 30),
            },
            required=["db"],
        ),
        handler=_schema,
    )
    tools["aicarmine_sqlite_readonly_query"] = ToolSpec(
        name="aicarmine_sqlite_readonly_query",
        description="Run one bounded SELECT/WITH query against an allowlisted SQLite database.",
        input_schema=object_schema(
            {
                "db": string_prop(),
                "sql": string_prop(),
                "query": string_prop(),
                "row_limit": integer_prop(100, 1, 1000),
                "limit": integer_prop(100, 1, 1000),
                "timeout_seconds": integer_prop(5, 1, 30),
                "max_cell_chars": integer_prop(4000, 200, 20000),
            },
            required=["db"],
        ),
        handler=_query,
        required_one_of=[["sql"], ["query"]],
    )
    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    if "--self-test" in argv:
        result = self_test(
            server_name=SERVER_NAME,
            server_version=SERVER_VERSION,
            tools=tools,
            health_tool="aicarmine_sqlite_readonly_health",
            real_tool="aicarmine_sqlite_readonly_list_databases",
            real_args={"max_results": 5},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())
