from __future__ import annotations

from aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

import sqlite3
import json
import os
import urllib.error
import httpx
from pathlib import Path
from typing import Any

from aicarmine_broker.application.controller.rag_preseed import (
    _default_controller_rag_db,
    _env_int,
    _fts_query,
    _index_meta,
    _load_codex_rag_indexer,
    _parse_suffixes,
    _query_terms,
    _sqlite_tables,
)
from aicarmine_broker.config import LAB_REPO
from aicarmine_broker.tools.deterministic_common import (
    bounded_int_arg,
    deterministic_input_error,
    repo_existing_path,
    write_tool_artifact,
)


TOOL = "repo_semantic_search"
DEFAULT_RERANK_URL = "http://127.0.0.1:3550/v3/rerank"
DEFAULT_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"


def _bool_arg(args: dict[str, Any], name: str, *, default: bool) -> bool:
    raw = args.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _float_arg(args: dict[str, Any], name: str, *, default: float, minimum: float, maximum: float) -> float:
    raw = args.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        parsed = float(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _repo_token(value: Any) -> str:
    return str(value or "").replace("\\", "/").strip("/")


def _under_scope(path: str, scope: str) -> bool:
    rel = _repo_token(path)
    prefix = _repo_token(scope)
    if not prefix or prefix == ".":
        return True
    return rel == prefix or rel.startswith(prefix.rstrip("/") + "/")


def _write_result(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    artifact = write_tool_artifact(root, TOOL, payload)
    payload["artifact"] = str(artifact)
    return payload


def _build_delta_index(repo_root: Path, db: Path) -> dict[str, Any]:
    indexer = _load_codex_rag_indexer()
    default_suffixes = set(getattr(indexer, "DEFAULT_SUFFIXES"))
    return indexer.build_index(
        repo_root=repo_root,
        db=db,
        suffixes=_parse_suffixes(default_suffixes),
        exclude_dirs=set(),
        max_file_bytes=_env_int(
            "AICARMINE_CONTROLLER_RAG_MAX_FILE_BYTES",
            int(getattr(indexer, "MAX_FILE_BYTES_DEFAULT")),
            minimum=1_000,
            maximum=20_000_000,
        ),
        chunk_lines=_env_int(
            "AICARMINE_CONTROLLER_RAG_CHUNK_LINES",
            int(getattr(indexer, "CHUNK_LINES_DEFAULT")),
            minimum=20,
            maximum=1000,
        ),
        chunk_chars=_env_int(
            "AICARMINE_CONTROLLER_RAG_CHUNK_CHARS",
            int(getattr(indexer, "CHUNK_CHARS_DEFAULT")),
            minimum=1000,
            maximum=120_000,
        ),
        source=str(getattr(indexer, "SOURCE_GIT_DEFAULT")),
        mode=str(getattr(indexer, "MODE_DELTA")),
    )


def _http_json(method: str, url: str, payload: Any | None = None, timeout: int = 20) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = httpx.Client(timeout=30).post(url, data=data, method=method.upper(), headers=headers)
    with httpx.Client(timeout=30).get(request, timeout=timeout) as response:
        text = response.read().decode("utf-8", errors="replace")
    if not text.strip():
        return {}
    return json.loads(text)


def _parse_rerank_results(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        raw_results = value.get("results") or value.get("data") or []
    elif isinstance(value, list):
        raw_results = value
    else:
        raw_results = []
    out: list[dict[str, Any]] = []
    for position, item in enumerate(raw_results):
        if not isinstance(item, dict):
            continue
        index = item.get("index", item.get("document_index", item.get("id", position)))
        try:
            idx = int(index)
        except (TypeError, ValueError):
            idx = position
        score = item.get("relevance_score", item.get("score", item.get("logit", 0.0)))
        try:
            score_value = float(score)
        except (TypeError, ValueError):
            score_value = 0.0
        out.append({"index": idx, "score": score_value})
    return out


def _rerank_matches(
    *,
    query: str,
    candidates: list[dict[str, Any]],
    enabled: bool,
    candidate_limit: int,
    doc_chars: int,
    timeout_seconds: float,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    warnings: list[str] = []
    url = os.environ.get("AICARMINE_RAG_RERANK_URL", DEFAULT_RERANK_URL).strip() or DEFAULT_RERANK_URL
    model = os.environ.get("AICARMINE_RAG_RERANK_MODEL", DEFAULT_RERANK_MODEL).strip() or DEFAULT_RERANK_MODEL
    meta: dict[str, Any] = {
        "enabled": enabled,
        "status": "not_started",
        "url": url,
        "model": model,
        "candidate_limit": candidate_limit,
        "doc_chars": doc_chars,
        "timeout_seconds": timeout_seconds,
    }
    if not enabled:
        meta["status"] = "skipped_disabled"
        return candidates, warnings, meta

    rerank_candidates = candidates[:candidate_limit]
    docs = [str(item.get("_content") or item.get("content_preview") or "")[:doc_chars] for item in rerank_candidates]
    meta["input_count"] = len(docs)
    if not docs:
        meta["status"] = "skipped_no_candidates"
        return [], warnings, meta
    try:
        parsed = _parse_rerank_results(
            _http_json(
                "POST",
                url,
                payload={"model": model, "query": query, "documents": docs},
                timeout=max(1, int(timeout_seconds)),
            )
        )
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        warnings.append(f"reranker_unavailable:{type(exc).__name__}:{exc}")
        meta.update({"status": "unavailable", "error": type(exc).__name__, "detail": str(exc)})
        return candidates, warnings, meta

    ranked: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in parsed:
        idx = int(item["index"])
        if idx < 0 or idx >= len(rerank_candidates) or idx in seen:
            continue
        seen.add(idx)
        merged = dict(rerank_candidates[idx])
        merged["rerank_score"] = item["score"]
        ranked.append(merged)
    for idx, candidate in enumerate(rerank_candidates):
        if idx in seen:
            continue
        merged = dict(candidate)
        merged["rerank_score"] = None
        ranked.append(merged)
    for candidate in candidates[candidate_limit:]:
        merged = dict(candidate)
        merged["rerank_score"] = None
        ranked.append(merged)
    meta.update({"status": "ready", "returned_scores": len(parsed), "ranked_count": len(ranked)})
    return ranked, warnings, meta


def _query_rag_db(
    *,
    db: Path,
    repo_root: Path,
    query: str,
    scope: str,
    limit: int,
    candidate_limit: int,
    preview_chars: int,
    rerank_enabled: bool,
    rerank_candidate_limit: int,
    rerank_doc_chars: int,
    rerank_timeout_seconds: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    terms = _query_terms(query, limit=32)
    fts = _fts_query(terms)
    report: dict[str, Any] = {
        "query_terms": terms,
        "fts_query": fts,
        "candidate_limit": candidate_limit,
    }
    if not fts:
        report.update({"status": "skipped", "reason": "no_query_terms"})
        return [], report
    if not db.exists() or not db.is_file():
        report.update({"status": "unavailable", "reason": "rag_db_missing"})
        return [], report

    rows: list[tuple[Any, ...]]
    conn = sqlite3.connect(db)
    try:
        tables = _sqlite_tables(conn)
        missing = [name for name in ("chunks", "chunks_fts") if name not in tables]
        if missing:
            report.update({"status": "unavailable", "reason": "schema_missing", "missing_tables": missing})
            return [], report
        meta = _index_meta(conn)
        report["index_meta"] = {
            key: meta.get(key)
            for key in ("repo_root", "index_source", "index_mode", "selector", "indexed_at")
            if meta.get(key) not in (None, "")
        }
        meta_root = str(meta.get("repo_root") or "").strip()
        if meta_root and Path(meta_root).resolve(strict=False) != repo_root.resolve(strict=False):
            report["warning"] = "rag_db_repo_root_mismatch"
        rows = conn.execute(
            """
            SELECT c.path, c.kind, c.symbol, c.start_line, c.end_line, c.content, bm25(chunks_fts) AS rank_score
            FROM chunks_fts
            JOIN chunks AS c ON c.id = chunks_fts.rowid
            WHERE chunks_fts MATCH ?
            ORDER BY rank_score
            LIMIT ?
            """,
            (fts, candidate_limit),
        ).fetchall()
    finally:
        conn.close()

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for row in rows:
        path = _repo_token(row[0])
        if not path or not _under_scope(path, scope):
            continue
        full = (repo_root / path).resolve(strict=False)
        try:
            full.relative_to(repo_root)
        except ValueError:
            continue
        if not full.is_file():
            continue
        start_line = int(row[3] or 0)
        end_line = int(row[4] or 0)
        key = (path, start_line, end_line)
        if key in seen:
            continue
        seen.add(key)
        content = str(row[5] or "")
        candidates.append(
            {
                "path": path,
                "kind": str(row[1] or ""),
                "symbol": str(row[2] or ""),
                "start_line": start_line,
                "end_line": end_line,
                "rank_score": float(row[6] or 0.0),
                "_content": content,
                "content_preview": content[:preview_chars],
            }
        )
        if len(candidates) >= candidate_limit:
            break

    ranked, warnings, rerank = _rerank_matches(
        query=query,
        candidates=candidates,
        enabled=rerank_enabled,
        candidate_limit=rerank_candidate_limit,
        doc_chars=rerank_doc_chars,
        timeout_seconds=rerank_timeout_seconds,
    )
    matches = []
    for rank, item in enumerate(ranked[:limit], start=1):
        cleaned = {key: value for key, value in item.items() if key != "_content"}
        cleaned["rank"] = rank
        matches.append(cleaned)

    report.update({
        "status": "ready",
        "raw_match_count": len(rows),
        "scoped_match_count": len(candidates),
        "returned_count": len(matches),
        "rerank": rerank,
        "warnings": warnings,
    })
    return matches, report


def repo_semantic_search(args: dict[str, Any], root: Path) -> dict[str, Any]:
    query = str(
        args.get("query")
        or args.get("pattern")
        or args.get("symbol")
        or args.get("text")
        or args.get("needle")
        or ""
    ).strip()
    if not query:
        return {"ok": False, "tool": TOOL, "error": "missing_query"}

    try:
        limit = bounded_int_arg(args, ("limit", "top_k", "max_results"), default=8, minimum=1, maximum=30)
        candidate_limit = bounded_int_arg(
            args,
            "candidate_limit",
            default=max(40, limit * 8),
            minimum=limit,
            maximum=200,
        )
        rerank_candidate_limit = bounded_int_arg(
            args,
            "rerank_candidate_limit",
            default=min(candidate_limit, 12),
            minimum=1,
            maximum=candidate_limit,
        )
        rerank_doc_chars = bounded_int_arg(
            args,
            "rerank_doc_chars",
            default=2500,
            minimum=200,
            maximum=20_000,
        )
        preview_chars = bounded_int_arg(
            args,
            ("max_chunk_chars", "max_chars"),
            default=1200,
            minimum=120,
            maximum=5000,
        )
        rerank_timeout_seconds = _float_arg(
            args,
            "rerank_timeout_seconds",
            default=30.0,
            minimum=1.0,
            maximum=120.0,
        )
        scope, _ = repo_existing_path(args.get("path"), default=".")
    except Exception as exc:
        return deterministic_input_error(TOOL, exc)

    repo_root = LAB_REPO.resolve(strict=False)
    db = _default_controller_rag_db(repo_root)
    reindex_enabled = _bool_arg(args, "reindex", default=True)
    reindex: dict[str, Any] | None = None
    if reindex_enabled:
        try:
            reindex = _build_delta_index(repo_root, db)
        except Exception:
                
            payload = {
                "ok": False,
                "tool": TOOL,
                "error": "rag_reindex_failed",
                "error_type": type(exc).__name__,
                "detail": str(exc),
                "query": query,
                "path": scope,
                "repo_root": str(repo_root),
                "db": str(db),
                "reindex_mode": "delta",
                "reindex_source": "git",
            }
            return _write_result(root, payload)

    try:
        matches, ranking = _query_rag_db(
            db=db,
            repo_root=repo_root,
            query=query,
            scope=scope,
            limit=limit,
            candidate_limit=candidate_limit,
            preview_chars=preview_chars,
            rerank_enabled=_bool_arg(args, "rerank", default=True),
            rerank_candidate_limit=rerank_candidate_limit,
            rerank_doc_chars=rerank_doc_chars,
            rerank_timeout_seconds=rerank_timeout_seconds,
        )
    except Exception:
                
        payload = {
            "ok": False,
            "tool": TOOL,
            "error": "rag_query_failed",
            "error_type": type(exc).__name__,
            "detail": str(exc),
            "query": query,
            "path": scope,
            "repo_root": str(repo_root),
            "db": str(db),
        }
        return _write_result(root, payload)

    paths: list[str] = []
    for item in matches:
        path = str(item.get("path") or "")
        if path and path not in paths:
            paths.append(path)

    payload = {
        "ok": True,
        "tool": TOOL,
        "query": query,
        "path": scope,
        "repo_root": str(repo_root),
        "db": str(db),
        "reindex": reindex,
        "ranking": ranking,
        "warnings": ranking.get("warnings") if isinstance(ranking.get("warnings"), list) else [],
        "limit": limit,
        "candidate_limit": candidate_limit,
        "count": len(matches),
        "paths": paths,
        "matches": matches,
        "truncated": int(ranking.get("raw_match_count") or 0) > len(matches),
        "suggested_next_tool": "repo_read" if paths else "",
        "suggested_repo_read": {"paths": paths, "max_chars": min(max(preview_chars * max(len(paths), 1), 4000), 24000)}
        if paths
        else {},
    }
    return _write_result(root, payload)
