"""Core discovery candidate helpers built from intrinsic and repo evidence."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..shared.path_tokens import repo_rel_token
from .user_scope_claims import scope_claim_conflict_for_path


PathUnderScope = Callable[[str, str], bool]
PathExists = Callable[[str], bool]
ReadableEvidenceFile = Callable[[str], bool]
ScopeReadCandidates = Callable[[list[dict[str, Any]], str, set[str]], list[str]]
MeaningfulReadCandidates = Callable[[list[dict[str, Any]], set[str]], list[str]]


def add_core_discovery_candidate(
    out: list[dict[str, Any]],
    seen: set[str],
    *,
    path: str,
    source: str,
    rank: int,
    reason: str,
    read_ok: set[str],
    target_scope: str,
    user_scope_claims: list[dict[str, Any]],
    lab_repo_label: str,
    path_under_scope: PathUnderScope,
    path_exists_repo_relative: PathExists,
    repo_readable_evidence_file: ReadableEvidenceFile,
    score: Any = None,
    ranking_source: str = "",
) -> bool:
    p = repo_rel_token(path)
    if not p or p == "." or p in seen or p in read_ok:
        return False
    if target_scope and not path_under_scope(p, target_scope):
        return False
    if not path_exists_repo_relative(p) or not repo_readable_evidence_file(p):
        return False
    seen.add(p)
    conflict = scope_claim_conflict_for_path(p, user_scope_claims)
    candidate = {
        "path": p,
        "next_tool": "repo_read",
        "source": source,
        "rank": rank,
        "reason": reason,
        "lab_repo": lab_repo_label,
        "claim_conflict": bool(conflict),
    }
    if ranking_source:
        candidate["ranking_source"] = ranking_source
    if score is not None:
        candidate["score"] = score
    if conflict:
        candidate["conflicting_user_scope_claim"] = conflict
        candidate["required_after_read"] = (
            "If patching this target, rationale must explain why read content proves it is core."
        )
    out.append(candidate)
    return True


def core_discovery_candidates_from_intrinsic(
    *,
    intrinsic_context: dict[str, Any] | None,
    list_rows: list[dict[str, Any]],
    read_ok: list[str],
    target_scope: str,
    user_scope_claims: list[dict[str, Any]],
    lab_repo_label: str,
    path_under_scope: PathUnderScope,
    path_exists_repo_relative: PathExists,
    repo_readable_evidence_file: ReadableEvidenceFile,
    scope_read_candidates_from_evidence: ScopeReadCandidates,
    meaningful_read_candidates_from_evidence: MeaningfulReadCandidates,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    already = {repo_rel_token(path) for path in read_ok}
    status: dict[str, Any] = {
        "schema": "core_discovery_status.v1",
        "lab_repo": lab_repo_label,
        "discovery_only": True,
        "patch_authorized_by_ranking": False,
        "source": "none",
        "rebuild_performed": False,
    }
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    rag = (
        intrinsic_context.get("retrieved_rag_chunks")
        if isinstance(intrinsic_context, dict)
        and isinstance(intrinsic_context.get("retrieved_rag_chunks"), dict)
        else {}
    )
    rag_items = rag.get("items") if isinstance(rag.get("items"), list) else []
    ranking_source = str(rag.get("ranking_source") or "")
    stale_or_unusable = 0
    intrinsic_rag_status = str(rag.get("status") or "") if rag else "not_populated"
    status.update({
        "rag_status": intrinsic_rag_status,
        "rag_status_scope": "intrinsic_context.retrieved_rag_chunks",
        "intrinsic_context_rag_status": intrinsic_rag_status,
        "intrinsic_context_rag_status_scope": "intrinsic_context.retrieved_rag_chunks",
        "rag_ranking_source": ranking_source or None,
        "rag_item_count": len(rag_items),
        "repo_semantic_search_available_as_planner_tool": True,
        "global_rag_status_not_represented_here": True,
    })
    for rank, item in enumerate(rag_items, start=1):
        if not isinstance(item, dict):
            continue
        path = repo_rel_token(item.get("path") or item.get("source_path") or "")
        before_count = len(candidates)
        added = add_core_discovery_candidate(
            candidates,
            seen,
            path=path,
            source="retrieved_rag_chunks",
            rank=rank,
            reason="RAG/FTS/rerank candidate under current LAB_REPO; read before deciding patch target.",
            read_ok=already,
            target_scope=target_scope,
            user_scope_claims=user_scope_claims,
            lab_repo_label=lab_repo_label,
            path_under_scope=path_under_scope,
            path_exists_repo_relative=path_exists_repo_relative,
            repo_readable_evidence_file=repo_readable_evidence_file,
            score=item.get("rerank_score", item.get("score")),
            ranking_source=ranking_source,
        )
        if not added and path and len(candidates) == before_count:
            stale_or_unusable += 1
    if candidates:
        status["source"] = "rag_current_lab_repo"
        status["rag_stale_or_unusable_count"] = stale_or_unusable
        return candidates[:16], status

    rebuilt_paths = (
        scope_read_candidates_from_evidence(list_rows, target_scope, already)
        if target_scope else
        meaningful_read_candidates_from_evidence(list_rows, already)
    )
    for rank, path in enumerate(rebuilt_paths[:16], start=1):
        add_core_discovery_candidate(
            candidates,
            seen,
            path=path,
            source="lab_repo_evidence_rebuild",
            rank=rank,
            reason="Runtime ranking rebuilt from current LAB_REPO list evidence.",
            read_ok=already,
            target_scope=target_scope,
            user_scope_claims=user_scope_claims,
            lab_repo_label=lab_repo_label,
            path_under_scope=path_under_scope,
            path_exists_repo_relative=path_exists_repo_relative,
            repo_readable_evidence_file=repo_readable_evidence_file,
            ranking_source="current_lab_repo_evidence",
        )
    if candidates:
        status["source"] = "ranking_rebuilt_from_lab_repo_evidence"
        status["rebuild_performed"] = bool(rag_items or stale_or_unusable or (rag and rag.get("status") != "ready"))
        status["rag_stale_or_unusable_count"] = stale_or_unusable
        status["reason"] = (
            "RAG ranking was missing or did not yield usable files under current LAB_REPO; "
            "candidate ranking rebuilt from current repo evidence."
        )
    else:
        status["source"] = "no_current_lab_repo_candidates"
        status["rag_stale_or_unusable_count"] = stale_or_unusable
    return candidates[:16], status


def core_discovery_read_paths(
    candidates: list[dict[str, Any]] | None,
    *,
    read_ok: set[str],
    target_scope: str,
    limit: int,
    path_under_scope: PathUnderScope,
    path_exists_repo_relative: PathExists,
    repo_readable_evidence_file: ReadableEvidenceFile,
) -> list[str]:
    out: list[str] = []
    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        p = repo_rel_token(item.get("path") or "")
        if not p or p in read_ok or p in out:
            continue
        if target_scope and not path_under_scope(p, target_scope):
            continue
        if not path_exists_repo_relative(p) or not repo_readable_evidence_file(p):
            continue
        out.append(p)
        if len(out) >= limit:
            break
    return out
