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
        "name": "Tree-sitter",
        "purpose": "parse and anchor files structurally before proposing edits",
        "writes_source": False,
        "policy": "parse errors are typed blockers, not text heuristics",
    },
    {
        "name": "unidiff/difflib",
        "purpose": "parse or generate complete unified diffs",
        "writes_source": False,
        "policy": "complete diff payload is evidence; previews and artifact paths are not",
    },
    {
        "name": "git apply --check",
        "purpose": "validate patch applicability without applying it",
        "writes_source": False,
    },
    {
        "name": "terminal_run_command_wait / Open Terminal",
        "purpose": "targeted diagnostics and validations under the project shell",
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
        "purpose": "optional internal rerank of retrieved RAG chunks before planner prompt injection",
        "planner_tool": False,
        "policy": "if unavailable, intrinsic_context must say so explicitly; do not expose as planner action",
    },
)


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


def _rerank_payload_documents(items: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("text") or "") for item in items]


def _rerank_order_from_response(response: dict[str, Any], item_count: int) -> list[tuple[int, float]]:
    candidates = response.get("results")
    if not isinstance(candidates, list):
        candidates = response.get("data")
    order: list[tuple[int, float]] = []
    if isinstance(candidates, list):
        for fallback_index, item in enumerate(candidates):
            if not isinstance(item, dict):
                continue
            raw_index = item.get("index", item.get("document_index", item.get("id", fallback_index)))
            try:
                index = int(raw_index)
            except Exception:
                continue
            score = item.get("relevance_score", item.get("score", item.get("rerank_score", 0.0)))
            try:
                score_float = float(score)
            except Exception:
                score_float = 0.0
            if 0 <= index < item_count:
                order.append((index, score_float))
    scores = response.get("scores")
    if not order and isinstance(scores, list):
        for index, score in enumerate(scores[:item_count]):
            try:
                order.append((index, float(score)))
            except Exception:
                order.append((index, 0.0))
    return order


def _external_rerank_items(
    *,
    goal: str,
    items: list[dict[str, Any]],
    engine: str,
    url: str,
    model: str,
    timeout_seconds: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rerank: dict[str, Any] = {
        "engine": str(engine or ""),
        "url": str(url or ""),
        "model": str(model or ""),
        "status": "disabled",
    }
    if not items:
        rerank["status"] = "skipped_no_items"
        return items, rerank
    if str(engine or "").lower() != "external":
        return items, rerank
    if not str(url or "").strip():
        rerank.update({"status": "unavailable", "error": "external_reranker_url_missing"})
        return items, rerank

    documents = _rerank_payload_documents(items)
    body = {
        "model": str(model or "BAAI/bge-reranker-v2-m3"),
        "query": str(goal or ""),
        "documents": documents,
        "top_n": len(documents),
    }
    request = urllib.request.Request(
        str(url),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=max(0.1, float(timeout_seconds or 0.1))) as response:
            raw = response.read(2_000_000)
        decoded = json.loads(raw.decode("utf-8", errors="replace"))
    except (TimeoutError, urllib.error.URLError, OSError) as exc:
        rerank.update({"status": "unavailable", "error": "external_reranker_unavailable", "details": type(exc).__name__})
        return items, rerank
    except Exception as exc:
        rerank.update({"status": "error", "error": "external_reranker_response_error", "details": type(exc).__name__})
        return items, rerank

    if not isinstance(decoded, dict):
        rerank.update({"status": "error", "error": "external_reranker_response_not_object"})
        return items, rerank
    order = _rerank_order_from_response(decoded, len(items))
    if not order:
        rerank.update({"status": "error", "error": "external_reranker_no_scores"})
        return items, rerank

    ordered_indices = [index for index, _score in sorted(order, key=lambda pair: -pair[1])]
    seen: set[int] = set()
    ranked: list[dict[str, Any]] = []
    for rank, index in enumerate(ordered_indices, start=1):
        if index in seen:
            continue
        seen.add(index)
        item = dict(items[index])
        score = next((score for idx, score in order if idx == index), None)
        item["rerank_score"] = score
        item["rerank_rank"] = rank
        item["reason"] = "external_rerank_after_fts_match"
        ranked.append(item)
    for index, item in enumerate(items):
        if index not in seen:
            ranked.append(item)
    rerank.update({"status": "ready", "returned_scores": len(order), "ranking_source": "external_rerank"})
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
            (query, max(1, min(int(top_k or 1), 30))),
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

    remaining = max(0, int(char_budget or 0))
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        row_dict = dict(row)
        chunk_id = str(row_dict.get("chunk_id") or "")
        if chunk_id and chunk_id in seen:
            continue
        if chunk_id:
            seen.add(chunk_id)
        if remaining <= 0:
            break
        per_item_limit = max(300, min(1600, remaining))
        text, truncated = _compact_text(row_dict.get("text"), per_item_limit)
        remaining -= len(text)
        items.append(
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

    items, rerank = _external_rerank_items(
        goal=goal,
        items=items,
        engine=rerank_engine,
        url=rerank_url,
        model=rerank_model,
        timeout_seconds=rerank_timeout_seconds,
    )
    ranking_source = "external_rerank" if rerank.get("status") == "ready" else "fts_only"
    if rerank.get("status") == "unavailable":
        ranking_source = "fts_only_rerank_unavailable"

    base.update(
        {
            "status": "ready",
            "query": query,
            "count": len(items),
            "items": items,
            "char_budget": int(char_budget or 0),
            "ranking_source": ranking_source,
            "rerank": rerank,
        }
    )
    if not items:
        base["gap"] = "rag_no_relevant_chunks"
    return base


def _memory_items(planner_memory: dict[str, Any], limit: int = 8) -> dict[str, Any]:
    surface = planner_memory if isinstance(planner_memory, dict) else {}
    raw_items = surface.get("records") if isinstance(surface.get("records"), list) else []
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
    code_contract = contract.get("code_product_contract") if isinstance(contract.get("code_product_contract"), dict) else {}
    violations = code_contract.get("latest_violations") if isinstance(code_contract.get("latest_violations"), list) else []
    if code_contract.get("required") and "missing_code_product_candidate" in violations:
        patterns.append(
            {
                "pattern": "code_product_goal_final_without_proposal",
                "source": "evidence_contract",
                "reason": "code-product final is blocked until repo_propose_code_edit ok=true",
                "required_next_action": "repo_propose_code_edit",
            }
        )
    for row in contract.get("validation_rejections_tail") or []:
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
        section = context.get(section_name) if isinstance(context.get(section_name), dict) else {}
        for item in section.get("items") or []:
            if not isinstance(item, dict) or "text" not in item:
                continue
            item["text"], item["truncated"] = _compact_text(item.get("text"), 500)
            item["chars"] = len(str(item.get("text") or ""))
    if _json_chars(context) <= max_chars:
        return
    rag = context.get("retrieved_rag_chunks") if isinstance(context.get("retrieved_rag_chunks"), dict) else {}
    if isinstance(rag.get("items"), list):
        rag["items"] = rag["items"][:3]
        rag["budget_trimmed"] = True
        rag["count"] = len(rag["items"])


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
