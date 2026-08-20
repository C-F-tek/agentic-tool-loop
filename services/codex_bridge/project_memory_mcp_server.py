#!/usr/bin/env python3
"""Project-local persistent memory MCP server with explicit write semantics."""

from __future__ import annotations

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
    run_git,
    self_test,
    serve,
)

# Import agent memory models for AgentMicroTask support
try:
    from .agent_memory_models import (
        MemoryRecord,
        AgentMicroTask,
        build_state_packet,
    )
except ImportError:
    MemoryRecord = None
    AgentMicroTask = None
    build_state_packet = None

SERVER_NAME = "aicarmine-project-memory-mcp"
SERVER_VERSION = "0.1.0"

SCOPES = {"global", "repo", "branch", "service", "tool"}
SOURCE_TYPES = {"file", "job", "commit", "user", "diagnostic"}
STATUSES = {"active", "stale", "superseded", "rejected"}
KEY_RE = re.compile(r"^[A-Za-z0-9_.:/@+-]{2,180}$")
JOB_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
UPSERT_CONFIRM = "project_memory_upsert_verified"
STALE_CONFIRM = "project_memory_mark_stale"
SUPERSEDE_CONFIRM = "project_memory_supersede"
MAX_SOURCE_FILE_BYTES = 100_000_000


def string_prop(default: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    return schema


def number_prop(default: float, minimum: float, maximum: float) -> dict[str, Any]:
    return {"type": "number", "default": default, "minimum": minimum, "maximum": maximum}


def integer_prop(default: int, minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum, "maximum": maximum}


def boolean_prop(default: bool) -> dict[str, Any]:
    return {"type": "boolean", "default": default}


def string_array_prop(default: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
    if default is not None:
        schema["default"] = default
    return schema


def _safe_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def _safe_float(value: Any, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def _diagnostic_preview(value: Any, limit: int = 500) -> str:
    try:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        try:
            text = str(value)
        except Exception:
            text = f"<unprintable {type(value).__name__}>"
    return text[:limit]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _value_hash(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8", errors="replace")).hexdigest()


def _record_id( repo_root: Path, scope: str, branch: str, key: str, value_hash: str) -> str:
    raw = "\x00".join([str(repo_root.resolve()), scope, branch, key, value_hash])
    return "pmem-" + hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:32]


def _memory_db(root: Path) -> Path:
    env = os.environ.get("AICARMINE_PROJECT_MEMORY_DB", "").strip()
    if env:
        candidate = Path(env).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        return candidate.resolve()
    return (root / "state" / "project_memory" / "project_memory.sqlite3").resolve()


def _path_is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def _db_allowed(db_path: Path, root: Path) -> bool:
    return _path_is_under(db_path, root)


def _connect(root: Path,  create: bool) -> sqlite3.Connection | None:
    db_path = _memory_db(root)
    if not _db_allowed(db_path, root):
        raise ValueError(f"memory db outside repo root: {db_path}")
    if not db_path.exists() and not create:
        return None
    if create:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    if create:
        _ensure_schema(conn)
    return conn


def _sqlite_failure_payload(
    
    tool: str,
    root: Path,
    stage: str,
    exc: Exception,
    source_writes_performed: bool = False,
) -> dict[str, Any]:
    return {
        "ok": False,
        "tool": tool,
        "error": "project_memory_sqlite_error",
        "error_type": type(exc).__name__,
        "stage": stage,
        "db": str(_memory_db(root)),
        "message_preview": _diagnostic_preview(exc, 500),
        "source_writes_performed": source_writes_performed,
    }


def _rollback_quietly(conn: sqlite3.Connection) -> bool:
    try:
        conn.rollback()
        return True
    except sqlite3.Error:
        return False


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id TEXT NOT NULL UNIQUE,
            scope TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            value_hash TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            repo_root TEXT NOT NULL,
            branch TEXT NOT NULL,
            commit_sha TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_verified_at TEXT NOT NULL,
            status TEXT NOT NULL,
            confidence REAL NOT NULL,
            superseded_by TEXT,
            obsolete_reason TEXT,
            tags_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            verification_count INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_identity ON memory_records(repo_root, branch, scope, key, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_source ON memory_records(source_type, source_ref)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_status ON memory_records(status, updated_at)")
    conn.commit()


def _git_context(root: Path) -> dict[str, str]:
    branch_code, branch, _branch_err = run_git(root, "branch", "--show-current")
    commit_code, commit, _commit_err = run_git(root, "rev-parse", "HEAD")
    return {
        "branch": branch if branch_code == 0 else "",
        "commit_sha": commit if commit_code == 0 else "",
    }


def _validate_key(value: Any) -> tuple[str | None, dict[str, Any] | None]:
    key = str(value or "").strip()
    if not key:
        return None, {"ok": False, "error": "missing_key"}
    if not KEY_RE.fullmatch(key):
        return None, {"ok": False, "error": "invalid_key", "key": key, "allowed_pattern": KEY_RE.pattern}
    return key, None


def _validate_scope(value: Any) -> tuple[str | None, dict[str, Any] | None]:
    scope = str(value or "repo").strip().lower()
    if scope not in SCOPES:
        return None, {"ok": False, "error": "invalid_scope", "scope": scope, "allowed": sorted(SCOPES)}
    return scope, None


def _validate_source_type(value: Any) -> tuple[str | None, dict[str, Any] | None]:
    source_type = str(value or "").strip().lower()
    if source_type not in SOURCE_TYPES:
        return None, {"ok": False, "error": "invalid_source_type", "source_type": source_type, "allowed": sorted(SOURCE_TYPES)}
    return source_type, None


def _validate_status(value: Any, default: str = "active") -> tuple[str | None, dict[str, Any] | None]:
    status = str(value or default).strip().lower()
    if status not in STATUSES:
        return None, {"ok": False, "error": "invalid_status", "status": status, "allowed": sorted(STATUSES)}
    return status, None


def _parse_json(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value if value is not None else default


def _parse_tags(value: Any) -> list[str]:
    parsed = _parse_json(value, [])
    if not isinstance(parsed, list):
        return []
    out: list[str] = []
    for item in parsed:
        text = str(item).strip()
        if text and text not in out:
            out.append(text[:120])
    return out[:40]


def _parse_metadata(value: Any) -> dict[str, Any]:
    parsed = _parse_json(value, {})
    return dict(parsed) if isinstance(parsed, dict) else {}


def _search_terms(query: str, max_terms: int = 16) -> list[str]:
    terms: list[str] = []
    for raw in re.split(r"[\s,;]+", query.lower()):
        term = raw.strip()
        if len(term) < 2 or term in terms:
            continue
        terms.append(term)
        if len(terms) >= max_terms:
            break
    return terms


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _record_search_text(record: dict[str, Any]) -> str:
    return "\n".join(
        [
            str(record.get("key") or ""),
            str(record.get("value") or ""),
            str(record.get("source_ref") or ""),
            json.dumps(record.get("tags") or [], ensure_ascii=False),
            json.dumps(record.get("metadata") or {}, ensure_ascii=False, sort_keys=True),
        ]
    ).lower()


def _source_file_resolution(root: Path, source_ref: str) -> tuple[Path | None, dict[str, Any] | None]:
    text = str(source_ref or "").strip()
    if not text:
        return None, {"error": "missing_source_ref"}
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve(strict=False)
    except PermissionError as exc:
        return None, {
            "error": "source_file_permission_denied",
            "source_ref": source_ref,
            "error_type": type(exc).__name__,
            "message_preview": _diagnostic_preview(exc, 500),
        }
    except (OSError, RuntimeError) as exc:
        return None, {
            "error": "source_file_resolve_failed",
            "source_ref": source_ref,
            "error_type": type(exc).__name__,
            "message_preview": _diagnostic_preview(exc, 500),
        }
    if not _path_is_under(resolved, root):
        return None, {
            "error": "source_file_outside_repo",
            "source_ref": source_ref,
            "resolved": str(resolved),
            "repo_root": str(root.resolve(strict=False)),
        }
    return resolved, None


def _source_file_path(root: Path, source_ref: str) -> Path | None:
    path, _problem = _source_file_resolution(root, source_ref)
    return path


def _job_roots(root: Path) -> list[Path]:
    return [
        root / "qwen-agent-workspace" / "vulkan-broker" / "agent-jobs",
        root / "output" / "agent-jobs",
        root / "output" / "agent_jobs",
        root / "agent-jobs",
        root / "agent_jobs",
    ]


def _verify_source(root: Path, source_type: str, source_ref: str) -> dict[str, Any]:
    if not source_ref.strip():
        return {"ok": False, "error": "missing_source_ref"}
    if source_type == "file":
        path, problem = _source_file_resolution(root, source_ref)
        if problem is not None:
            return {
                "ok": False,
                "source_type": source_type,
                "source_ref": source_ref,
                **problem,
            }
        assert path is not None
        try:
            stat = path.stat()
        except FileNotFoundError:
            return {
                "ok": False,
                "source_type": source_type,
                "source_ref": source_ref,
                "resolved": str(path),
                "error": "source_file_not_found_or_not_file",
                "path_status": "missing",
            }
        except PermissionError as exc:
            return {
                "ok": False,
                "source_type": source_type,
                "source_ref": source_ref,
                "resolved": str(path),
                "error": "source_file_permission_denied",
                "error_type": type(exc).__name__,
                "message_preview": _diagnostic_preview(exc, 500),
            }
        except OSError as exc:
            return {
                "ok": False,
                "source_type": source_type,
                "source_ref": source_ref,
                "resolved": str(path),
                "error": "source_file_stat_failed",
                "error_type": type(exc).__name__,
                "message_preview": _diagnostic_preview(exc, 500),
            }
        if not path.is_file():
            return {
                "ok": False,
                "source_type": source_type,
                "source_ref": source_ref,
                "resolved": str(path),
                "error": "source_file_not_found_or_not_file",
                "path_status": "directory" if path.is_dir() else "missing",
            }
        if stat.st_size > MAX_SOURCE_FILE_BYTES:
            return {
                "ok": False,
                "source_type": source_type,
                "source_ref": source_ref,
                "resolved": str(path),
                "error": "source_file_too_large",
                "size_bytes": stat.st_size,
                "max_bytes": MAX_SOURCE_FILE_BYTES,
            }
        return {
            "ok": True,
            "source_type": source_type,
            "source_ref": source_ref,
            "resolved": str(path),
            "size_bytes": stat.st_size,
            "error": "",
        }
    if source_type == "job":
        job_id = source_ref.strip()
        if not JOB_ID_RE.fullmatch(job_id):
            return {"ok": False, "source_type": source_type, "source_ref": source_ref, "error": "invalid_job_source_ref"}
        for jobs_root in _job_roots(root):
            candidate = jobs_root / job_id
            if candidate.is_dir():
                return {"ok": True, "source_type": source_type, "source_ref": source_ref, "resolved": str(candidate.resolve())}
        return {"ok": False, "source_type": source_type, "source_ref": source_ref, "error": "job_source_not_found"}
    if source_type == "commit":
        code, _stdout, _stderr = run_git(root, "cat-file", "-e", f"{source_ref}^{{commit}}")
        return {"ok": code == 0, "source_type": source_type, "source_ref": source_ref, "error": "" if code == 0 else "commit_source_not_found"}
    if source_type in {"user", "diagnostic"}:
        return {"ok": True, "source_type": source_type, "source_ref": source_ref, "externally_verifiable": False}
    return {"ok": False, "source_type": source_type, "source_ref": source_ref, "error": "unsupported_source_type"}


def _row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["tags"] = _parse_tags(item.get("tags_json"))
    item["metadata"] = _parse_metadata(item.get("metadata_json"))
    item.pop("tags_json", None)
    item.pop("metadata_json", None)
    return item


def _active_identity_row(conn: sqlite3.Connection,  root: Path, branch: str, scope: str, key: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM memory_records
        WHERE repo_root = ? AND branch = ? AND scope = ? AND key = ? AND status = 'active'
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (str(root.resolve()), branch, scope, key),
    ).fetchone()


def _record_by_id(conn: sqlite3.Connection, record_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM memory_records WHERE record_id = ?", (record_id,)).fetchone()


def _resolve_record(args: dict[str, Any], root: Path, conn: sqlite3.Connection) -> tuple[sqlite3.Row | None, dict[str, Any] | None]:
    record_id = str(args.get("record_id") or "").strip()
    if record_id:
        row = _record_by_id(conn, record_id)
        if row is None:
            return None, {"ok": False, "error": "record_not_found", "record_id": record_id}
        return row, None
    key, key_problem = _validate_key(args.get("key"))
    if key_problem is not None:
        return None, key_problem
    scope, scope_problem = _validate_scope(args.get("scope"))
    if scope_problem is not None:
        return None, scope_problem
    git = _git_context(root)
    branch = str(args.get("branch") or git["branch"] or "").strip()
    row = _active_identity_row(conn, root=root, branch=branch, scope=scope or "repo", key=key or "")
    if row is None:
        return None, {"ok": False, "error": "record_not_found", "scope": scope, "key": key, "branch": branch}
    return row, None


def _health(args: dict[str, Any], root: Path, tools: dict[str, ToolSpec]) -> dict[str, Any]:
    db_path = _memory_db(root)
    payload = health_payload(SERVER_NAME, list(tools))
    payload.update(
        {
            "project_local": True,
            "write_capable": True,
            "semantic_write_only": True,
            "db": str(db_path),
            "db_exists": db_path.is_file(),
            "db_under_repo_root": _db_allowed(db_path, root),
            "allowed_scopes": sorted(SCOPES),
            "allowed_source_types": sorted(SOURCE_TYPES),
            "allowed_statuses": sorted(STATUSES),
            "no_broker_http": True,
            "no_agentic_loop": True,
            "no_free_sql": True,
        }
    )
    return payload


def _search(args: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        conn = _connect(root, create=False)
    except (sqlite3.Error, PermissionError, OSError, ValueError) as exc:
        return _sqlite_failure_payload(tool="aicarmine_project_memory_search", root=root, stage="connect", exc=exc)
    if conn is None:
        return {
            "ok": True,
            "tool": "aicarmine_project_memory_search",
            "db": str(_memory_db(root)),
            "db_exists": False,
            "records": [],
            "count": 0,
        }
    query = str(args.get("query") or "").strip()
    limit = _safe_int(args.get("limit") or args.get("max_results"), 20, 1, 200)
    status = str(args.get("status") or "active").strip().lower()
    scope = str(args.get("scope") or "").strip().lower()
    source_type = str(args.get("source_type") or "").strip().lower()
    include_stale = bool(args.get("include_stale", False))
    clauses = ["repo_root = ?"]
    values: list[Any] = [str(root.resolve())]
    if status and status != "any":
        clauses.append("status = ?")
        values.append(status)
    elif not include_stale:
        clauses.append("status = 'active'")
    if scope:
        clauses.append("scope = ?")
        values.append(scope)
    if source_type:
        clauses.append("source_type = ?")
        values.append(source_type)
    query_terms = _search_terms(query)
    if query_terms:
        term_clauses = []
        for term in query_terms:
            like = f"%{_escape_like(term)}%"
            field_clauses = [
                f"{field} LIKE ? ESCAPE '\\'"
                for field in ("key", "value", "source_ref", "tags_json", "metadata_json")
            ]
            term_clauses.append("(" + " OR ".join(field_clauses) + ")")
            values.extend([like, like, like, like, like])
        clauses.append(f"({' OR '.join(term_clauses)})")
    sql = f"""
        SELECT * FROM memory_records
        WHERE {' AND '.join(clauses)}
        ORDER BY last_verified_at DESC, updated_at DESC, id DESC
        LIMIT ?
    """
    values.append(min(1000, max(limit, limit * 5)) if query_terms else limit)
    try:
        rows = conn.execute(sql, values).fetchall()
    except (sqlite3.Error, PermissionError, OSError, ValueError) as exc:
        return _sqlite_failure_payload(tool="aicarmine_project_memory_search", root=root, stage="query", exc=exc)
    finally:
        conn.close()
    records = [_row_to_record(row) for row in rows]
    if query_terms:
        scored: list[tuple[int, str, str, dict[str, Any]]] = []
        for record in records:
            search_text = _record_search_text(record)
            score = sum(1 for term in query_terms if term in search_text)
            if score <= 0:
                continue
            record["search_score"] = score
            scored.append((score, str(record.get("last_verified_at") or ""), str(record.get("updated_at") or ""), record))
        records = [record for _score, _verified, _updated, record in sorted(scored, key=lambda item: -item[0])[:limit]]
    return {
        "ok": True,
        "tool": "aicarmine_project_memory_search",
        "db": str(_memory_db(root)),
        "db_exists": True,
        "query_terms": query_terms,
        "records": records,
        "count": len(records),
    }


def _get(args: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        conn = _connect(root, create=False)
    except (sqlite3.Error, PermissionError, OSError, ValueError) as exc:
        return _sqlite_failure_payload(tool="aicarmine_project_memory_get", root=root, stage="connect", exc=exc)
    if conn is None:
        return {"ok": False, "tool": "aicarmine_project_memory_get", "error": "memory_db_not_found", "db": str(_memory_db(root))}
    try:
        row, problem = _resolve_record(args, root, conn)
    except (sqlite3.Error, PermissionError, OSError, ValueError) as exc:
        return _sqlite_failure_payload(tool="aicarmine_project_memory_get", root=root, stage="query", exc=exc)
    finally:
        conn.close()
    if problem is not None:
        problem["tool"] = "aicarmine_project_memory_get"
        return problem
    assert row is not None
    return {"ok": True, "tool": "aicarmine_project_memory_get", "record": _row_to_record(row)}


def _upsert_verified(args: dict[str, Any], root: Path) -> dict[str, Any]:
    confirm = str(args.get("confirm_write") or "").strip()
    if confirm != UPSERT_CONFIRM:
        return {
            "ok": False,
            "tool": "aicarmine_project_memory_upsert_verified",
            "error": "missing_confirm_write",
            "expected": UPSERT_CONFIRM,
            "provided_preview": confirm[:120],
            "source_writes_performed": False,
        }
    key, key_problem = _validate_key(args.get("key"))
    if key_problem is not None:
        return key_problem
    scope, scope_problem = _validate_scope(args.get("scope"))
    if scope_problem is not None:
        return scope_problem
    source_type, source_problem = _validate_source_type(args.get("source_type"))
    if source_problem is not None:
        return source_problem
    status, status_problem = _validate_status(args.get("status"), default="active")
    if status_problem is not None:
        return status_problem
    value = str(args.get("value") or "").strip()
    if not value:
        return {"ok": False, "error": "missing_value"}
    source_ref = str(args.get("source_ref") or "").strip()
    source_check = _verify_source(root, source_type or "", source_ref)
    if not source_check.get("ok"):
        return {"ok": False, "error": "source_verification_failed", "source_check": source_check}

    git = _git_context(root)
    branch = str(args.get("branch") or git["branch"] or "").strip()
    commit_sha = str(args.get("commit_sha") or git["commit_sha"] or "").strip()
    confidence = _safe_float(args.get("confidence"), 1.0, 0.0, 1.0)
    tags = _parse_tags(args.get("tags"))
    metadata = _parse_metadata(args.get("metadata"))
    now = _now_iso()
    value_hash = _value_hash(value)
    record_id = _record_id(repo_root=root, scope=scope or "repo", branch=branch, key=key or "", value_hash=value_hash)
    supersede_existing = bool(args.get("supersede_existing", False))

    try:
        conn = _connect(root, create=True)
    except (sqlite3.Error, PermissionError, OSError, ValueError) as exc:
        return _sqlite_failure_payload(tool="aicarmine_project_memory_upsert_verified", root=root, stage="connect", exc=exc)
    assert conn is not None
    committed = False
    try:
        existing = _active_identity_row(conn, root=root, branch=branch, scope=scope or "repo", key=key or "")
        if existing is not None and existing["value_hash"] != value_hash and not supersede_existing:
            return {
                "ok": False,
                "tool": "aicarmine_project_memory_upsert_verified",
                "error": "active_memory_conflict",
                "message": "Existing active memory has a different value. Use supersede_existing=true or memory_supersede.",
                "existing": _row_to_record(existing),
                "source_writes_performed": False,
            }
        if existing is not None and existing["value_hash"] == value_hash:
            conn.execute(
                """
                UPDATE memory_records
                SET last_verified_at = ?, updated_at = ?, source_type = ?, source_ref = ?,
                    commit_sha = ?, confidence = ?, tags_json = ?, metadata_json = ?,
                    verification_count = verification_count + 1
                WHERE record_id = ?
                """,
                (
                    now,
                    now,
                    source_type,
                    source_ref,
                    commit_sha,
                    confidence,
                    _json_text(tags),
                    _json_text(metadata),
                    existing["record_id"],
                ),
            )
            conn.commit()
            committed = True
            row = _record_by_id(conn, existing["record_id"])
            return {
                "ok": True,
                "tool": "aicarmine_project_memory_upsert_verified",
                "changed": False,
                "verified_existing": True,
                "record": _row_to_record(row) if row is not None else {},
                "source_writes_performed": True,
                "write_scope": "project_local_sqlite_semantic_memory",
            }
        conn.execute(
            """
            INSERT INTO memory_records (
                record_id, scope, key, value, value_hash, source_type, source_ref,
                repo_root, branch, commit_sha, created_at, updated_at, last_verified_at,
                status, confidence, superseded_by, obsolete_reason, tags_json, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (
                record_id,
                scope,
                key,
                value,
                value_hash,
                source_type,
                source_ref,
                str(root.resolve()),
                branch,
                commit_sha,
                now,
                now,
                now,
                status,
                confidence,
                _json_text(tags),
                _json_text(metadata),
            ),
        )
        if existing is not None and supersede_existing:
            conn.execute(
                """
                UPDATE memory_records
                SET status = 'superseded', superseded_by = ?, obsolete_reason = ?, updated_at = ?
                WHERE record_id = ?
                """,
                (
                    record_id,
                    str(args.get("obsolete_reason") or "superseded by verified memory update"),
                    now,
                    existing["record_id"],
                ),
            )
        conn.commit()
        committed = True
        row = _record_by_id(conn, record_id)
        return {
            "ok": True,
            "tool": "aicarmine_project_memory_upsert_verified",
            "changed": True,
            "record": _row_to_record(row) if row is not None else {},
            "superseded_record_id": existing["record_id"] if existing is not None and supersede_existing else "",
            "source_writes_performed": True,
            "write_scope": "project_local_sqlite_semantic_memory",
        }
    except (sqlite3.Error, PermissionError, OSError, TypeError, ValueError) as exc:
        rollback_ok = True if committed else _rollback_quietly(conn)
        payload = _sqlite_failure_payload(
            tool="aicarmine_project_memory_upsert_verified",
            root=root,
            stage="post_commit_read" if committed else "write",
            exc=exc,
            source_writes_performed=committed,
        )
        payload["rollback_attempted"] = not committed
        payload["rollback_ok"] = rollback_ok
        return payload
    finally:
        conn.close()


def _mark_stale(args: dict[str, Any], root: Path) -> dict[str, Any]:
    if str(args.get("confirm_stale") or "").strip() != STALE_CONFIRM:
        return {
            "ok": False,
            "error": "missing_confirm_stale",
            "expected": STALE_CONFIRM,
            "source_writes_performed": False,
        }
    reason = str(args.get("obsolete_reason") or args.get("reason") or "").strip()
    if not reason:
        return {"ok": False, "error": "missing_obsolete_reason"}
    source_type, source_problem = _validate_source_type(args.get("source_type"))
    if source_problem is not None:
        return source_problem
    source_ref = str(args.get("source_ref") or "").strip()
    source_check = _verify_source(root, source_type or "", source_ref)
    if not source_check.get("ok"):
        return {"ok": False, "error": "source_verification_failed", "source_check": source_check}
    try:
        conn = _connect(root, create=False)
    except (sqlite3.Error, PermissionError, OSError, ValueError) as exc:
        return _sqlite_failure_payload(tool="aicarmine_project_memory_mark_stale", root=root, stage="connect", exc=exc)
    if conn is None:
        return {"ok": False, "tool": "aicarmine_project_memory_mark_stale", "error": "memory_db_not_found", "source_writes_performed": False}
    committed = False
    try:
        row, problem = _resolve_record(args, root, conn)
        if problem is not None:
            problem["tool"] = "aicarmine_project_memory_mark_stale"
            problem["source_writes_performed"] = False
            return problem
        assert row is not None
        now = _now_iso()
        metadata = _parse_metadata(row["metadata_json"])
        metadata.setdefault("stale_evidence", []).append({"source_type": source_type, "source_ref": source_ref, "ts": now})
        conn.execute(
            """
            UPDATE memory_records
            SET status = 'stale', obsolete_reason = ?, updated_at = ?, metadata_json = ?
            WHERE record_id = ?
            """,
            (reason, now, _json_text(metadata), row["record_id"]),
        )
        conn.commit()
        committed = True
        updated = _record_by_id(conn, row["record_id"])
        return {
            "ok": True,
            "tool": "aicarmine_project_memory_mark_stale",
            "record": _row_to_record(updated) if updated is not None else {},
            "source_writes_performed": True,
        }
    except (sqlite3.Error, PermissionError, OSError, TypeError, ValueError) as exc:
        rollback_ok = True if committed else _rollback_quietly(conn)
        payload = _sqlite_failure_payload(
            tool="aicarmine_project_memory_mark_stale",
            root=root,
            stage="post_commit_read" if committed else "write",
            exc=exc,
            source_writes_performed=committed,
        )
        payload["rollback_attempted"] = not committed
        payload["rollback_ok"] = rollback_ok
        return payload
    finally:
        conn.close()


def _supersede(args: dict[str, Any], root: Path) -> dict[str, Any]:
    if str(args.get("confirm_supersede") or "").strip() != SUPERSEDE_CONFIRM:
        return {
            "ok": False,
            "error": "missing_confirm_supersede",
            "expected": SUPERSEDE_CONFIRM,
            "source_writes_performed": False,
        }
    reason = str(args.get("obsolete_reason") or args.get("reason") or "").strip()
    if not reason:
        return {"ok": False, "error": "missing_obsolete_reason"}
    new_value = str(args.get("new_value") or args.get("value") or "").strip()
    if not new_value:
        return {"ok": False, "error": "missing_new_value"}
    try:
        conn = _connect(root, create=False)
    except (sqlite3.Error, PermissionError, OSError, ValueError) as exc:
        return _sqlite_failure_payload(tool="aicarmine_project_memory_supersede", root=root, stage="connect", exc=exc)
    if conn is None:
        return {"ok": False, "tool": "aicarmine_project_memory_supersede", "error": "memory_db_not_found", "source_writes_performed": False}
    try:
        old_row, problem = _resolve_record(args, root, conn)
    except (sqlite3.Error, PermissionError, OSError, ValueError) as exc:
        return _sqlite_failure_payload(tool="aicarmine_project_memory_supersede", root=root, stage="query", exc=exc)
    finally:
        conn.close()
    if problem is not None:
        problem["tool"] = "aicarmine_project_memory_supersede"
        problem["source_writes_performed"] = False
        return problem
    assert old_row is not None
    upsert_args = {
        "scope": args.get("new_scope") or old_row["scope"],
        "key": args.get("new_key") or old_row["key"],
        "value": new_value,
        "source_type": args.get("source_type"),
        "source_ref": args.get("source_ref"),
        "confidence": args.get("confidence", old_row["confidence"]),
        "tags": args.get("tags") or _parse_tags(old_row["tags_json"]),
        "metadata": args.get("metadata") or _parse_metadata(old_row["metadata_json"]),
        "supersede_existing": True,
        "obsolete_reason": reason,
        "branch": args.get("branch") or old_row["branch"],
        "confirm_write": UPSERT_CONFIRM,
    }
    result = _upsert_verified(upsert_args, root)
    if result.get("ok"):
        result["tool"] = "aicarmine_project_memory_supersede"
        result["superseded_record_id"] = old_row["record_id"]
    return result


def _audit_sources(args: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        conn = _connect(root, create=False)
    except (sqlite3.Error, PermissionError, OSError, ValueError) as exc:
        return _sqlite_failure_payload(tool="aicarmine_project_memory_audit_sources", root=root, stage="connect", exc=exc)
    if conn is None:
        return {
            "ok": True,
            "tool": "aicarmine_project_memory_audit_sources",
            "db": str(_memory_db(root)),
            "db_exists": False,
            "sources": [],
            "records_checked": 0,
        }
    status = str(args.get("status") or "active").strip().lower()
    limit = _safe_int(args.get("limit") or args.get("max_results"), 200, 1, 1000)
    clauses = ["repo_root = ?"]
    values: list[Any] = [str(root.resolve())]
    if status and status != "any":
        clauses.append("status = ?")
        values.append(status)
    try:
        rows = conn.execute(
            f"""
            SELECT record_id, source_type, source_ref, status, key
            FROM memory_records
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (*values, limit),
        ).fetchall()
    except (sqlite3.Error, PermissionError, OSError, ValueError) as exc:
        return _sqlite_failure_payload(tool="aicarmine_project_memory_audit_sources", root=root, stage="query", exc=exc)
    finally:
        conn.close()
    source_rows: list[dict[str, Any]] = []
    for row in rows:
        source_check = _verify_source(root, str(row["source_type"]), str(row["source_ref"]))
        source_rows.append(
            {
                "record_id": row["record_id"],
                "key": row["key"],
                "status": row["status"],
                "source_type": row["source_type"],
                "source_ref": row["source_ref"],
                "source_ok": bool(source_check.get("ok")),
                "source_check": source_check,
            }
        )
    broken = [item for item in source_rows if not item["source_ok"]]
    return {
        "ok": True,
        "tool": "aicarmine_project_memory_audit_sources",
        "db": str(_memory_db(root)),
        "db_exists": True,
        "sources": source_rows,
        "records_checked": len(source_rows),
        "broken_source_count": len(broken),
        "broken_sources": broken[:50],
    }


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        return _health(args, root, tools)

    tools["aicarmine_project_memory_health"] = ToolSpec(
        name="aicarmine_project_memory_health",
        description="Report project-local memory MCP health, DB path and write guardrails.",
        input_schema=object_schema(),
        handler=health,
    )
    tools["aicarmine_project_memory_search"] = ToolSpec(
        name="aicarmine_project_memory_search",
        description="Search project-local persistent memory records. Read-only.",
        input_schema=object_schema(
            {
                "query": string_prop(),
                "scope": string_prop(),
                "status": string_prop("active"),
                "source_type": string_prop(),
                "include_stale": boolean_prop(False),
                "limit": integer_prop(20, 1, 200),
                "max_results": integer_prop(20, 1, 200),
            }
        ),
        handler=_search,
    )
    tools["aicarmine_project_memory_get"] = ToolSpec(
        name="aicarmine_project_memory_get",
        description="Read one project-local memory record by record_id or active scope/key identity.",
        input_schema=object_schema(
            {
                "record_id": string_prop(),
                "scope": string_prop("repo"),
                "key": string_prop(),
                "branch": string_prop(),
            }
        ),
        handler=_get,
        required_one_of=[["record_id"], ["key"]],
    )
    tools["aicarmine_project_memory_upsert_verified"] = ToolSpec(
        name="aicarmine_project_memory_upsert_verified",
        description="Write or re-verify one memory record only with explicit source evidence.",
        input_schema=object_schema(
            {
                "scope": string_prop("repo"),
                "key": string_prop(),
                "value": string_prop(),
                "source_type": string_prop(),
                "source_ref": string_prop(),
                "branch": string_prop(),
                "commit_sha": string_prop(),
                "status": string_prop("active"),
                "confidence": number_prop(1.0, 0.0, 1.0),
                "tags": string_array_prop(),
                "metadata": {"type": "object"},
                "confirm_write": string_prop(),
                "supersede_existing": boolean_prop(False),
                "obsolete_reason": string_prop(),
            },
            required=["key", "value", "source_type", "source_ref", "confirm_write"],
        ),
        handler=_upsert_verified,
    )
    tools["aicarmine_project_memory_mark_stale"] = ToolSpec(
        name="aicarmine_project_memory_mark_stale",
        description="Mark a memory record stale with explicit evidence for the invalidation.",
        input_schema=object_schema(
            {
                "record_id": string_prop(),
                "scope": string_prop("repo"),
                "key": string_prop(),
                "branch": string_prop(),
                "obsolete_reason": string_prop(),
                "reason": string_prop(),
                "source_type": string_prop(),
                "source_ref": string_prop(),
                "confirm_stale": string_prop(),
            },
            required=["source_type", "source_ref", "confirm_stale"],
        ),
        handler=_mark_stale,
        required_one_of=[["record_id"], ["key"]],
    )
    tools["aicarmine_project_memory_supersede"] = ToolSpec(
        name="aicarmine_project_memory_supersede",
        description="Supersede a memory record by inserting a new verified record and linking the old one.",
        input_schema=object_schema(
            {
                "record_id": string_prop(),
                "scope": string_prop("repo"),
                "key": string_prop(),
                "branch": string_prop(),
                "new_scope": string_prop(),
                "new_key": string_prop(),
                "new_value": string_prop(),
                "value": string_prop(),
                "source_type": string_prop(),
                "source_ref": string_prop(),
                "confidence": number_prop(1.0, 0.0, 1.0),
                "tags": string_array_prop(),
                "metadata": {"type": "object"},
                "obsolete_reason": string_prop(),
                "reason": string_prop(),
                "confirm_supersede": string_prop(),
            },
            required=["source_type", "source_ref", "confirm_supersede"],
        ),
        handler=_supersede,
        required_one_of=[["record_id"], ["key"]],
    )
    tools["aicarmine_project_memory_audit_sources"] = ToolSpec(
        name="aicarmine_project_memory_audit_sources",
        description="Audit source references for project-local memory records. Read-only.",
        input_schema=object_schema(
            {
                "status": string_prop("active"),
                "limit": integer_prop(200, 1, 1000),
                "max_results": integer_prop(200, 1, 1000),
            }
        ),
        handler=_audit_sources,
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
            health_tool="aicarmine_project_memory_health",
            real_tool="aicarmine_project_memory_search",
            real_args={"limit": 1},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())
