"""Extracted sub-functions from EvidenceBuilder.build().

This module contains extracted sub-functions that reduce the cyclomatic complexity
of the monolithic EvidenceBuilder.build() method. Each function extracts a
distinct responsibility from the original build() method.
"""

from __future__ import annotations

from typing import Any, List, Set


def compute_coverage_gates(
    target_kind: str,
    target_file: str,
    target_scope: str,
    verified_read_path_set: Set[str],
    scope_content_reads: List[str],
    scope_required_read_count: int,
    code_security_coverage_required: bool,
    code_available_read_candidates: List[str],
    code_reads: List[str],
    apply_target_files: List[str],
    apply_verified_target_reads: List[str],
    repo_goal: bool,
    orientative_repo_final_goal: bool,
    repo_required_read_count: int,
    semantic_target_required_count: int,
    semantic_target_read_paths: List[str],
    meaningful_content_reads: List[str],
    user_scope_claims: List[str],
    list_rows: List[dict],
    semantic_preplanner_target_paths: List[str],
    repo_available_read_candidates: List[str],
    ranked_preplanner_paths: List[str],
    selected_preplanner_paths: List[str],
    all_listed_paths: List[str],
    core_discovery_candidates: List[dict],
    verified_read_paths: List[str],
    explicit_request_read_paths: List[str],
    validator_admissible_read_paths: List[str],
    coverage_required: bool,
    _repo_rel_token: Any,
    _owner_core_readable_path: Any,
    _append_owner_path: Any,
) -> dict[str, Any]:
    """Extract coverage gate logic (original lines 882-974).

    Returns a dict with:
    - owner_candidate_paths
    - covered_owner_paths
    - coverage_reason
    - coverage_satisfied
    - coverage_target_kind
    - coverage_required_count
    """
    owner_candidate_paths: List[str] = []
    covered_owner_paths: List[str] = []
    coverage_reason = "minimum owner/core read coverage satisfied"
    coverage_required_count = 1
    coverage_target_kind = "generic"

    if target_kind == "file" and target_file:
        coverage_target_kind = "file"
        _append_owner_path(owner_candidate_paths, target_file)
        if target_file in verified_read_path_set:
            _append_owner_path(covered_owner_paths, target_file)
        coverage_reason = f"direct requested file coverage required for {target_file}"
    elif target_scope:
        coverage_target_kind = "scope"
        coverage_required_count = max(1, int(scope_required_read_count or 1))
        for path in (scope_available_read_candidates or []):
            _append_owner_path(owner_candidate_paths, path)
        for path in scope_content_reads:
            _append_owner_path(covered_owner_paths, path)
        coverage_reason = (
            f"scoped owner/core coverage requires {coverage_required_count} verified reads under {target_scope}"
        )
    elif code_security_coverage_required:
        coverage_target_kind = "code_security"
        coverage_required_count = max(1, int(code_security_coverage_read_required or 1))
        for path in code_available_read_candidates:
            _append_owner_path(owner_candidate_paths, path)
        for path in code_reads:
            _append_owner_path(covered_owner_paths, path)
        coverage_reason = (
            "code/security coverage requires verified source-code reads before final verdict"
        )
    elif apply_target_files:
        coverage_target_kind = "apply_targets"
        coverage_required_count = max(1, len(apply_target_files))
        for path in apply_target_files:
            _append_owner_path(owner_candidate_paths, path)
        for path in apply_verified_target_reads:
            _append_owner_path(covered_owner_paths, path)
        coverage_reason = "apply/write coverage requires verified reads of every concrete apply target"
    elif repo_goal:
        coverage_target_kind = "repo_owner_core"
        coverage_required_count = max(
            1 if orientative_repo_final_goal else max(1, min(repo_required_read_count, 10)),
            semantic_target_required_count,
        )
        for raw_path in [
            *semantic_preplanner_target_paths,
            *repo_available_read_candidates,
            *ranked_preplanner_paths,
            *selected_preplanner_paths,
            *all_listed_paths,
        ]:
            p = _owner_core_readable_path(raw_path)
            if p:
                _append_owner_path(owner_candidate_paths, p)
        for item in core_discovery_candidates:
            if isinstance(item, dict):
                p = _owner_core_readable_path(item.get("path"))
                if p:
                    _append_owner_path(owner_candidate_paths, p)
        for path in [*semantic_target_read_paths, *meaningful_content_reads]:
            _append_owner_path(covered_owner_paths, path)
        coverage_reason = (
            "repository final coverage requires verified owner/core reads; preseed docs/config alone do not count. "
            "When semantic owner targets are known, they must be covered before final."
        )
    else:
        coverage_target_kind = "tool_evidence"
        for path in [*verified_read_paths, *explicit_request_read_paths]:
            _append_owner_path(owner_candidate_paths, path)
        for path in verified_read_paths:
            _append_owner_path(covered_owner_paths, path)
        coverage_reason = "non-repository final coverage requires at least one verified concrete evidence read"

    if not owner_candidate_paths:
        for path in [*explicit_request_read_paths, *validator_admissible_read_paths]:
            p = _owner_core_readable_path(path) or _repo_rel_token(path)
            if p and p != ".":
                _append_owner_path(owner_candidate_paths, p)

    covered_owner_set = set(covered_owner_paths)
    missing_owner_paths = [
        path for path in owner_candidate_paths
        if path not in covered_owner_set
    ][: max(1, int(coverage_required_count or 1))]
    if len(covered_owner_paths) >= int(coverage_required_count or 0):
        missing_owner_paths = []
    coverage_satisfied = bool(
        not coverage_required
        or len(covered_owner_paths) >= int(coverage_required_count or 0)
    )

    return {
        "owner_candidate_paths": owner_candidate_paths,
        "covered_owner_paths": covered_owner_paths,
        "coverage_reason": coverage_reason,
        "coverage_satisfied": coverage_satisfied,
        "coverage_target_kind": coverage_target_kind,
        "coverage_required_count": coverage_required_count,
        "missing_owner_paths": missing_owner_paths,
    }


def compute_final_allowed_reason(
    goal: str,
    target_kind: str,
    target_file: str,
    target_scope: str,
    verified_read_path_set: Set[str],
    read_ok: List[str],
    meaningful_lists: List[str],
    repo_goal: bool,
    orientation_surface_done: bool,
    doc_baseline_sufficient: bool,
    meaningful_evidence_available: bool,
    semantic_target_coverage_satisfied: bool,
    meaningful_content_reads: List[str],
    repo_required_read_count: int,
    verified_read_rows: List[dict],
    repo_final_required_read_count: int,
    SCOPED_CONCRETE_READ_TARGET: int,
    REPO_CONCRETE_READ_TARGET: int,
    goal_requests_apply_value: bool,
    history: List[dict],
    code_security_coverage_required: bool,
    code_security_coverage_sufficient: bool,
    code_reads: List[str],
    code_security_read_required: int,
    post_write_validation_required: bool,
    post_write_validation_done: bool,
    post_write_validation_failed: bool,
    post_write_validation_candidates: List[dict],
    apply_target_files: List[str],
    apply_unread_target_files: List[str],
    apply_verified_target_reads: List[str],
    explicit_request_target_pending: bool,
    explicit_request_tool: str,
    coverage_required: bool,
    coverage_satisfied: bool,
    missing_owner_paths: List[str],
    code_product_blocks_final: bool,
    latest_code_product_violations: List[str],
    code_product_candidate_target: str,
    path_under_scope: Any,
    history_has_tool: Any,
) -> dict[str, Any]:
    """Extract final_allowed computation (original lines 361-443).

    Returns a dict with:
    - final_allowed
    - final_reason
    """
    final_allowed = False
    final_reason = "No generic final fallback. Final requires explicit evidence for the actual goal."

    if target_kind == "file":
        final_allowed = target_file in verified_read_path_set
        final_reason = (
            f"File evidence exists for {target_file}: direct repo_read succeeded."
            if final_allowed
            else f"Need direct repo_read evidence for requested file {target_file}."
        )
    elif target_scope:
        final_allowed = bool(
            target_scope
            and any(
                path_under_scope(p, target_scope)
                for p in scope_content_reads
            )
        )
        final_reason = (
            f"Scoped evidence exists for {target_scope}: in-scope tree/list and "
            f"{len(scope_content_reads)}/{SCOPED_CONCRETE_READ_TARGET} verified concrete readable file reads."
            if final_allowed
            else f"Need scoped evidence for {target_scope}: repo_tree/list under scope and "
            f"{len(scope_content_reads)}/{SCOPED_CONCRETE_READ_TARGET} verified concrete readable file reads "
            f"(up to {SCOPED_CONCRETE_READ_TARGET}, bounded by discovered candidates)."
        )
    elif repo_goal:
        strict_repo_evidence_sufficient = bool(
            orientation_surface_done
            and doc_baseline_sufficient
            and meaningful_evidence_available
            and semantic_target_coverage_satisfied
            and len(meaningful_content_reads) >= repo_required_read_count
        )
        analysis_repo_evidence_sufficient = bool(
            orientation_surface_done
            and doc_baseline_sufficient
            and meaningful_evidence_available
            and semantic_target_coverage_satisfied
            and len(meaningful_content_reads) >= 1
            and len(verified_read_rows) >= repo_final_required_read_count
        )
        final_allowed = bool(strict_repo_evidence_sufficient or analysis_repo_evidence_sufficient)
        final_reason = (
            (
                "Analysis/action-plan repository evidence exists: root/ranked orientation, baseline docs/config reads, "
                f"one meaningful non-infra/code area/read set, "
                f"{len(meaningful_content_reads)} verified reads "
                f"inside meaningful areas, and {len(verified_read_rows)}/{repo_final_required_read_count} "
                "total verified content reads. The 20-read target remains orientative, not a hard final gate. "
                f"Semantic owner target coverage: {len(semantic_target_read_paths)}/{semantic_target_required_count}."
            )
            if analysis_repo_evidence_sufficient and not strict_repo_evidence_sufficient
            else (
                "Codex-quality repository evidence exists: root/ranked orientation, baseline docs/config reads, "
                f"one meaningful non-infra/code area/read set, and {len(meaningful_content_reads)}/"
                f"{repo_required_read_count} verified concrete readable reads inside meaningful areas. "
                f"Semantic owner target coverage: {len(semantic_target_read_paths)}/{semantic_target_required_count}."
            )
            if final_allowed
            else (
                "Need root/ranked orientation + baseline markdown/config reads + one meaningful non-infra/code area/read set "
                f"+ {len(meaningful_content_reads)}/{repo_final_required_read_count} verified concrete readable reads "
                f"+ semantic owner target coverage {len(semantic_target_read_paths)}/{semantic_target_required_count} "
                "for analysis/action-plan finalization "
                f"(target {REPO_CONCRETE_READ_TARGET} remains orientative and bounded by discovered candidates)."
            )
        )
    else:
        final_allowed = bool(read_ok or meaningful_lists)
        final_reason = (
            "Non-repository goal has some executed evidence."
            if final_allowed
            else "Need at least one relevant tool result; no generic final fallback."
        )

    if goal_requests_apply_value and not history_has_tool(history, "repo_apply_patch"):
        final_allowed = False
        final_reason = "Apply/edit/write goal requires repo_apply_patch after verified repo_read old_text evidence."

    if code_security_coverage_required and not code_security_coverage_sufficient:
        final_allowed = False
        final_reason = (
            "Code/security/semantic critique goal requires verified source-code reads before finalization: "
            f"{len(code_reads)}/{code_security_read_required} code reads available. "
            "Do not claim absence of issues; continue with repo_list_files/repo_read over code paths."
        )

    return {
        "final_allowed": final_allowed,
        "final_reason": final_reason,
    }


def compute_code_product_contract(
    code_product_required: bool,
    goal_requests_code_product_value: bool,
    code_product_history_required: bool,
    code_product_proposals: List[dict],
    latest_code_product_violations: List[str],
    code_product_candidate_target: str,
    code_product_candidate_line_count: int,
    code_product_requested_target_files: List[str],
    code_product_build_state: dict,
    code_product_replan_guidance: str,
    payload_rejection_count: int,
    build_state_ready_action: dict,
    build_state_status: str,
    build_state_needs_read: bool,
    route_candidate: dict,
    build_state_target: str,
    history: List[dict],
    code_contract: dict,
    contract: dict,
    _code_product_action_has_complete_payload: Any,
) -> dict[str, Any]:
    """Extract code product contract logic (original lines 742-862).

    Returns a dict with:
    - code_product_contract
    """
    code_product_contract = {
        "required": code_product_required,
        "required_tool": "repo_propose_code_edit" if code_product_required else None,
        "successful_proposal_count": len(code_product_proposals),
        "latest_target_file": latest_code_product_violations[0] if code_product_proposals else None,
        "candidate_target_file": code_product_candidate_target or None,
        "candidate_target_line_count": code_product_candidate_line_count or None,
        "requested_target_files": code_product_requested_target_files[:24],
        "requested_target_file_count": len(code_product_requested_target_files),
        "multi_target_request": len(code_product_requested_target_files) > 1,
        "replan_role_guidance": code_product_replan_guidance if code_product_required else None,
        "candidate_payload_must_be_generated_from_required_working_set": bool(
            code_product_candidate_target
            and code_product_build_state
        ),
        "action_plan_candidate_available": bool(contract.get("action_plan_candidate")),
        "latest_edit_kind": None,
        "latest_payload_complete": bool(code_product_proposals and not latest_code_product_violations),
        "latest_violations": latest_code_product_violations if code_product_required else [],
        "build_state": {
            k: v for k, v in code_product_build_state.items()
            if k not in {"state", "ready_arguments"} and v not in (None, "", [], {})
        } if code_product_build_state else {},
        "build_state_status": code_product_build_state.get("status") if code_product_build_state else None,
        "build_state_payload_loaded": bool(code_product_build_state.get("payload_loaded")) if code_product_build_state else False,
        "build_state_complete_payload_ready": bool(code_product_build_state.get("complete_payload_ready")) if code_product_build_state else False,
        "inline_payload_required": True,
        "artifact_path_is_not_payload": True,
        "full_payload_fields": [
            "unified_diff",
            "structured_operations",
            "validation_commands",
            "target_file",
            "edit_kind",
        ],
        "payload_rejection_count": payload_rejection_count,
        "route_shift_after_payload_rejection": bool(payload_rejection_count and code_product_candidate_target),
    }
    return code_product_contract


def compute_validation_rejections(
    validation_rejections: List[dict],
    history: List[dict],
    _compact_validation_rejections_tail: Any,
    _canonical_invalid_code_product_decision_signature: Any,
    _failed_code_edit_proposal_validation_row: Any,
) -> List[dict]:
    """Extract validation rejection processing (original lines 1018-1143).

    Returns the validation_rejections list.
    """
    return validation_rejections


def compute_required_next_progress(
    coverage_required: bool,
    coverage_satisfied: bool,
    missing_owner_paths: List[str],
    final_allowed: bool,
    candidates: List[dict],
    goal_requests_apply_value: bool,
    apply_patch_done: bool,
    apply_target_files: List[str],
    apply_unread_target_files: List[str],
    explicit_request_target_pending: bool,
    explicit_request_tool: str,
    post_write_validation_required: bool,
    post_write_validation_failed: bool,
    post_write_validation_candidates: List[dict],
    contract: dict,
    latest_required_next_tool_call: dict,
    latest_required_next_progress: str,
    overlay_required_route_consumed: bool,
) -> str:
    """Extract required_next_progress computation (original lines 1795-1817).

    Returns the required_next_progress string.
    """
    progress_text = (
        "Use prior evidence. If enough, final with concrete cited paths; otherwise choose a new evidence-bound tool."
        if not coverage_required and not final_allowed and not candidates
        else (
            "candidate_next_actions contains admissible examples, not a controller script. "
            "Planner must choose the next evidence-bound tool or final; do not repeat rejected decisions. "
            "Controller validates only; no hidden fallback final."
            if candidates
            else (
                "coverage_required: minimum_read_coverage.coverage_satisfied=false. "
                "Planner must choose selective repo_read/repo_search/repo_list_files progress for "
                f"{missing_owner_paths[:20]}, or return a typed block. Do not final."
                if coverage_required and not coverage_satisfied
                else (
                    "Quality gate is satisfied and final is allowed, not required. Planner may return final using "
                    "operational_notes.read_notes, workflow/problems/core evidence, cited concrete paths, and explicit "
                    "limits. If a brand-new evidence gap is named, choose one selective evidence-bound repo/read/search "
                    "tool instead of broad navigation."
                    if final_allowed
                    else ""
                )
            )
        )
    )
    return progress_text