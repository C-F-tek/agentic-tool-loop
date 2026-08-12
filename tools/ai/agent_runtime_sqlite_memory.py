#!/usr/bin/env python3
"""Runtime SQLite memory tool for IA-Carmine planners.

This tool separates two memory classes:

- persistent/consistent memory:
  read-only access to the project memory database, intended as durable memory;

- operational context memory:
  scratch SQLite database under output/**, writable and clearable at runtime.

The operational database is a doctor's working tray: useful during diagnosis,
safe to empty, and never meant to be committed. Persistent memory is protected:
this tool does not write, promote, delete or migrate it.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_OPERATIONAL_DB = "output/ai_runtime_memory/operational_context.sqlite"
DEFAULT_PERSISTENT_DB = "indexAI/agent_memory/agent_memory.sqlite"
DEFAULT_OUTPUT = "output/validation/agent_runtime_sqlite_memory.json"
DEFAULT_MARKDOWN = "output/validation/agent_runtime_sqlite_memory.md"
SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def repo_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path)


def is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False


def safe_id(value: str) -> str:
    text = SAFE_ID_RE.sub("_", str(value or "").strip()).strip("._-")
    return text[:80] or "runtime_memory"


def parse_tags(values: list[str]) -> list[str]:
    tags: list[str] = []
    for value in values:
        for part in str(value).split(","):
            normalized = part.strip()
            if normalized and normalized not in tags:
                tags.append(normalized)
    return tags


def ensure_operational_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS operational_memory_records (
                record_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                scope TEXT NOT NULL,
                role TEXT NOT NULL,
                summary TEXT NOT NULL,
                content TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_operational_memory_kind ON operational_memory_records(kind)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_operational_memory_scope ON operational_memory_records(scope)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_operational_memory_role ON operational_memory_records(role)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS operational_memory_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute("INSERT OR REPLACE INTO operational_memory_meta(key, value) VALUES('schema_version', '1')")
        conn.execute("INSERT OR REPLACE INTO operational_memory_meta(key, value) VALUES('memory_class', 'operational_context')")


def operational_status(db_path: Path) -> dict[str, Any]:
    ensure_operational_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row_count = conn.execute("SELECT count(*) FROM operational_memory_records").fetchone()[0]
        kind_rows = conn.execute(
            "SELECT kind, count(*) AS count FROM operational_memory_records GROUP BY kind ORDER BY count DESC, kind"
        ).fetchall()
        role_rows = conn.execute(
            "SELECT role, count(*) AS count FROM operational_memory_records GROUP BY role ORDER BY count DESC, role"
        ).fetchall()
    return {
        "record_count": row_count,
        "kind_counts": {str(row["kind"]): int(row["count"]) for row in kind_rows},
        "role_counts": {str(row["role"]): int(row["count"]) for row in role_rows},
    }


def persistent_status(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {"exists": False, "opened_read_only": False, "record_count": 0, "tables": []}
    tables: list[dict[str, Any]] = []
    record_count = 0
    uri = f"file:{db_path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        table_rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        for row in table_rows:
            table_name = str(row["name"])
            try:
                count = conn.execute(f'SELECT count(*) FROM "{table_name.replace(chr(34), chr(34) + chr(34))}"').fetchone()[0]
            except Exception:
                count = None
            tables.append({"name": table_name, "row_count": count})
        if any(item["name"] == "memory_records" for item in tables):
            record_count = conn.execute("SELECT count(*) FROM memory_records").fetchone()[0]
    return {"exists": True, "opened_read_only": True, "record_count": record_count, "tables": tables}


def ensure_persistent_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_records (
                record_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                scope TEXT NOT NULL,
                source TEXT NOT NULL,
                summary TEXT NOT NULL,
                content TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_records_kind ON memory_records(kind)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_records_scope ON memory_records(scope)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_records_source ON memory_records(source)")


def remember_operational(db_path: Path, *, summary: str, content: str, role: str, tags: list[str], metadata: dict[str, Any]) -> dict[str, Any]:
    ensure_operational_db(db_path)
    timestamp = now_iso()
    identity = f"{timestamp}:{role}:{summary}:{content}"
    record_id = safe_id(identity)[:48]
    if not content.strip():
        raise ValueError("content is required for operational remember")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO operational_memory_records (
                record_id, created_at, updated_at, kind, scope, role,
                summary, content, tags_json, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                timestamp,
                timestamp,
                "operational_context",
                "runtime",
                role,
                summary or content[:180],
                content,
                json.dumps(tags, ensure_ascii=False),
                json.dumps(metadata, ensure_ascii=False),
            ),
        )
    return {"record_id": record_id, "created_at": timestamp}


def remember_persistent(db_path: Path, *, summary: str, content: str, source: str, tags: list[str], metadata: dict[str, Any]) -> dict[str, Any]:
    ensure_persistent_db(db_path)
    timestamp = now_iso()
    identity = f"{timestamp}:{source}:{summary}:{content}"
    record_id = safe_id(identity)[:64]
    if not content.strip():
        raise ValueError("content is required for persistent remember")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO memory_records (
                record_id, created_at, updated_at, kind, scope, source,
                summary, content, tags_json, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                timestamp,
                timestamp,
                "project_operating_rule",
                "persistent",
                source,
                summary or content[:180],
                content,
                json.dumps(tags, ensure_ascii=False),
                json.dumps(metadata, ensure_ascii=False),
            ),
        )
    return {"record_id": record_id, "created_at": timestamp, "persistent_database_written": True}


def search_operational(db_path: Path, query: str, limit: int) -> list[dict[str, Any]]:
    ensure_operational_db(db_path)
    pattern = f"%{query}%"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if query:
            rows = conn.execute(
                """
                SELECT record_id, created_at, updated_at, kind, scope, role, summary, content, tags_json, metadata_json
                FROM operational_memory_records
                WHERE summary LIKE ? OR content LIKE ? OR tags_json LIKE ? OR role LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (pattern, pattern, pattern, pattern, int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT record_id, created_at, updated_at, kind, scope, role, summary, content, tags_json, metadata_json
                FROM operational_memory_records
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
    return [row_to_dict(row) for row in rows]


def search_persistent(db_path: Path, query: str, limit: int) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    pattern = f"%{query}%"
    uri = f"file:{db_path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        has_memory_records = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='memory_records'"
        ).fetchone()[0]
        if not has_memory_records:
            return []
        if query:
            rows = conn.execute(
                """
                SELECT record_id, created_at, updated_at, kind, scope, source, summary, content, tags_json, metadata_json
                FROM memory_records
                WHERE summary LIKE ? OR content LIKE ? OR tags_json LIKE ? OR source LIKE ?
                ORDER BY COALESCE(updated_at, created_at) DESC
                LIMIT ?
                """,
                (pattern, pattern, pattern, pattern, int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT record_id, created_at, updated_at, kind, scope, source, summary, content, tags_json, metadata_json
                FROM memory_records
                ORDER BY COALESCE(updated_at, created_at) DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
    return [persistent_row_to_dict(row) for row in rows]


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "record_id": row["record_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "kind": row["kind"],
        "scope": row["scope"],
        "role": row["role"],
        "summary": row["summary"],
        "content_preview": str(row["content"])[:1000],
        "tags": json.loads(row["tags_json"] or "[]"),
        "metadata": json.loads(row["metadata_json"] or "{}"),
    }


def persistent_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "record_id": row["record_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "kind": row["kind"],
        "scope": row["scope"],
        "source": row["source"],
        "summary": row["summary"],
        "content_preview": str(row["content"])[:1000],
        "tags": json.loads(row["tags_json"] or "[]"),
        "metadata": json.loads(row["metadata_json"] or "{}"),
    }


def clear_operational(db_path: Path, confirm: str) -> dict[str, Any]:
    ensure_operational_db(db_path)
    if confirm != "clear_operational":
        raise ValueError("clear_operational requires --confirm clear_operational")
    before = operational_status(db_path)["record_count"]
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM operational_memory_records")
    return {"cleared": before, "remaining": operational_status(db_path)["record_count"]}


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    operational_db = resolve_path(repo_root, args.database)
    persistent_db = resolve_path(repo_root, args.persistent_database)
    output_root = resolve_path(repo_root, "output")
    errors: list[str] = []
    warnings: list[str] = []
    result: dict[str, Any] = {}
    operation = args.action
    memory_scope = args.scope
    operational_db_allowed = is_under(operational_db, output_root)
    operational_write = False
    operational_clear = False
    persistent_write = False

    if memory_scope == "operational" and not operational_db_allowed:
        errors.append("operational database must be under output/**")
    else:
        try:
            if operation == "status":
                result = operational_status(operational_db) if memory_scope == "operational" else persistent_status(persistent_db)
            elif operation == "remember":
                if memory_scope == "operational":
                    result = remember_operational(
                        operational_db,
                        summary=args.summary,
                        content=args.content,
                        role=args.role,
                        tags=parse_tags(args.tag),
                        metadata={"tool": "agent_runtime_sqlite_memory", "request_id": args.request_id},
                    )
                    operational_write = True
                elif memory_scope == "persistent":
                    if not args.allow_persistent_write or args.confirm != "persistent_write":
                        raise ValueError("persistent remember requires --allow-persistent-write and --confirm persistent_write")
                    result = remember_persistent(
                        persistent_db,
                        summary=args.summary,
                        content=args.content,
                        source=args.role,
                        tags=parse_tags(args.tag),
                        metadata={"tool": "agent_runtime_sqlite_memory", "request_id": args.request_id, "explicit_confirm": args.confirm},
                    )
                    persistent_write = True
                else:
                    raise ValueError(f"unsupported memory scope for remember: {memory_scope}")
            elif operation == "search":
                result = {
                    "query": args.query,
                    "records": search_operational(operational_db, args.query, args.limit)
                    if memory_scope == "operational"
                    else search_persistent(persistent_db, args.query, args.limit),
                }
            elif operation == "clear_operational":
                if memory_scope != "operational":
                    raise ValueError("clear_operational is allowed only for operational memory")
                result = clear_operational(operational_db, args.confirm)
                operational_write = True
                operational_clear = True
            else:
                raise ValueError(f"unsupported action: {operation}")
        except Exception as exc:  # noqa: BLE001 - report-only tool result.
            errors.append(f"{type(exc).__name__}: {exc}")

    return {
        "schema_version": 1,
        "kind": "agent_runtime_sqlite_memory",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "sqlite_write_performed": persistent_write,
        "persistent_memory_write_performed": persistent_write,
        "operational_sqlite_write_performed": operational_write,
        "persistent_sqlite_write_performed": persistent_write,
        "operational_memory_write_performed": operational_write,
        "operational_memory_clear_performed": operational_clear,
        "action": operation,
        "scope": memory_scope,
        "operational_database": repo_rel(operational_db, repo_root),
        "persistent_database": repo_rel(persistent_db, repo_root),
        "operational_database_under_output": operational_db_allowed,
        "result": result,
        "guardrails": {
            "persistent_memory_read_only": True,
            "persistent_memory_write_performed": persistent_write,
            "persistent_memory_promotion_performed": False,
            "persistent_memory_write_authorized": bool(args.allow_persistent_write and args.confirm == "persistent_write"),
            "sqlite_write_performed": persistent_write,
            "operational_sqlite_write_performed": operational_write,
            "operational_memory_clear_performed": operational_clear,
            "operational_database_must_be_under_output": True,
            "operational_database_under_output": operational_db_allowed,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "blender_runtime_touched": False,
            "git_write_performed": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agent Runtime SQLite Memory", ""]
    for key in (
        "passed",
        "action",
        "scope",
        "operational_database",
        "persistent_database",
        "provider_execution_performed",
        "patch_application_performed",
        "sqlite_write_performed",
        "persistent_memory_write_performed",
        "operational_sqlite_write_performed",
        "operational_memory_clear_performed",
    ):
        lines.append(f"- {key}: `{report.get(key)}`")
    lines.append("")
    lines.append("## Result")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report.get("result", {}), indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    lines.append("## Guardrails")
    lines.append("")
    for key, value in report.get("guardrails", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--action", choices=("status", "remember", "search", "clear_operational"), default="status")
    parser.add_argument("--scope", choices=("operational", "persistent"), default="operational")
    parser.add_argument("--database", default=DEFAULT_OPERATIONAL_DB)
    parser.add_argument("--persistent-database", default=DEFAULT_PERSISTENT_DB)
    parser.add_argument("--request-id", default="runtime_sqlite_memory")
    parser.add_argument("--summary", default="")
    parser.add_argument("--content", default="")
    parser.add_argument("--role", default="doctor_tool")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--query", default="")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--confirm", default="")
    parser.add_argument("--allow-persistent-write", action="store_true")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_report(args)
    output = resolve_path(repo_root, args.output)
    markdown = resolve_path(repo_root, args.markdown_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown),
                "action": report["action"],
                "scope": report["scope"],
                "sqlite_write_performed": report["sqlite_write_performed"],
                "persistent_memory_write_performed": report["persistent_memory_write_performed"],
                "operational_sqlite_write_performed": report["operational_sqlite_write_performed"],
                "operational_memory_clear_performed": report["operational_memory_clear_performed"],
                "patch_application_performed": report["patch_application_performed"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

