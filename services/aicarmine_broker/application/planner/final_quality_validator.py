"""Final quality validation and terminal block handling."""

from __future__ import annotations

import json
from typing import Any, Mapping

from aicarmine_broker.application.code_product import history
from aicarmine_broker.application.evidence.audit_guidance import goal_requests_semantic_audit
from aicarmine_broker.application.evidence.goal_classifier import effective_repo_analysis_goal
from aicarmine_broker.application.tool_surface.required_tool_call import (
    append_stale_required_call_marker,
    required_next_tool_call_satisfaction,
)
from aicarmine_broker.application.shared.path_tokens import repo_path_token as _repo_path_token, repo_rel_token

# Import validation utilities from shared module
from aicarmine_broker.application.shared.validation_utils import (
    _list_or_empty,
    _repo_path_is_concrete,
    _coalesce_repo_read_paths,
    _final_quality_repo_read_allowlist,
    _collect_repo_paths,
    _known_contract_repo_paths,
    _known_contract_repo_dirs,
    _route_token_is_prose_or_metric,
    _search_query_is_concrete,
    _required_next_route_has_deterministic_proof,
)


def _next_final_rewrite_latch(
    current: str,
    *,
    reject_count: int,
    has_gap_route: bool,
) -> str:
    current = str(current or "").strip().lower()
    if current == "terminal_block_required":
        return current

    # one retry is allowed; on the second final-quality reject, block deterministically.
    if reject_count >= 2:
        return "terminal_block_required"

    if current == "required_gap_only":
        if has_gap_route:
            return "required_gap_only"
        return "terminal_block_required"

    # first rejection starts rewrite branch and keeps retry path concrete.
    return "rewrite_required"


def _escalate_final_terminal_block_state(
    contract: dict[str, Any],
    *,
    has_gap_route: bool,
) -> dict[str, Any]:
    contract = contract if isinstance(contract, dict) else {}
    
    # Check cuda_rewrite stuck count - force terminal block if exceeded
    MAX_CUDA_REWRITE_ATTEMPTS = 2
    cuda_rewrite_count = int(contract.get("planner_rewrite_stuck_count") or 0)
    if cuda_rewrite_count >= MAX_CUDA_REWRITE_ATTEMPTS:
        contract["planner_cuda_rewrite_required"] = False
        final_contract = (
            contract.get("finalization_contract")
            if isinstance(contract.get("finalization_contract"), dict)
            else {}
        )
        final_contract["final_allowed"] = False
        final_contract["planner_may_choose_final"] = False
        final_contract["planner_may_choose_block"] = False
        final_contract["reason"] = "cuda_rewrite_max_attempts_exceeded"
        contract["finalization_contract"] = final_contract
        return contract
    
    current_latch = str(contract.get("final_rewrite_latch") or "").strip().lower()
    if not current_latch:
        return contract
    if current_latch not in {"rewrite_required", "required_gap_only", "terminal_block_required"}:
        return contract
    if contract.get("planner_cuda_rewrite_required") is not True:
        return contract
    if current_latch == "terminal_block_required":
        contract["planner_may_choose_block"] = True
        return contract

    reject_count = int(contract.get("planner_final_quality_reject_count") or 0) + 1
    contract["planner_final_quality_reject_count"] = reject_count
    contract["planner_final_quality_last_rewrite_decision"] = len(history)

    # EARLY WARNING: Alert when first rejection occurs
    if reject_count >= 1:
        import logging
        logging.warning(
            f"Terminal block risk detected: reject_count={reject_count}. "
            f"Ensure entry points are verified before finalizing."
        )
    
    next_latch = _next_final_rewrite_latch(
        current_latch,
        reject_count=reject_count,
        has_gap_route=has_gap_route,
    )
    contract["final_rewrite_latch"] = next_latch
    contract["planner_may_choose_block"] = next_latch == "terminal_block_required"
    final_contract = (
        contract.get("finalization_contract")
        if isinstance(contract.get("finalization_contract"), dict)
        else {}
    )
    if next_latch == "terminal_block_required":
        final_contract["planner_may_choose_block"] = True
        final_contract["final_allowed"] = False
        final_contract["planner_may_choose_final"] = False
        final_contract["reason"] = "planner_cuda_rewrite_required_repeated_retry_block_required"
    elif next_latch == "required_gap_only":
        final_contract["reason"] = "planner_cuda_rewrite_required_retry_gap_only"
    else:
        final_contract["reason"] = "planner_cuda_rewrite_required_retry_continue"
    contract["finalization_contract"] = final_contract
    return contract


def _clear_final_terminal_block_state(contract: dict[str, Any]) -> dict[str, Any]:
    contract = contract if isinstance(contract, dict) else {}
    final_contract = (
        contract.get("finalization_contract")
        if isinstance(contract.get("finalization_contract"), dict)
        else {}
    )

    # A valid final answer is considered an explicit reset of terminal rewrite/block
    # pressure for the current contract state.
    contract["final_rewrite_latch"] = "inactive"
    contract["planner_may_choose_block"] = False
    contract["planner_may_choose_final"] = True
    for key in (
        "planner_cuda_rewrite_required",
        "planner_forced_terminal_block",
        "planner_forced_terminal_block_reason",
        "planner_final_quality_terminal_block",
        "planner_final_quality_terminal_block_count",
        "planner_final_quality_terminal_block_latched",
        "planner_final_quality_latched_patch_axes",
        "planner_final_quality_latched_operator_instructions",
        "planner_final_answer_blocked_reason",
        "planner_final_quality_public_notice",
        "required_next_tool_call",
        "required_next_tool_call_validated",
        "required_next_tool_call_validation_source",
        "required_next_tool_call_invalid_tool",
        "required_next_tool_call_invalid_reason",
        "required_next_tool_call_satisfied",
        "required_next_tool_call_satisfied_reason",
        "required_next_missing_evidences",
        "required_next_output_sections",
        "invalid_required_next_missing_evidences",
        "invalid_required_next_missing_evidence_reason",
        "invalid_required_next_tool_call_paths",
        "invalid_required_next_tool_call_reason",
        "invalid_required_next_tool_call_query",
        "required_next_progress_model_stale",
        "required_next_progress_model",
        "stale_required_next_tool_calls",
        "required_next_progress",
        "required_next_tool_call_validation_error",
        "replan_specialist_route_diagnostics",
        "replan_specialist_route_audit",
        "replan_specialist_retry_audit",
        "replan_specialist_retry_replan",
    ):
        contract.pop(key, None)

    existing_actions = (
        contract.get("candidate_next_actions")
        if isinstance(contract.get("candidate_next_actions"), list)
        else []
    )
    filtered_actions = [
        item for item in existing_actions
        if not (
            isinstance(item, dict)
            and (
                str(item.get("source") or "") == "repo_analysis_final_model_quality"
                or str(item.get("action_id") or "").startswith("repo_analysis_final_quality:")
            )
        )
    ]
    if filtered_actions:
        contract["candidate_next_actions"] = filtered_actions
    else:
        contract.pop("candidate_next_actions", None)

    final_contract["final_allowed"] = True
    final_contract["planner_may_choose_final"] = True
    final_contract["planner_may_choose_block"] = False
    for key in (
        "planner_forced_terminal_block",
        "planner_forced_terminal_block_reason",
        "planner_final_quality_terminal_block",
        "planner_final_quality_terminal_block_count",
        "planner_final_quality_terminal_block_latched",
        "planner_final_quality_latched_patch_axes",
        "planner_final_quality_latched_operator_instructions",
        "planner_final_answer_blocked_reason",
        "planner_final_quality_public_notice",
        "required_next_tool_call",
        "required_next_missing_evidences",
        "required_next_output_sections",
        "replan_specialist_route_diagnostics",
        "replan_specialist_route_audit",
        "replan_specialist_retry_audit",
        "replan_specialist_retry_replan",
    ):
        final_contract.pop(key, None)
    if final_contract.get("reason") in {
        "repo_analysis_final_quality_no_runnable_gap_terminal_block",
        "repo_analysis_final_model_quality_rejected_no_runnable_gap",
        "planner_cuda_rewrite_required_repeated_retry_block_required",
        "planner_cuda_rewrite_required_retry_gap_only",
        "planner_cuda_rewrite_required_retry_continue",
        "required_next_tool_call_unknown_tool",
        "required_next_tool_call_not_in_current_surface",
    }:
        final_contract.pop("reason", None)
    contract["finalization_contract"] = final_contract
    return contract


def _answer_chunk_misuses_terminal_payload_shape(text: str) -> bool:
    try:
        parsed = json.loads(str(text or ""))
    except Exception:
        return False
    if not isinstance(parsed, dict):
        return False
    return any(str(key) in parsed for key in ("final_answer", "answer", "summary"))


def _successful_answer_chunk_signatures() -> set[str]:
    signatures: set[str] = set()
    # This function would need to be implemented based on the actual history processing
    return signatures


def _minimum_read_coverage_contract() -> dict[str, Any]:
    # This function would need to be implemented based on the actual contract processing
    return {}


def _minimum_read_coverage_required() -> bool:
    # This function would need to be implemented based on the actual contract processing
    return False


def _minimum_read_coverage_satisfied() -> bool:
    # This function would need to be implemented based on the actual contract processing
    return False


def _minimum_read_coverage_missing_owner_paths() -> list[str]:
    # This function would need to be implemented based on the actual contract processing
    return []


def _final_answer_declares_missing_coverage(text: str) -> bool:
    low = str(text or "").lower()
    return any(
        needle in low
        for needle in (
            "coverage_satisfied=false",
            "coverage_satisfied: false",
            '"coverage_satisfied": false',
            "missing_owner_paths",
            "missing coverage",
            "insufficient coverage",
            "copertura mancante",
            "mancanza di copertura",
        )
    )


def _coalesce_required_next_missing_paths(values: Any) -> list[str]:
    out: list[str] = []
    if not isinstance(values, (list, tuple, set)):
        return out
    for value in values:
        token = repo_rel_token(value)
        if token and token not in out:
            out.append(token)
    return out[:12]


def _stale_required_next_repo_read_paths() -> set[str]:
    paths: set[str] = set()
    # This function would need to be implemented based on the actual contract processing
    return paths


def _successful_read_paths_for_final_route() -> set[str]:
    # This function would need to be implemented based on the actual contract processing
    return set()


def _path_allowed_by_missing_evidence(path: str, required_missing: list[str]) -> bool:
    # This function would need to be implemented based on the actual contract processing
    return False


def _verified_required_next_missing_paths(values: Any) -> tuple[list[str], list[str]]:
    valid: list[str] = []
    invalid: list[str] = []
    # This function would need to be implemented based on the actual contract processing
    return valid[:12], invalid[:12]


def _required_next_tool_from_missing_evidences(values: Any, allow_if_missing: bool) -> dict[str, Any]:
    # This function would need to be implemented based on the actual contract processing
    return {}


def _coalesce_required_next_tool_tool(value: dict[str, Any]) -> dict[str, Any]:
    # This function would need to be implemented based on the actual contract processing
    return {}


def _coerce_final_rewrite_latch(value: Any) -> str:
    raw = str(value or "inactive").strip().lower()
    return (
        raw
        if raw in {"inactive", "rewrite_required", "required_gap_only", "terminal_block_required"}
        else "inactive"
    )


def _required_gap_paths_from_quality(
    quality: Mapping[str, Any],
    *,
    existing_missing: list[str],
) -> list[str]:
    # This function would need to be implemented based on the actual contract processing
    return []


def _apply_final_quality_route(quality: dict[str, Any]) -> None:
    # This function would need to be implemented based on the actual contract processing
    pass