"""Planner scratchpad and broker-owned SQLite memory tools."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from .config import PLANNER_MEMORY_DB, PLANNER_MEMORY_RETENTION_DAYS


def _dict_from_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _dict_items_field(mapping: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = mapping.get(key)
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _scratchpad_path(root: Path) -> Path:
    return root / "planner_scratchpad.json"


def _read_scratchpad(root: Path) -> list[dict[str, Any]]:
    path = _scratchpad_path(root)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _write_scratchpad(root: Path, rows: list[dict[str, Any]]) -> None:
    path = _scratchpad_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _composer_db_path(root: Path) -> Path:
    return root / "planner_composer.sqlite"


def _connect_composer(root: Path) -> sqlite3.Connection:
    db_path = _composer_db_path(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS planner_answer_chunks (
            id TEXT PRIMARY KEY,
            ts REAL NOT NULL,
            kind TEXT NOT NULL,
            tag TEXT,
            text TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS planner_prompt_context_documents (
            id TEXT PRIMARY KEY,
            ts REAL NOT NULL,
            section TEXT NOT NULL,
            text TEXT NOT NULL,
            text_hash TEXT NOT NULL,
            metadata_json TEXT
        )
        """
    )
    conn.commit()
    return conn


def _text_hash(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8", errors="replace")).hexdigest()


CODE_PRODUCT_BUILD_STATE_KIND = "code_product_build_state"
CODE_PRODUCT_BUILD_STATE_SCHEMA = "code_product_build_state.v1"
CODE_PRODUCT_BUILD_STATE_STATUSES = {
    "collecting_source",
    "ready_for_propose",
    "blocked_incomplete",
}


def _window_text(text: str, *, query: str = "", max_chars: int = 3000) -> dict[str, Any]:
    full = str(text or "")
    budget = max(500, int(max_chars or 3000))
    if len(full) <= budget:
        return {
            "text": full,
            "window_start": 0,
            "window_end": len(full),
            "full_chars": len(full),
            "window_chars": len(full),
            "complete": True,
            "has_more_before": False,
            "has_more_after": False,
            "sha256": _text_hash(full),
            "window_sha256": _text_hash(full),
        }
    start = 0
    tokens = re.findall(r"[A-Za-z0-9_./-]{4,}", str(query or ""))
    for token in tokens[:12]:
        idx = full.lower().find(token.lower())
        if idx >= 0:
            start = max(0, idx - budget // 3)
            break
    end = min(len(full), start + budget)
    start = max(0, end - budget)
    window = full[start:end]
    return {
        "text": window,
        "window_start": start,
        "window_end": end,
        "full_chars": len(full),
        "window_chars": len(window),
        "complete": False,
        "has_more_before": start > 0,
        "has_more_after": end < len(full),
        "sha256": _text_hash(full),
        "window_sha256": _text_hash(window),
    }


def planner_prompt_context_store_window(
    root: Path,
    *,
    section: str,
    text: str,
    query: str = "",
    max_chars: int = 3000,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Store full pre-turn context and return one real planner window.

    This is controller substrate, not a planner-selectable tool. The returned
    window always contains real text plus offsets/hashes; the SQLite row is only
    the backing store for automatic prompt compaction.
    """
    full_text = str(text or "")
    text_hash = _text_hash(full_text)
    doc_id = f"prompt-context-{text_hash[:24]}"
    conn = _connect_composer(root)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO planner_prompt_context_documents
            (id, ts, section, text, text_hash, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                time.time(),
                str(section or "context"),
                full_text,
                text_hash,
                json.dumps(metadata or {}, ensure_ascii=False, default=str),
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT text FROM planner_prompt_context_documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
    finally:
        conn.close()
    stored_text = str(row["text"] if row is not None else full_text)
    window = _window_text(stored_text, query=query, max_chars=max_chars)
    return {
        "schema": "planner_prompt_context_window.v1",
        "section": str(section or "context"),
        "document_id": doc_id,
        "store": "job_local_sqlite",
        "metadata": metadata or {},
        **window,
    }


def _code_product_build_state_section(target_file: str) -> str:
    target = str(target_file or "").strip().replace("\\", "/")
    return f"{CODE_PRODUCT_BUILD_STATE_KIND}:{target}" if target else CODE_PRODUCT_BUILD_STATE_KIND


def _load_code_product_build_state_text(text: str) -> tuple[dict[str, Any], str]:
    try:
        parsed = json.loads(str(text or ""))
    except Exception:
        return {}, "invalid_code_product_build_state_json"
    if not isinstance(parsed, dict):
        return {}, "code_product_build_state_not_object"
    if parsed.get("schema") != CODE_PRODUCT_BUILD_STATE_SCHEMA:
        return parsed, "invalid_code_product_build_state_schema"
    return parsed, ""


def _code_product_build_state_complete_payload_ready(state: dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        return False
    if str(state.get("status") or "") != "ready_for_propose":
        return False
    if isinstance(state.get("unified_diff"), str) and state["unified_diff"].strip():
        return True
    if isinstance(state.get("old_text"), str) and isinstance(state.get("new_text"), str):
        return True
    operations = state.get("structured_operations")
    return isinstance(operations, list) and bool(operations)


def _write_code_product_build_state(args: dict[str, Any], root: Path) -> dict[str, Any]:
    text = str(args.get("text") or args.get("content") or "")
    if not text.strip():
        return {"ok": False, "tool": "planner_scratchpad_write", "mode": CODE_PRODUCT_BUILD_STATE_KIND, "error": "missing_text"}
    state, error = _load_code_product_build_state_text(text)
    if error:
        return {"ok": False, "tool": "planner_scratchpad_write", "mode": CODE_PRODUCT_BUILD_STATE_KIND, "error": error}
    target_file = str(args.get("target_file") or args.get("path") or state.get("target_file") or "").strip().replace("\\", "/")
    if not target_file:
        return {"ok": False, "tool": "planner_scratchpad_write", "mode": CODE_PRODUCT_BUILD_STATE_KIND, "error": "missing_target_file"}
    status = str(args.get("status") or state.get("status") or "").strip()
    if status not in CODE_PRODUCT_BUILD_STATE_STATUSES:
        return {"ok": False, "tool": "planner_scratchpad_write", "mode": CODE_PRODUCT_BUILD_STATE_KIND, "error": "invalid_status"}
    section = str(args.get("section") or _code_product_build_state_section(target_file))
    complete_payload_ready = _code_product_build_state_complete_payload_ready(state)
    window = planner_prompt_context_store_window(
        root,
        section=section,
        text=text,
        query=target_file,
        max_chars=max(500, int(args.get("max_chars") or 3000)),
        metadata={
            "kind": CODE_PRODUCT_BUILD_STATE_KIND,
            "schema": CODE_PRODUCT_BUILD_STATE_SCHEMA,
            "target_file": target_file,
            "status": status,
            "edit_kind": state.get("edit_kind"),
            "complete_payload_ready": complete_payload_ready,
        },
    )
    return {
        "ok": True,
        "tool": "planner_scratchpad_write",
        "mode": CODE_PRODUCT_BUILD_STATE_KIND,
        "schema": CODE_PRODUCT_BUILD_STATE_SCHEMA,
        "artifact": str(_composer_db_path(root)),
        "document_id": window.get("document_id"),
        "section": section,
        "target_file": target_file,
        "status": status,
        "sha256": window.get("sha256"),
        "complete_payload_ready": complete_payload_ready,
    }


def _write_composer_answer_chunk(root: Path, row: dict[str, Any]) -> dict[str, Any]:
    conn = _connect_composer(root)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO planner_answer_chunks
            (id, ts, kind, tag, text)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(row.get("id") or ""),
                float(row.get("ts") or 0.0),
                str(row.get("kind") or ""),
                str(row.get("tag") or ""),
                str(row.get("text") or ""),
            ),
        )
        conn.commit()
        count = conn.execute("SELECT count(*) FROM planner_answer_chunks").fetchone()[0]
    finally:
        conn.close()
    return {"artifact": str(_composer_db_path(root)), "count": int(count)}


def planner_composed_answer(root: Path) -> dict[str, Any]:
    db_path = _composer_db_path(root)
    if not db_path.exists():
        return {"ok": False, "reason": "planner_composer_missing", "artifact": str(db_path), "count": 0}
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, ts, kind, tag, text
            FROM planner_answer_chunks
            ORDER BY ts ASC, id ASC
            """
        ).fetchall()
    except Exception as exc:
        return {
            "ok": False,
            "reason": "planner_composer_read_failed",
            "error_type": type(exc).__name__,
            "artifact": str(db_path),
            "count": 0,
        }
    finally:
        if conn is not None:
            conn.close()
    chunks = [dict(row) for row in rows if str(dict(row).get("text") or "").strip()]
    if not chunks:
        return {"ok": False, "reason": "planner_composer_empty", "artifact": str(db_path), "count": 0}
    text = "\n\n".join(str(row.get("text") or "").strip() for row in chunks)
    return {
        "ok": True,
        "schema": "planner_answer_composer.v1",
        "artifact": str(db_path),
        "count": len(chunks),
        "chunks": [{k: row.get(k) for k in ("id", "kind", "tag", "ts")} for row in chunks],
        "text": text,
        "chars": len(text),
    }


def planner_scratchpad_write(args: dict[str, Any], root: Path) -> dict[str, Any]:
    if str(args.get("kind") or "").strip() == CODE_PRODUCT_BUILD_STATE_KIND:
        return _write_code_product_build_state(args, root)
    rows = _read_scratchpad(root)
    now = time.time()
    row = {
        "id": f"scratch-{int(now * 1000)}",
        "ts": now,
        "kind": str(args.get("kind") or "note"),
        "tag": str(args.get("tag") or ""),
        "text": str(args.get("text") or args.get("content") or ""),
    }
    if not row["text"].strip():
        return {"ok": False, "tool": "planner_scratchpad_write", "error": "missing_text"}
    rows.append(row)
    _write_scratchpad(root, rows)
    composer: dict[str, Any] = {}
    if row["kind"] in {"answer_chunk", "final_answer_chunk"}:
        composer = _write_composer_answer_chunk(root, row)
    result = {
        "ok": True,
        "tool": "planner_scratchpad_write",
        "artifact": str(_scratchpad_path(root)),
        "count": len(rows),
        "written": {k: row[k] for k in ("id", "kind", "tag", "ts")},
    }
    if composer:
        result["composer"] = composer
    return result


def _planner_prompt_context_read(args: dict[str, Any], root: Path) -> dict[str, Any]:
    db_path = _composer_db_path(root)
    if not db_path.exists():
        return {
            "ok": True,
            "tool": "planner_scratchpad_read",
            "mode": "prompt_context_window",
            "artifact": str(db_path),
            "count": 0,
            "items": [],
        }
    document_id = str(args.get("document_id") or args.get("id") or "").strip()
    section = str(args.get("section") or args.get("tag") or "").strip()
    query = str(args.get("query") or "").strip()
    limit = max(1, int(args.get("limit") or 3))
    max_chars = max(500, int(args.get("max_chars") or 3000))
    offset_arg = args.get("offset")
    offset = None
    if offset_arg not in (None, ""):
        try:
            offset = max(0, int(offset_arg))
        except (TypeError, ValueError):
            return {
                "ok": False,
                "tool": "planner_scratchpad_read",
                "mode": "prompt_context_window",
                "error": "invalid_offset",
            }
    where = ["1=1"]
    params: list[Any] = []
    if document_id:
        where.append("id = ?")
        params.append(document_id)
    if section and not document_id:
        where.append("section = ?")
        params.append(section)
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, ts, section, text, text_hash, metadata_json "
            f"FROM planner_prompt_context_documents WHERE {' AND '.join(where)} "
            "ORDER BY ts DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
    except sqlite3.Error as exc:
        return {
            "ok": False,
            "tool": "planner_scratchpad_read",
            "mode": "prompt_context_window",
            "artifact": str(db_path),
            "error": "planner_prompt_context_read_failed",
            "details": str(exc)[:1000],
        }
    finally:
        if conn is not None:
            conn.close()
    items: list[dict[str, Any]] = []
    for row in rows:
        raw = dict(row)
        text = str(raw.get("text") or "")
        if offset is None:
            window = _window_text(text, query=query, max_chars=max_chars)
        else:
            start = min(offset, len(text))
            end = min(len(text), start + max_chars)
            part = text[start:end]
            window = {
                "text": part,
                "window_start": start,
                "window_end": end,
                "full_chars": len(text),
                "window_chars": len(part),
                "complete": start == 0 and end >= len(text),
                "has_more_before": start > 0,
                "has_more_after": end < len(text),
                "sha256": raw.get("text_hash") or _text_hash(text),
                "window_sha256": _text_hash(part),
            }
        metadata: dict[str, Any] = {}
        try:
            loaded = json.loads(str(raw.get("metadata_json") or "{}"))
            metadata = loaded if isinstance(loaded, dict) else {}
        except Exception:
            metadata = {}
        items.append(
            {
                "document_id": raw.get("id"),
                "section": raw.get("section"),
                "store": "job_local_sqlite",
                "metadata": metadata,
                **window,
            }
        )
    return {
        "ok": True,
        "tool": "planner_scratchpad_read",
        "mode": "prompt_context_window",
        "artifact": str(db_path),
        "count": len(items),
        "items": items,
    }


def _read_code_product_build_state(args: dict[str, Any], root: Path) -> dict[str, Any]:
    adjusted = dict(args)
    target_file = str(adjusted.get("target_file") or adjusted.get("path") or "").strip().replace("\\", "/")
    if target_file and not str(adjusted.get("section") or "").strip() and not str(adjusted.get("document_id") or adjusted.get("id") or "").strip():
        adjusted["section"] = _code_product_build_state_section(target_file)
    result = _planner_prompt_context_read(adjusted, root)
    result["mode"] = CODE_PRODUCT_BUILD_STATE_KIND
    result["schema"] = "code_product_build_state_window.v1"
    result["kind"] = CODE_PRODUCT_BUILD_STATE_KIND
    items = _dict_items_field(result, "items")
    if items:
        first = items[0]
        metadata = _dict_from_value(first.get("metadata"))
        state, error = _load_code_product_build_state_text(str(first.get("text") or ""))
        result["target_file"] = metadata.get("target_file") or state.get("target_file") or target_file
        result["status"] = metadata.get("status") or state.get("status")
        result["complete_payload_ready"] = bool(
            metadata.get("complete_payload_ready")
            or _code_product_build_state_complete_payload_ready(state)
        )
        if error and first.get("complete") is True:
            result["state_parse_error"] = error
    return result


def planner_scratchpad_read(args: dict[str, Any], root: Path) -> dict[str, Any]:
    if str(args.get("kind") or "").strip() == CODE_PRODUCT_BUILD_STATE_KIND:
        return _read_code_product_build_state(args, root)
    if (
        str(args.get("kind") or "").strip() in {"prompt_context", "prompt_context_window"}
        or args.get("document_id")
        or args.get("section")
        or args.get("offset") not in (None, "")
    ):
        return _planner_prompt_context_read(args, root)
    rows = _read_scratchpad(root)
    query = str(args.get("query") or "").lower()
    tag = str(args.get("tag") or "")
    limit = max(1, int(args.get("limit") or 50))
    selected: list[dict[str, Any]] = []
    for row in reversed(rows):
        text = str(row.get("text") or "")
        if query and query not in text.lower() and query not in str(row.get("kind") or "").lower():
            continue
        if tag and tag != str(row.get("tag") or ""):
            continue
        selected.append(dict(row))
        if len(selected) >= limit:
            break
    selected.reverse()
    return {
        "ok": True,
        "tool": "planner_scratchpad_read",
        "artifact": str(_scratchpad_path(root)),
        "count": len(selected),
        "items": selected,
    }


def _memory_db(args: dict[str, Any]) -> Path:
    value = args.get("db") or args.get("path") or ""
    return Path(str(value)).resolve(strict=False) if value else PLANNER_MEMORY_DB


def _connect_memory(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_memory_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            expires_at REAL,
            kind TEXT NOT NULL,
            tag TEXT,
            text TEXT NOT NULL,
            metadata_json TEXT,
            pinned INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS broker_memory_records_fts "
        "USING fts5(text, kind, tag, content='broker_memory_records', content_rowid='id')"
    )
    conn.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS broker_memory_records_ai AFTER INSERT ON broker_memory_records BEGIN
            INSERT INTO broker_memory_records_fts(rowid, text, kind, tag)
            VALUES (new.id, new.text, new.kind, coalesce(new.tag, ''));
        END;
        CREATE TRIGGER IF NOT EXISTS broker_memory_records_ad AFTER DELETE ON broker_memory_records BEGIN
            INSERT INTO broker_memory_records_fts(broker_memory_records_fts, rowid, text, kind, tag)
            VALUES('delete', old.id, old.text, old.kind, coalesce(old.tag, ''));
        END;
        CREATE TRIGGER IF NOT EXISTS broker_memory_records_au AFTER UPDATE ON broker_memory_records BEGIN
            INSERT INTO broker_memory_records_fts(broker_memory_records_fts, rowid, text, kind, tag)
            VALUES('delete', old.id, old.text, old.kind, coalesce(old.tag, ''));
            INSERT INTO broker_memory_records_fts(rowid, text, kind, tag)
            VALUES (new.id, new.text, new.kind, coalesce(new.tag, ''));
        END;
        """
    )
    conn.commit()
    return conn


def runtime_sqlite_memory_write(args: dict[str, Any], root: Path) -> dict[str, Any]:
    db_path = _memory_db(args)
    text = str(args.get("text") or args.get("content") or "")[:24000]
    if not text.strip():
        return {"ok": False, "tool": "runtime_sqlite_memory_write", "error": "missing_text"}
    now = time.time()
    ttl_days = args.get("ttl_days")
    retention_days = int(ttl_days if ttl_days not in (None, "") else PLANNER_MEMORY_RETENTION_DAYS)
    expires_at = None if retention_days <= 0 else now + retention_days * 86400
    metadata = args.get("metadata") if isinstance(args.get("metadata"), dict) else {}
    conn = _connect_memory(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO broker_memory_records
            (created_at, updated_at, expires_at, kind, tag, text, metadata_json, pinned)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                now,
                expires_at,
                str(args.get("kind") or "planner_note"),
                str(args.get("tag") or ""),
                text,
                json.dumps(metadata, ensure_ascii=False, default=str),
                1 if bool(args.get("pinned")) else 0,
            ),
        )
        if cur.lastrowid is None:
            raise RuntimeError("sqlite_insert_missing_lastrowid")
        record_id = int(cur.lastrowid)
        conn.commit()
    finally:
        conn.close()
    return {
        "ok": True,
        "tool": "runtime_sqlite_memory_write",
        "db": str(db_path),
        "record_id": record_id,
        "expires_at": expires_at,
    }


def runtime_sqlite_memory_search(args: dict[str, Any], root: Path) -> dict[str, Any]:
    db_path = _memory_db(args)
    query = str(args.get("query") or "").strip()
    limit = max(1, int(args.get("limit") or 50))
    kind = str(args.get("kind") or "")
    tag = str(args.get("tag") or "")
    if not db_path.exists():
        return {"ok": True, "tool": "runtime_sqlite_memory_search", "db": str(db_path), "count": 0, "items": []}
    try:
        conn = _connect_memory(db_path)
        try:
            params: list[Any] = []
            where = ["1=1"]
            if kind:
                where.append("m.kind = ?")
                params.append(kind)
            if tag:
                where.append("coalesce(m.tag, '') = ?")
                params.append(tag)
            if query:
                sql = (
                    "SELECT m.* FROM broker_memory_records_fts f "
                    "JOIN broker_memory_records m ON m.id = f.rowid "
                    f"WHERE f.broker_memory_records_fts MATCH ? AND {' AND '.join(where)} "
                    "ORDER BY m.updated_at DESC LIMIT ?"
                )
                params = [query] + params + [limit]
            else:
                sql = (
                    "SELECT m.* FROM broker_memory_records m "
                    f"WHERE {' AND '.join(where)} ORDER BY m.updated_at DESC LIMIT ?"
                )
                params.append(limit)
            rows = [dict(row) for row in conn.execute(sql, params)]
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return {
            "ok": False,
            "tool": "runtime_sqlite_memory_search",
            "db": str(db_path),
            "error": "sqlite_memory_search_error",
            "details": str(exc)[:1000],
        }
    for row in rows:
        row["text"] = str(row.get("text") or "")[:2000]
    return {"ok": True, "tool": "runtime_sqlite_memory_search", "db": str(db_path), "count": len(rows), "items": rows}


def _planner_memory_query(goal: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9_]{3,}", str(goal or "").lower())
    deduped: list[str] = []
    for token in tokens:
        if token not in deduped:
            deduped.append(token)
        if len(deduped) >= 8:
            break
    return " ".join(deduped)


def planner_memory_surface(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Controller-injected planner memory surface.

    This is not a planner tool result. It makes memory availability explicit in
    the planner prompt so the model cannot infer that long-term memory is absent
    merely because it has not called a memory tool yet.
    """
    goal = str(args.get("goal") or "")
    limit = max(1, int(args.get("limit") or 12))
    target_key = str(args.get("target_key") or args.get("tag") or "").strip()
    db_path = _memory_db(args)
    scratchpad = planner_scratchpad_read({"limit": limit}, root)
    query = _planner_memory_query(goal)
    target_memory = (
        runtime_sqlite_memory_search({
            "db": str(db_path),
            "query": "",
            "kind": "controller_job_lesson",
            "tag": target_key,
            "limit": min(limit, 5),
        }, root)
        if target_key else {"ok": True, "tool": "runtime_sqlite_memory_search", "count": 0, "items": []}
    )
    target_loop_memory = (
        runtime_sqlite_memory_search({
            "db": str(db_path),
            "query": "",
            "kind": "controller_loop_turn",
            "tag": target_key,
            "limit": min(limit * 2, 50),
        }, root)
        if target_key else {"ok": True, "tool": "runtime_sqlite_memory_search", "count": 0, "items": []}
    )
    persistent = runtime_sqlite_memory_search({
        "db": str(db_path),
        "query": query,
        "kind": "controller_job_lesson",
        "limit": limit,
    }, root)
    loop_persistent = runtime_sqlite_memory_search({
        "db": str(db_path),
        "query": query,
        "kind": "controller_loop_turn",
        "limit": min(limit * 2, 50),
    }, root)
    scratch_items = _dict_items_field(scratchpad, "items")
    target_items = _dict_items_field(target_memory, "items")
    query_items = _dict_items_field(persistent, "items")
    target_loop_items = _dict_items_field(target_loop_memory, "items")
    query_loop_items = _dict_items_field(loop_persistent, "items")
    persistent_items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in [*target_items, *query_items]:
        row_id = str(row.get("id") or row.get("record_id") or row.get("text") or "")
        if row_id and row_id in seen_ids:
            continue
        if row_id:
            seen_ids.add(row_id)
        persistent_items.append(row)
        if len(persistent_items) >= limit:
            break
    loop_turn_items: list[dict[str, Any]] = []
    loop_seen_ids: set[str] = set()
    for row in [*target_loop_items, *query_loop_items]:
        row_id = str(row.get("id") or row.get("record_id") or row.get("text") or "")
        if row_id and row_id in loop_seen_ids:
            continue
        if row_id:
            loop_seen_ids.add(row_id)
        loop_turn_items.append(row)
        if len(loop_turn_items) >= min(limit * 2, 50):
            break
    persistent_ok = bool(target_memory.get("ok")) and bool(persistent.get("ok"))
    loop_turn_ok = bool(target_loop_memory.get("ok")) and bool(loop_persistent.get("ok"))
    memory_query_ok = persistent_ok and loop_turn_ok
    memory_query_error = (
        target_memory.get("error")
        or persistent.get("error")
        or target_loop_memory.get("error")
        or loop_persistent.get("error")
        or ""
    )
    memory_query_details = (
        target_memory.get("details")
        or persistent.get("details")
        or target_loop_memory.get("details")
        or loop_persistent.get("details")
        or ""
    )
    return {
        "available": True,
        "available_meaning": "feature_available_not_query_success",
        "memory_feature_available": True,
        "memory_query_ok": memory_query_ok,
        "memory_records_available": bool(persistent_items or loop_turn_items or scratch_items),
        "memory_query_error": memory_query_error,
        "memory_query_details": memory_query_details,
        "source": "controller_injected_planner_memory",
        "instruction": (
            "Long-term memory is available through this planner_memory surface "
            "and through runtime_sqlite_memory_* tools. If no records are shown, "
            "memory is available but currently empty for this query. If "
            "memory_query_ok=false, investigate the SQLite query error instead "
            "of treating memory as absent."
        ),
        "target_key": target_key,
        "goal_query": query,
        "scratchpad": {
            "available": True,
            "count": len(scratch_items),
            "items": scratch_items[:limit],
            "artifact": scratchpad.get("artifact"),
        },
        "persistent": {
            "available": True,
            "ok": persistent_ok,
            "target_count": int(target_memory.get("count") or 0),
            "query_count": int(persistent.get("count") or 0),
            "count": len(persistent_items),
            "items": persistent_items[:limit],
            "db": persistent.get("db"),
            "error": target_memory.get("error") or persistent.get("error"),
            "details": target_memory.get("details") or persistent.get("details"),
        },
        "loop_turn_memory": {
            "available": True,
            "kind": "controller_loop_turn",
            "instruction": (
                "Controller-owned per-turn loop memory written during the active "
                "loop. Use it to recover prior loop decisions/results when only a "
                "window of Ollama message history fits."
            ),
            "ok": loop_turn_ok,
            "target_count": int(target_loop_memory.get("count") or 0),
            "query_count": int(loop_persistent.get("count") or 0),
            "count": len(loop_turn_items),
            "items": loop_turn_items[: min(limit * 2, 50)],
            "db": loop_persistent.get("db") or target_loop_memory.get("db"),
            "error": target_loop_memory.get("error") or loop_persistent.get("error"),
            "details": target_loop_memory.get("details") or loop_persistent.get("details"),
        },
        "records": persistent_items[:limit],
        "record_count": len(persistent_items),
        "loop_turn_record_count": len(loop_turn_items),
    }


def runtime_sqlite_memory_cleanup(
    args: dict[str, Any],
    root: Path,
    allow_command: bool = False,
    user_consent: str = "",
) -> dict[str, Any]:
    db_path = _memory_db(args)
    dry_run = not bool(args.get("apply"))
    now = time.time()
    older_than_days = args.get("older_than_days")
    expired_only = bool(args.get("expired_only", True))
    kind = str(args.get("kind") or "")
    tag = str(args.get("tag") or "")
    pinned = bool(args.get("pinned", False))
    where = ["pinned = ?"]
    params: list[Any] = [1 if pinned else 0]
    if expired_only:
        where.append("expires_at IS NOT NULL AND expires_at <= ?")
        params.append(now)
    if older_than_days not in (None, ""):
        where.append("updated_at <= ?")
        params.append(now - int(older_than_days) * 86400)
    if kind:
        where.append("kind = ?")
        params.append(kind)
    if tag:
        where.append("coalesce(tag, '') = ?")
        params.append(tag)
    if len(where) <= 1:
        return {
            "ok": False,
            "tool": "runtime_sqlite_memory_cleanup",
            "error": "cleanup_requires_filter",
            "dry_run": dry_run,
        }
    conn = _connect_memory(db_path)
    try:
        rows = [dict(row) for row in conn.execute(
            f"SELECT id, kind, tag, updated_at, expires_at, pinned FROM broker_memory_records WHERE {' AND '.join(where)} ORDER BY updated_at LIMIT 500",
            params,
        )]
        if not dry_run and rows:
            if not allow_command:
                return {
                    "ok": False,
                    "tool": "runtime_sqlite_memory_cleanup",
                    "db": str(db_path),
                    "dry_run": True,
                    "needs_consent": True,
                    "error": "memory_cleanup_requires_command_permission",
                    "required_consent": "enable command/write permission and confirm runtime SQLite memory cleanup",
                    "would_delete_count": len(rows),
                    "items": rows[:100],
                }
            consent = str(user_consent or "").lower()
            if "confirm" not in consent and "confermo" not in consent:
                return {
                    "ok": False,
                    "tool": "runtime_sqlite_memory_cleanup",
                    "db": str(db_path),
                    "dry_run": True,
                    "needs_consent": True,
                    "error": "memory_cleanup_requires_user_consent",
                    "required_consent": "confirm runtime SQLite memory cleanup",
                    "would_delete_count": len(rows),
                    "items": rows[:100],
                }
        if not dry_run and rows:
            ids = [int(row["id"]) for row in rows]
            placeholders = ",".join("?" for _ in ids)
            conn.execute(f"DELETE FROM broker_memory_records WHERE id IN ({placeholders})", ids)
            conn.commit()
    finally:
        conn.close()
    return {
        "ok": True,
        "tool": "runtime_sqlite_memory_cleanup",
        "db": str(db_path),
        "dry_run": dry_run,
        "allow_command": bool(allow_command),
        "count": len(rows),
        "items": rows[:100],
    }
