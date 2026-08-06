"""
planner_intrinsic_context
=========================
Controller-built context injected before each planner turn.

This module is not a planner tool surface. It reads already available memory
and optional RAG SQLite/FTS5 chunks, bounds them, and returns one structured
payload that the planner receives before deciding whether a selective memory
tool call is still needed.
"""
from __future__ import annotations

import json
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


SCHEMA = "planner_intrinsic_context.v1"
DEFAULT_FTS_CANDIDATE_LIMIT = 80
DEFAULT_RERANK_CANDIDATE_LIMIT = 12
DEFAULT_RERANK_DOC_CHARS = 2500
DEFAULT_RERANK_RESPONSE_BYTES = 2_000_000

TOOL_PURPOSE_MANIFEST: tuple[dict[str, Any], ...] = (
    {
        "name": "repo_propose_code_edit",
        "purpose": "only report-only tool for diff/proposal/refactoring code products",
        "writes_source": False,
        "requires": "repo_read target first; complete unified_diff, structured_operations, or explicit no_op rationale",
    },
    {
        "name": "repo_apply_patch",
        "purpose": "apply/edit/fix/write goals only",
        "writes_source": True,
        "requires": "explicit apply intent and exact prior source evidence",
    },
    {
        "name": "ast-grep",
        "purpose": "deterministic AST search/rewrite evidence and codemod dry-run",
        "writes_source": False,
        "policy": "support evidence only; never direct apply without explicit apply goal",
    },
    {
        "name": "repo_fd_files / repo_rg_search / repo_jq_query",
        "purpose": "deterministic file discovery, text search and JSON query evidence",
        "writes_source": False,
        "policy": "turn-scoped repo inspection only; payloads are bounded and structured",
    },
    {
        "name": "repo_ast_grep_search / repo_ast_grep_dry_run",
        "purpose": "deterministic AST search/rewrite evidence and codemod dry-run",
        "writes_source": False,
        "policy": "dry-run/evidence only; generated operations or diffs must still be explicit payloads",
    },
    {
        "name": "Tree-sitter",
        "purpose": "deterministic tree-sitter parsing evidence",
        "writes_source": False,
        "policy": "parse errors are typed blockers, not text heuristics",
    },
    {
        "name": "repo_tree_sitter_parse / repo_ctags_symbols",
        "purpose": "tree-sitter parsing and ctags symbol evidence",
        "writes_source": False,
        "policy": "anchors support planner decisions; they do not replace repo_read evidence",
    },
    {
        "name": "unidiff/difflib",
        "purpose": "unified diff evidence",
        "writes_source": False,
        "policy": "complete diff payload is evidence; previews and artifact paths are not",
    },
    {
        "name": "git apply --check",
        "purpose": "validate patch application without actually applying it",
        "writes_source": False,
    },
    {
        "name": "repo_unidiff_validate / repo_git_apply_check",
        "purpose": "validate unified diff payloads",
        "writes_source": False,
        "policy": "validation output is evidence; source writes remain prohibited in report-only lanes",
    },
    {
        "name": "repo_ruff_check / repo_pyright_check / repo_pytest_run",
        "purpose": "validate code quality and correctness",
        "writes_source": False,
        "policy": "only exposed for validation/apply or relevant analysis turns; not a generic escape route",
    },
    {
        "name": "repo_shellcheck / repo_semgrep_scan",
        "purpose": "validate shell scripts and scan for security issues",
        "writes_source": False,
        "policy": "only exposed when the request or controller context makes the check relevant",
    },
    {
        "name": "repo_hyperfine_benchmark",
        "purpose": "benchmark code performance",
        "writes_source": False,
        "policy": "guarded tool; requires explicit benchmark intent and command consent",
    },
    {
        "name": "terminal_run_command_wait / Open Terminal",
        "purpose": "run terminal commands and wait for completion",
        "writes_source": "only when the explicit command writes; prefer read-only validation",
    },
    {
        "name": "SQLite/FTS5/RAG/chunks",
        "purpose": "intrinsic pre-turn context substrate",
        "planner_tool": False,
        "policy": "planner may call runtime_sqlite_memory_* only after a concrete gap remains",
    },
    {
        "name": "external RAG reranker",
        "purpose": "rerank documents based on external RAG model",
        "planner_tool": False,
        "policy": "if unavailable, intrinsic_context must say so explicitly; do not expose as planner action",
    },
)


class ExternalRerankerHTTPError(RuntimeError):
    """Typed HTTP error from the optional external reranker."""

    def __init__(self, *, status: int, reason: str, body_preview: str) -> None:
        super().__init__(f"external reranker HTTP {status}: {reason}")
        self.status = status
        self.reason = reason
        self.body_preview = body_preview


def _compact_text(value: Any, limit: int) -> tuple[str, bool]:
    text = str(value or "")
    if limit <= 0 or len(text) <= limit:
        return text, False
    return text[:limit], True


def _json_chars(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str))


def _goal_tokens(goal: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9_./:-]{2,}", str(goal or "").lower())
    out: list[str] = []
    for token in tokens:
        if token not in out:
            out.append(token)
        if len(out) >= 24:
            break
    return out


def _fts_query(goal: str) -> str:
    tokens = _goal_tokens(goal)
    if not tokens:
        return ""
    return " OR ".join(f'"{token.replace(chr(34), chr(34) + chr(34))}"' for token in tokens)


def _sqlite_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _http_json(method: str, url: str, payload: Any | None = None, timeout: float = 20.0) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    request = urllib.request.Request(str(url), data=data, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=max(0.1, float(timeout or 0.1))) as response:
            raw = response.read(DEFAULT_RERANK_RESPONSE_BYTES)
            text = raw.decode("utf-8", errors="replace")
            status = getattr(response, "status", None)
            content_type = (response.headers.get("Content-Type") or "").lower()
    except urllib.error.HTTPError as exc:
        raw = exc.read(DEFAULT_RERANK_RESPONSE_BYTES)
        text = raw.decode("utf-8", errors="replace")
        raise ExternalRerankerHTTPError(
            status=int(exc.code or 0),
            reason=str(exc.reason or exc),
            body_preview=text[:2000],
        ) from exc
    if not text.strip():
        return {"status": status}
    if "application/json" in content_type or text.strip().startswith(("{", "[")):
        return json.loads(text)
    return {
        "status": status,
        "content_type": content_type,
        "text": text[:2000],
        "non_json_response": True,
    }


def _rerank_payload_documents(items: list[dict[str, Any]], doc_chars: int) -> list[str]:
    limit = max(1, int(doc_chars or DEFAULT_RERANK_DOC_CHARS))
    return [str(item.get("text") or "")[:limit] for item in items]


def _rerank_order_from_response(response: Any, item_count: int) -> list[tuple[int, float]]:
    if isinstance(response, dict):
        candidates = response.get("results")
        if not isinstance(candidates, list):
            candidates = response.get("data")
    elif isinstance(response, list):
        candidates = response
    else:
        candidates = None

    order: list[tuple[int, float]] = []
    if isinstance(candidates, list):
        for fallback_index, item in enumerate(candidates):
            if not isinstance(item, dict):
                continue
            raw_index = item.get("index", item.get("document_index", item.get("id", fallback_index)))
            try:
                index = int(raw_index)
            except Exception:
                index = fallback_index
            score = item.get("relevance_score", item.get("score", item.get("logit", item.get("rerank_score", 0.0))))
            try:
                score_float = float(score)
            except Exception:
                score_float = 0.0
            if 0 <= index < item_count:
                order.append((index, score_float))

    scores = response.get("scores") if isinstance(response, dict) else None
    if not order and isinstance(scores, list):
        for index, score in enumerate(scores[:item_count]):
            try:
                order.append((index, float(score)))
            except Exception:
                order.append((index, 0.0))
    return order


def _items_with_missing_rerank_scores(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        merged = dict(item)
        merged.setdefault("rerank_score", None)
        out.append(merged)
    return out


def _external_rerank_items(
    *,
    goal: str,
    items: list[dict[str, Any]],
    engine: str,
    url: str,
    model: str,
    timeout_seconds: float,
    candidate_limit: int = DEFAULT_RERANK_CANDIDATE_LIMIT,
    doc_chars: int = DEFAULT_RERANK_DOC_CHARS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    enabled = str(engine or "").lower() == "external"
    limit = max(1, int(candidate_limit or DEFAULT_RERANK_CANDIDATE_LIMIT))
    document_chars = max(1, int(doc_chars or DEFAULT_RERANK_DOC_CHARS))
    rerank: dict[str, Any] = {
        "enabled": enabled,
        "engine": str(engine or ""),
        "url": str(url or ""),
        "model": str(model or ""),
        "candidate_limit": limit,
        "doc_chars": document_chars,
        "timeout_seconds": float(timeout_seconds or 0.0),
        "candidate_count": len(items),
        "input_count": 0,
        "status": "not_started",
    }
    if not items:
        rerank["status"] = "skipped_no_items"
        return items, rerank
    if not enabled:
        rerank["status"] = "skipped_disabled"
        return items, rerank
    if not str(url or "").strip():
        rerank.update({"status": "unavailable", "error": "external_reranker_url_missing"})
        return _items_with_missing_rerank_scores(items), rerank

    rerank_candidates = items[:limit]
    documents = _rerank_payload_documents(rerank_candidates, document_chars)
    rerank["input_count"] = len(documents)
    body = {
        "model": str(model or "BAAI/bge-reranker-v2-m3"),
        "query": str(goal or ""),
        "documents": documents,
    }
    try:
        decoded = _http_json("POST", str(url), body, timeout=float(timeout_seconds or 0.1))
    except ExternalRerankerHTTPError as exc:
        http_status = int(exc.status or 0)
        status = "unavailable" if http_status == 429 or http_status >= 500 else "error"
        rerank.update({
            "status": status,
            "error": "external_reranker_http_error",
            "details": f"http_{http_status}",
            "http_status": http_status,
            "http_reason": exc.reason[:200],
            "body_preview": exc.body_preview[:1000],
        })
        return _items_with_missing_rerank_scores(items), rerank
    except TimeoutError as exc:
        rerank.update({
            "status": "unavailable",
            "error": "external_reranker_timeout",
            "details": type(exc).__name__,
        })
        return _items_with_missing_rerank_scores(items), rerank
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        error_name = "external_reranker_timeout" if isinstance(reason, TimeoutError) else "external_reranker_unavailable"
        rerank.update({
            "status": "unavailable",
            "error": error_name,
            "details": type(reason).__name__ if reason is not None else type(exc).__name__,
        })
        return _items_with_missing_rerank_scores(items), rerank
    except json.JSONDecodeError as exc:
        rerank.update({
            "status": "error",
            "error": "external_reranker_invalid_json",
            "details": type(exc).__name__,
            "json_error": str(exc)[:300],
        })
        return _items_with_missing_rerank_scores(items), rerank
    except (OSError, ValueError) as exc:
        rerank.update({"status": "unavailable", "error": "external_reranker_unavailable", "details": type(exc).__name__})
        return _items_with_missing_rerank_scores(items), rerank
    except Exception as exc:
        rerank.update({"status": "error", "error": "external_reranker_response_error", "details": type(exc).__name__})
        return _items_with_missing_rerank_scores(items), rerank

    if isinstance(decoded, dict) and decoded.get("non_json_response"):
        rerank.update({
            "status": "error",
            "error": "external_reranker_non_json_response",
            "http_status": decoded.get("status"),
            "content_type": decoded.get("content_type"),
            "body_preview": str(decoded.get("text") or "")[:1000],
        })
        return _items_with_missing_rerank_scores(items), rerank

    order = _rerank_order_from_response(decoded, len(rerank_candidates))
    if not order:
        rerank.update({
            "status": "error",
            "error": "external_reranker_no_scores",
            "response_shape": type(decoded).__name__,
        })
        return _items_with_missing_rerank_scores(items), rerank

    seen: set[int] = set()
    ranked: list[dict[str, Any]] = []
    for index, score in order:
        if index in seen:
            continue
        seen.add(index)
        item = dict(rerank_candidates[index])
        item["rerank_score"] = score
        item["rerank_rank"] = len(ranked) + 1
        item["reason"] = "external_rerank_after_fts_match"
        ranked.append(item)

    for index, item in enumerate(rerank_candidates):
        if index not in seen:
            merged = dict(item)
            merged["rerank_score"] = None
            ranked.append(merged)
    for item in items[limit:]:
        merged = dict(item)
        merged["rerank_score"] = None
        ranked.append(merged)

    rerank.update(
        {
            "status": "ready",
            "returned_scores": len(order),
            "ranked_count": len(ranked),
            "ranking_source": "external_rerank",
        }
    )
    return ranked, rerank


def _rag_sqlite_chunks(
    *,
    goal: str,
    db_path: Path,
    top_k: int,
    char_budget: int,
    rerank_engine: str,
    rerank_url: str,
    rerank_model: str,
    rerank_timeout_seconds: float,
) -> dict[str, Any]:
    db = db_path.resolve(strict=False)
    base: dict[str, Any] = {
        "source": "sqlite_fts5_rag",
        "db": str(db),
        "status": "missing",
        "count": 0,
        "items": [],
        "ranking_source": "none",
        "rerank": {
            "engine": str(rerank_engine or ""),
            "url": str(rerank_url or ""),
            "model": str(rerank_model or ""),
            "status": "not_attempted",
        },
    }
    if not db.exists():
        base["gap"] = "rag_sqlite_missing"
        return base

    query = _fts_query(goal)
    if not query:
        base.update({"status": "empty_query", "gap": "rag_query_empty"})
        return base

    output_limit = max(1, min(int(top_k or 1), 30))
    candidate_limit = max(output_limit, DEFAULT_FTS_CANDIDATE_LIMIT)

    try:
        conn = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except Exception as exc:
        base.update({"status": "error", "error": "rag_sqlite_open_failed", "details": type(exc).__name__})
        return base

    try:
        tables = _sqlite_tables(conn)
        if "rag_chunks" not in tables or "rag_chunks_fts" not in tables:
            base.update(
                {
                    "status": "schema_missing",
                    "gap": "rag_sqlite_schema_missing",
                    "tables_seen": sorted(tables)[:40],
                }
            )
            return base
        rows = conn.execute(
            """
            SELECT c.chunk_id, c.source_path, c.chunk_index, c.char_start, c.char_end,
                   c.text, c.text_hash, bm25(rag_chunks_fts) AS bm25
            FROM rag_chunks_fts
            JOIN rag_chunks AS c ON c.chunk_id = rag_chunks_fts.chunk_id
            WHERE rag_chunks_fts MATCH ? AND c.active = 1
            ORDER BY bm25(rag_chunks_fts)
            LIMIT ?
            """,
            (query, candidate_limit),
        ).fetchall()
    except sqlite3.Error as exc:
        base.update(
            {
                "status": "error",
                "error": "rag_sqlite_query_error",
                "details": type(exc).__name__,
                "query": query,
            }
        )
        return base
    finally:
        conn.close()

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        row_dict = dict(row)
        chunk_id = str(row_dict.get("chunk_id") or "")
        if chunk_id and chunk_id in seen:
            continue
        if chunk_id:
            seen.add(chunk_id)
        text, truncated = _compact_text(row_dict.get("text"), DEFAULT_RERANK_DOC_CHARS)
        candidates.append(
            {
                "path": str(row_dict.get("source_path") or ""),
                "source": "rag.sqlite",
                "reason": "fts_match_for_current_goal",
                "score": row_dict.get("bm25"),
                "chars": len(text),
                "truncated": truncated,
                "chunk_id": chunk_id,
                "chunk_index": row_dict.get("chunk_index"),
                "char_start": row_dict.get("char_start"),
                "char_end": row_dict.get("char_end"),
                "text_hash": row_dict.get("text_hash"),
                "text": text,
            }
        )

    ranked_candidates, rerank = _external_rerank_items(
        goal=goal,
        items=candidates,
        engine=rerank_engine,
        url=rerank_url,
        model=rerank_model,
        timeout_seconds=rerank_timeout_seconds,
        candidate_limit=DEFAULT_RERANK_CANDIDATE_LIMIT,
        doc_chars=DEFAULT_RERANK_DOC_CHARS,
    )
    ranking_source = "external_rerank" if rerank.get("status") == "ready" else "fts_only"
    if rerank.get("status") == "unavailable":
        ranking_source = "fts_only_rerank_unavailable"

    remaining = max(0, int(char_budget or 0))
    items: list[dict[str, Any]] = []
    for item in ranked_candidates:
        if len(items) >= output_limit:
            break
        if remaining <= 0:
            break
        per_item_limit = max(300, min(1600, remaining))
        text, truncated = _compact_text(item.get("text"), per_item_limit)
        remaining -= len(text)
        bounded_item = dict(item)
        bounded_item["chars"] = len(text)
        bounded_item["text"] = text
        bounded_item["truncated"] = bool(item.get("truncated") or truncated)
        items.append(bounded_item)

    base.update(
        {
            "status": "ready",
            "query": query,
            "count": len(items),
            "items": items,
            "char_budget": int(char_budget or 0),
            "candidate_count": len(candidates),
            "ranking_source": ranking_source,
            "rerank": rerank,
        }
    )
    if not items:
        base["gap"] = "rag_no_relevant_chunks"
    return base


def _memory_items(planner_memory: dict[str, Any], limit: int = 8) -> dict[str, Any]:
    surface = planner_memory if isinstance(planner_memory, dict) else {}
    raw_records = surface.get("records")
    raw_items: list[Any] = raw_records if isinstance(raw_records, list) else []
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("content") or item.get("note") or "")
        row_id = str(item.get("id") or item.get("record_id") or item.get("created_at") or text)
        if row_id in seen:
            continue
        seen.add(row_id)
        compact, truncated = _compact_text(text, 900)
        items.append(
            {
                "path": str(item.get("tag") or item.get("kind") or "runtime_sqlite_memory"),
                "source": "planner_memory_surface",
                "reason": "controller_injected_relevant_memory",
                "score": item.get("score"),
                "chars": len(compact),
                "truncated": truncated,
                "kind": item.get("kind"),
                "tag": item.get("tag"),
                "text": compact,
            }
        )
        if len(items) >= limit:
            break
    return {
        "source": surface.get("source") or "planner_memory_surface",
        "available": bool(surface.get("available", True)),
        "record_count": int(surface.get("record_count") or len(raw_items)),
        "count": len(items),
        "items": items,
        "policy": "use these records first; call runtime_sqlite_memory_search/write only for a concrete selective gap after intrinsic_context",
    }


def _repo_map_summary(evidence_contract: dict[str, Any]) -> dict[str, Any]:
    contract = evidence_contract if isinstance(evidence_contract, dict) else {}
    return {
        "source": "planner_evidence_contract",
        "target_kind": contract.get("target_kind"),
        "resolved_goal_file": contract.get("resolved_goal_file"),
        "resolved_goal_scope": contract.get("resolved_goal_scope"),
        "known_paths_total": contract.get("known_paths_total_in_latest_digest"),
        "known_paths_sample": (contract.get("known_paths_from_latest_repo_list_files") or [])[:30],
        "verified_read_count": contract.get("verified_content_read_count"),
        "verified_reads": (contract.get("verified_content_reads") or [])[:20],
        "ranked_core_candidate_dirs": (contract.get("ranked_core_candidate_dirs") or [])[:8],
    }


def _failure_patterns(evidence_contract: dict[str, Any]) -> list[dict[str, Any]]:
    contract = evidence_contract if isinstance(evidence_contract, dict) else {}
    patterns: list[dict[str, Any]] = []
    raw_code_contract = contract.get("code_product_contract")
    code_contract: dict[str, Any] = raw_code_contract if isinstance(raw_code_contract, dict) else {}
    raw_violations = code_contract.get("latest_violations")
    violations: list[Any] = raw_violations if isinstance(raw_violations, list) else []
    if code_contract.get("required") and "missing_code_product_candidate" in violations:
        patterns.append(
            {
                "pattern": "code_product_goal_final_without_proposal",
                "source": "evidence_contract",
                "reason": "code-product final is blocked until repo_propose_code_edit ok=true",
                "required_next_action": "repo_propose_code_edit",
            }
        )
    raw_validation_rows = contract.get("validation_rejections_tail")
    validation_rows: list[Any] = raw_validation_rows if isinstance(raw_validation_rows, list) else []
    for row in validation_rows:
        if not isinstance(row, dict):
            continue
        row_violations = row.get("violations") if isinstance(row.get("violations"), list) else []
        if row_violations:
            patterns.append(
                {
                    "pattern": "recent_validator_rejection",
                    "source": "validation_rejections_tail",
                    "reason": ", ".join(str(v) for v in row_violations[:6]),
                    "step": row.get("step"),
                    "next_instruction": row.get("next_instruction"),
                }
            )
        if len(patterns) >= 8:
            break
    return patterns


def _enforce_budget(context: dict[str, Any], max_chars: int) -> None:
    if max_chars <= 0 or _json_chars(context) <= max_chars:
        return
    for section_name in ("retrieved_rag_chunks", "retrieved_memory"):
        section_value = context.get(section_name)
        section: dict[str, Any] = section_value if isinstance(section_value, dict) else {}
        raw_items = section.get("items")
        section_items: list[Any] = raw_items if isinstance(raw_items, list) else []
        for item in section_items:
            if not isinstance(item, dict) or "text" not in item:
                continue
            item["text"], item["truncated"] = _compact_text(item.get("text"), 500)
            item["chars"] = len(str(item.get("text") or ""))
    if _json_chars(context) <= max_chars:
        return
    rag_value = context.get("retrieved_rag_chunks")
    rag: dict[str, Any] = rag_value if isinstance(rag_value, dict) else {}
    rag_items = rag.get("items")
    if isinstance(rag_items, list):
        trimmed_items = rag_items[:3]
        rag["items"] = trimmed_items
        rag["budget_trimmed"] = True
        rag["count"] = len(trimmed_items)


def build_planner_intrinsic_context(
    *,
    goal: str,
    history: list[dict[str, Any]],
    evidence_contract: dict[str, Any],
    planner_memory: dict[str, Any],
    rag_db: Path,
    num_ctx: int,
    max_chars: int,
    rag_top_k: int,
    rag_char_budget: int,
    rerank_engine: str = "",
    rerank_url: str = "",
    rerank_model: str = "",
    rerank_timeout_seconds: float = 2.0,
    rag_embedding_batch_size: int = 4,
) -> dict[str, Any]:
    contract = evidence_contract if isinstance(evidence_contract, dict) else {}
    goal_classification = {
        "semantic_goal_classification": contract.get("semantic_goal_classification")
        if isinstance(contract.get("semantic_goal_classification"), dict) else {},
        "goal_requests_code_product": bool(contract.get("goal_requests_code_product")),
        "goal_requires_code_product_report": bool(contract.get("goal_requires_code_product_report")),
        "goal_requests_apply": bool(contract.get("goal_requests_apply")),
        "code_product_required": bool((contract.get("code_product_contract") or {}).get("required"))
        if isinstance(contract.get("code_product_contract"), dict) else False,
        "target_kind": contract.get("target_kind"),
        "resolved_goal_file": contract.get("resolved_goal_file"),
        "resolved_goal_scope": contract.get("resolved_goal_scope"),
        "history_count": len(history if isinstance(history, list) else []),
    }
    context: dict[str, Any] = {
        "schema": SCHEMA,
        "goal_classification": goal_classification,
        "retrieved_memory": _memory_items(planner_memory),
        "retrieved_rag_chunks": _rag_sqlite_chunks(
            goal=goal,
            db_path=rag_db,
            top_k=rag_top_k,
            char_budget=rag_char_budget,
            rerank_engine=rerank_engine,
            rerank_url=rerank_url,
            rerank_model=rerank_model,
            rerank_timeout_seconds=rerank_timeout_seconds,
        ),
        "repo_map_summary": _repo_map_summary(contract),
        "failure_patterns": _failure_patterns(contract),
        "tool_purpose_manifest": list(TOOL_PURPOSE_MANIFEST),
        "budget_report": {
            "num_ctx_effective": int(num_ctx or 0),
            "max_chars": int(max_chars or 0),
            "rag_top_k": int(rag_top_k or 0),
            "rag_char_budget": int(rag_char_budget or 0),
            "rag_reranking_engine": str(rerank_engine or ""),
            "rag_external_reranker_url": str(rerank_url or ""),
            "rag_reranking_model": str(rerank_model or ""),
            "rag_embedding_batch_size": int(rag_embedding_batch_size or 0),
            "bounded": True,
        },
    }
    _enforce_budget(context, int(max_chars or 0))
    context["budget_report"]["intrinsic_context_chars"] = _json_chars(context)
    context["budget_report"]["over_budget_after_trim"] = (
        int(max_chars or 0) > 0 and context["budget_report"]["intrinsic_context_chars"] > int(max_chars or 0)
    )
    return context
