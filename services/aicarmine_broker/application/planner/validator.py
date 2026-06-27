

from collections.abc import Mapping
import json
from typing import Any
from .validator_helpers import *
from .validator_helpers import ValidationContext
from aicarmine_broker.application.evidence.audit_guidance import *
from aicarmine_broker.application.evidence.goal_classifier import *
from aicarmine_broker.application.shared.path_tokens import *
from aicarmine_broker.application.tool_surface.required_tool_call import *

def _normalize_terminal_planner_decision(
    decision: dict[str, Any]
) -> dict[str, Any]:
    """Normalize terminal planner decision."""
    return decision


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _repo_path_is_concrete(token: Any) -> bool:
    token = repo_path_token(token)
    if not token:
        return False
    lowered = token.lower()
    if lowered in {"services", "tools", "cache", "cache_dir", "repo"}:
        return False
    if " " in token:
        return False
    if token in {".", ".."}:
        return False
    if "/" in token or "\\" in token:
        return True
    if token.count(".") >= 1:
        return True
    return False


def _coalesce_repo_read_paths(values: Any) -> list[str]:
    if isinstance(values, tuple):
        values = list(values)
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for value in values:
        token = repo_path_token(value)
        if not _repo_path_is_concrete(token):
            continue
        if token not in out:
            out.append(token)
    return out


def _final_quality_repo_read_allowlist(contract: dict[str, Any]) -> set[str]:
    contract = contract if isinstance(contract, dict) else {}
    allowlist: set[str] = set()
    memory = contract.get("file_memory") if isinstance(contract.get("file_memory"), list) else []
    operational = contract.get("operational_notes") if isinstance(contract.get("operational_notes"), dict) else {}
    read_notes = operational.get("read_notes") if isinstance(operational.get("read_notes"), list) else []
    rows: list[dict[str, Any]] = [row for row in memory if isinstance(row, dict)] + [
        row for row in read_notes if isinstance(row, dict)
    ]

    def add_token(raw: Any) -> None:
        token = repo_path_token(raw)
        if token and _repo_path_is_concrete(token):
            allowlist.add(token)

    for key in (
        "validator_admissible_repo_read_paths",
        "read_admissible_paths",
        "successful_repo_read_paths",
        "covered_owner_paths",
        "candidate_owner_paths",
        "missing_owner_paths",
    ):
        values = contract.get(key)
        if isinstance(values, dict):
            for item in values.values():
                if isinstance(item, dict):
                    add_token(item.get("path"))
                    add_token(item.get("repo_path"))
                else:
                    add_token(item)
        elif isinstance(values, list):
            for item in values:
                if isinstance(item, dict):
                    add_token(item.get("path"))
                    add_token(item.get("repo_path"))
                else:
                    add_token(item)
    verified_reads = contract.get("verified_content_reads")
    if isinstance(verified_reads, list):
        for read in verified_reads:
            if isinstance(read, dict):
                add_token(read.get("path") or read.get("repo_path"))
    for row in rows:
        add_token(row.get("path"))
        for path in row.get("mentioned_paths") if isinstance(row.get("mentioned_paths"), list) else []:
            add_token(path)
    return allowlist


def _next_final_rewrite_latch(
    current: str,
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


def _collect_repo_paths(values: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(values, dict):
        for item in values.values():
            token = repo_path_token(item)
            if token:
                out.add(token)
    elif isinstance(values, list):
        for item in values:
            if isinstance(item, dict):
                token = repo_path_token(item.get("path") or item.get("source_path") or item.get("repo_path"))
            else:
                token = repo_path_token(item)
            if token:
                out.add(token)
    else:
        token = repo_path_token(values)
        if token:
            out.add(token)
    return out


def _known_contract_repo_paths(contract: dict[str, Any]) -> set[str]:
    contract = contract if isinstance(contract, dict) else {}
    paths: set[str] = set()
    for key in (
        "validator_admissible_repo_read_paths",
        "read_admissible_paths",
        "successful_repo_read_paths",
        "verified_content_reads",
        "covered_owner_paths",
        "candidate_owner_paths",
        "missing_owner_paths",
    ):
        paths.update(_collect_repo_paths(contract.get(key)))
    coverage = contract.get("minimum_read_coverage") if isinstance(contract.get("minimum_read_coverage"), dict) else {}
    for key in ("covered_owner_paths", "candidate_owner_paths", "missing_owner_paths"):
        paths.update(_collect_repo_paths(coverage.get(key)))
    final_contract = contract.get("finalization_contract") if isinstance(contract.get("finalization_contract"), dict) else {}
    final_coverage = (
        final_contract.get("minimum_read_coverage")
        if isinstance(final_contract.get("minimum_read_coverage"), dict)
        else {}
    )
    for key in ("covered_owner_paths", "candidate_owner_paths", "missing_owner_paths"):
        paths.update(_collect_repo_paths(final_coverage.get(key)))
    return {path for path in paths if path and path != "."}


def _known_contract_repo_dirs(contract: dict[str, Any]) -> set[str]:
    dirs = {"."}
    for path in _known_contract_repo_paths(contract):
        parts = [part for part in path.split("/") if part]
        for index in range(1, len(parts)):
            dirs.add("/".join(parts[:index]))
    return dirs


def _route_token_is_prose_or_metric(value: Any) -> bool:
    token = repo_path_token(value)
    if not token:
        return True
    lowered = token.lower()
    if lowered in {
        "ridondanze/rischi",
        "docs/config",
        "planner/final-quality",
        "planner/controller rejection paths",
    }:
        return True
    compact = lowered.replace("/", "").replace(".", "").replace("-", "").replace("_", "")
    if "/" in lowered and compact.isdigit():
        return True
    if " " in token:
        return True
    return False


def _search_query_is_concrete(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or len(text) > 260:
        return False
    lowered = text.lower()
    if lowered in {
        "docs/config",
        "ridondanze/rischi",
        "8/2",
        "8/8",
        "9/9",
        "planner/controller rejection paths",
    }:
        return False
    compact = lowered.replace("/", "").replace(".", "").replace("-", "").replace("_", "")
    if "/" in lowered and compact.isdigit():
        return False
    useful_tokens = [
        token
        for token in lowered.replace(",", " ").replace(";", " ").split()
        if len(token) >= 3 and "/" not in token and any(ch.isalpha() for ch in token)
    ]
    if "/" in lowered and len(useful_tokens) < 2:
        return False
    return bool(useful_tokens)


def _required_next_route_has_deterministic_proof(
    required_call: dict[str, Any],
    contract: dict[str, Any],
) -> bool:
    required_call = required_call if isinstance(required_call, dict) else {}
    tool = str(required_call.get("tool") or "").strip()
    args = required_call.get("arguments") if isinstance(required_call.get("arguments"), dict) else {}
    if tool == "repo_read":
        return True
    if tool == "repo_list_files":
        path = repo_path_token(args.get("path") or ".") or "."
        if path == ".":
            return True
        return not _route_token_is_prose_or_metric(path) and path in _known_contract_repo_dirs(contract)
    if tool in {"repo_semantic_search", "repo_rg_search", "repo_search"}:
        query = args.get("query") or args.get("pattern") or args.get("symbol") or args.get("needle") or args.get("text")
        if not _search_query_is_concrete(query):
            return False
        path = repo_path_token(args.get("path")) if args.get("path") else ""
        if path and path not in _known_contract_repo_paths(contract) and path not in _known_contract_repo_dirs(contract):
            return False
        return True
    if tool == "planner_scratchpad_read":
        document_id = str(args.get("document_id") or "").strip()
        target_file = repo_path_token(args.get("target_file")) if args.get("target_file") else ""
        if document_id and not _route_token_is_prose_or_metric(document_id):
            return True
        return bool(target_file and target_file in _known_contract_repo_paths(contract))
    return False


def validate_planner_decision_against_evidence(
    goal: str,
    decision: dict[str, Any],
    history: list[dict[str, Any]],
    deps: Any,
    config: Any,
) -> dict[str, Any]:
    AGENTIC_PLANNER_NATIVE_TOOLS = config["AGENTIC_PLANNER_NATIVE_TOOLS"]
    CODE_PRODUCT_BUILD_STATE_KIND = config["CODE_PRODUCT_BUILD_STATE_KIND"]
    VALID_INTERNAL_TOOLS = config["VALID_INTERNAL_TOOLS"]
    SUPPORT_SUBTURN_TOOLS = frozenset({
        "planner_scratchpad_read",
        "planner_scratchpad_write",
        "runtime_sqlite_memory_search",
        "runtime_sqlite_memory_write",
    })
    _agentic_v2_decision_paths = deps["agentic_v2_decision_paths"]
    _agentic_v2_goal_scope = deps["agentic_v2_goal_scope"]
    _agentic_v2_read_has_window = deps["agentic_v2_read_has_window"]
    _agentic_v2_successful_read_paths = deps["agentic_v2_successful_read_paths"]
    _any_argument_group_present = deps["any_argument_group_present"]
    _apply_duplicate_window_replan_contract = deps["apply_duplicate_window_replan_contract"]
    _apply_unverified_old_text_replan_contract = deps["apply_unverified_old_text_replan_contract"]
    _argument_value_present = deps["argument_value_present"]
    _canonical_invalid_code_product_decision_signature = deps["canonical_invalid_code_product_decision_signature"]
    _code_product_build_state_duplicate_write = deps["code_product_build_state_duplicate_write"]
    _code_product_build_state_has_collecting_progress = deps["code_product_build_state_has_collecting_progress"]
    _code_product_build_state_parse = deps["code_product_build_state_parse"]
    _code_product_build_state_ready_payload = deps["code_product_build_state_ready_payload"]
    _code_product_low_signal_target = deps["code_product_low_signal_target"]
    _code_product_payload_violations = deps["code_product_payload_violations"]
    _contract_final_required_now = deps["contract_final_required_now"]
    _copyable_example_text = deps["copyable_example_text"]
    _decision_matches_prompt_context_continuation = deps["decision_matches_prompt_context_continuation"]
    _decision_paths = deps["decision_paths"]
    _enforce_required_scratchpad_read_continuation_contract = deps[
        "enforce_required_scratchpad_read_continuation_contract"
    ]
    _final_answer_is_action_plan_without_code_product = deps["final_answer_is_action_plan_without_code_product"]
    _final_composition_tool_names_from_candidates = deps["final_composition_tool_names_from_candidates"]
    _repo_analysis_final_answer_model_quality = deps.get("repo_analysis_final_answer_model_quality")
    _repo_analysis_final_answer_quality = deps["repo_analysis_final_answer_quality"]
    _invalid_code_product_decision_signature_count = deps["invalid_code_product_decision_signature_count"]
    _invalid_decision_signature_key = deps["invalid_decision_signature_key"]
    _native_required_tool_decision_has_transport_provenance = deps["native_required_tool_decision_has_transport_provenance"]
    _normalize_terminal_planner_decision = deps["normalize_terminal_planner_decision"]
    _normalize_tool_name = deps["normalize_tool_name"]
    _old_text_verified_by_repo_read = deps["old_text_verified_by_repo_read"]
    _path_exists_repo_relative = deps["path_exists_repo_relative"]
    _path_under_scope = deps["path_under_scope"]
    _planner_scratchpad_read_selector_present = deps["planner_scratchpad_read_selector_present"]
    _planner_scratchpad_window_signature = deps["planner_scratchpad_window_signature"]
    _prompt_window_consumed_offsets = deps["prompt_window_consumed_offsets"]
    _prompt_window_tracking_metadata_errors = deps["prompt_window_tracking_metadata_errors"]
    _repo_analysis_goal = deps["repo_analysis_goal"]
    _repo_path_kind = deps["repo_path_kind"]
    _repo_read_selector_present = deps["repo_read_selector_present"]
    _repo_read_window_signature = deps["repo_read_window_signature"]
    _repo_readable_evidence_file = deps["repo_readable_evidence_file"]
    _repo_rel_token = deps["repo_rel_token"]
    repeated_tool_call_count = deps["repeated_tool_call_count"]
    _scope_claim_conflict_for_path = deps["scope_claim_conflict_for_path"]
    _successful_window_signatures = deps["successful_window_signatures"]
    _target_scope_conflict_resolved = deps["target_scope_conflict_resolved"]
    latest_file_list_result = deps["latest_file_list_result"]
    goal_requires_code_product_report = deps["goal_requires_code_product_report"]
    planner_evidence_contract = deps["planner_evidence_contract"]
    validate_unified_diff_text = deps["validate_unified_diff_text"]

    # ValidationContext: holds all closure variables for extracted helpers
    ctx = ValidationContext(
        contract=planner_evidence_contract(goal, history),
        history=history,
        deps=deps,
        config=config,
        repo_rel_token=_repo_rel_token,
        path_exists_repo_relative=_path_exists_repo_relative,
        repo_readable_evidence_file=_repo_readable_evidence_file,
        normalize_tool_name=_normalize_tool_name,
        decision_paths=_decision_paths,
        prompt_window_consumed_offsets=_prompt_window_consumed_offsets,
        successful_read_paths=_agentic_v2_successful_read_paths,
    )

    decision = _normalize_terminal_planner_decision(decision if isinstance(decision, dict) else {})
    action = str(decision.get("action") or "tool").strip().lower()
    tool = _normalize_tool_name(str(decision.get("tool") or ""))
    args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
    contract = planner_evidence_contract(goal, history)
    semantic_contract = (
        contract.get("semantic_goal_classification")
        if isinstance(contract.get("semantic_goal_classification"), dict)
        else {}
    )
    effective_repo_goal = effective_repo_analysis_goal(
        goal,
        semantic_contract,
        repo_analysis_goal=_repo_analysis_goal,
    )
    semantic_audit_goal = goal_requests_semantic_audit(goal)
    violations: list[str] = []
    from .validator_helpers import (
        _minimum_read_coverage_contract,
        _final_answer_declares_missing_coverage,
        _coalesce_required_next_missing_paths,
        _stale_required_next_repo_read_paths,
        _successful_read_paths_for_final_route,
        _path_allowed_by_missing_evidence,
        _verified_required_next_missing_paths,
        _required_next_tool_from_missing_evidences,
        _coalesce_required_next_tool_tool,
        _coerce_final_rewrite_latch,
        _required_gap_paths_from_quality,
        _next_final_rewrite_latch,
    )

    # Re-bind nested helpers to use ctx for closure variables (wrapper functions)
    def _answer_chunk_misuses_terminal_payload_shape(text: str) -> bool:
        return _answer_chunk_misuses_terminal_payload_shape(ctx, text)

    def _successful_answer_chunk_signatures() -> set[str]:
        return _successful_answer_chunk_signatures(ctx)

    def _minimum_read_coverage_required() -> bool:
        return _minimum_read_coverage_required(ctx)

    def _minimum_read_coverage_satisfied() -> bool:
        return _minimum_read_coverage_satisfied(ctx)

    def _minimum_read_coverage_missing_owner_paths() -> list[str]:
        return _minimum_read_coverage_missing_owner_paths(ctx)

    def _clear_final_terminal_block_state(contract: dict) -> dict:
        ctx.contract = contract
        _clear_final_terminal_block_state(ctx)
        return contract

    def _escalate_final_terminal_block_state(contract: dict, has_gap_route: bool) -> dict:
        ctx.contract = contract
        _escalate_final_terminal_block_state(ctx, has_gap_route)
        return contract

    def _apply_final_quality_route(quality: dict) -> None:
        step_index = len(history)
        _apply_final_quality_route(ctx, quality, step_index)

    def _apply_duplicate_repo_read_path_recovery_contract(contract: dict, repeated_reads: list, history: list) -> dict:
        ctx.contract = contract
        _apply_duplicate_repo_read_path_recovery_contract(ctx, repeated_reads)
        return contract

    internal_inconsistencies: list[str] = []
    prompt_context_continuation_required = (
        decision.get("prompt_context_continuation_required")
        if isinstance(decision.get("prompt_context_continuation_required"), dict)
        else {}
    )
    prompt_context_continuation_matches = bool(
        prompt_context_continuation_required
        and _decision_matches_prompt_context_continuation(
            decision,
            prompt_context_continuation_required,
        )
    )
    if prompt_context_continuation_required:
        contract = _enforce_required_scratchpad_read_continuation_contract(
            contract,
            prompt_context_continuation_required,
        )

    tracking_errors = _prompt_window_tracking_metadata_errors(history)
    if tracking_errors:
        return {
            "ok": False,
            "violations": ["prompt_context_window_tracking_errors"],
            "evidence_contract": contract,
            "prompt_window_tracking_errors": tracking_errors,
        }
    if (
        AGENTIC_PLANNER_NATIVE_TOOLS
        and action == "tool"
        and not _native_required_tool_decision_has_transport_provenance(decision)
    ):
        violations.append("planner_text_tool_call_disallowed_in_native_mode")
        contract["required_next_progress"] = (
            "Native tool mode is required. Tool execution must arrive as "
            "message.tool_calls with native_tool_call=true; JSON-text action=tool "
            "is not executable. Choose a native tool_call, or return a terminal "
            "final/block answer."
        )
        return {"ok": False, "violations": violations, "evidence_contract": contract}
    allowed_tool_names_source = (
        decision.get("allowed_tool_names")
        if isinstance(decision.get("allowed_tool_names"), list)
        else decision.get("allowed_native_tool_names")
    )
    if action == "tool" and isinstance(allowed_tool_names_source, list):
        allowed_tool_names = {
            _normalize_tool_name(str(name or ""))
            for name in allowed_tool_names_source
            if str(name or "").strip()
        }
        if tool not in allowed_tool_names:
            violations.append("tool_not_in_turn_surface")
            if (
                AGENTIC_PLANNER_NATIVE_TOOLS
                and _native_required_tool_decision_has_transport_provenance(decision)
            ):
                violations.append("native_tool_not_in_turn_surface")
            contract["required_next_progress"] = (
                "The tool call was not in the planner tool surface for this turn. "
                "Use only the current turn tool surface; if final is allowed and no named "
                "evidence gap remains, return final instead of calling an unavailable tool."
            )
    if action == "tool" and tool == "planner_scratchpad_read":
        requested_kind = str(args.get("kind") or "").strip()
        requested_doc_id = str(args.get("document_id") or args.get("id") or "").strip()
        if requested_kind in {"prompt_context", "prompt_context_window", CODE_PRODUCT_BUILD_STATE_KIND} and requested_doc_id:
            try:
                requested_offset = int(args.get("offset") or 0)
            except (TypeError, ValueError):
                requested_offset = 0
            consumed_offset = _prompt_window_consumed_offsets(history).get(requested_doc_id, 0)
            if consumed_offset > 0 and requested_offset < consumed_offset:
                violation = "planner_scratchpad_window_already_successful_without_progress"
                contract = _apply_duplicate_window_replan_contract(
                    contract,
                    violation=violation,
                    tool=tool,
                    args=args,
                    history=history,
                )
                return {
                    "ok": False,
                    "violations": [violation],
                    "evidence_contract": contract,
                    "document_id": requested_doc_id,
                    "requested_offset": requested_offset,
                    "expected_next_offset": consumed_offset,
                }
    if prompt_context_continuation_required and not prompt_context_continuation_matches:
        violations.append("prompt_context_continuation_required")
        return {
            "ok": False,
            "violations": violations,
            "evidence_contract": contract,
            "required_prompt_context_continuation": prompt_context_continuation_required,
        }
    if (
        action == "tool"
        and tool == "planner_scratchpad_read"
        and not prompt_context_continuation_matches
        and str(args.get("kind") or "").strip() == "prompt_context_window"
        and _contract_final_required_now(contract)
    ):
        violations.append("final_required_optional_prompt_context_window_disallowed")
        contract["required_next_progress"] = (
            "Quality gate is satisfied. Produce action=final from the real context already "
            "in the prompt and prior verified evidence. Do not consume optional prompt_context_window "
            "repo_read offsets linearly; if a concrete evidence gap remains, it must be named and "
            "resolved before the terminal final-required state with selective repo/RAG/search tools."
        )
        return {
            "ok": False,
            "violations": violations,
            "evidence_contract": contract,
        }

    requested_limit = int(contract.get("requested_file_limit") or 0)
    target_scope = str(contract.get("resolved_goal_scope") or "")
    target_file = str(contract.get("resolved_goal_file") or "")
    target_kind = str(contract.get("target_kind") or "")
    review_goal = bool(contract.get("goal_requests_python_file_review"))
    known_paths_set: set[str] = set()
    known_paths_set.update(_collect_repo_paths(contract.get("known_paths_from_latest_repo_list_files")))
    known_paths_set.update(_collect_repo_paths(contract.get("validator_admissible_repo_read_paths")))
    known_paths_set.update(_collect_repo_paths(contract.get("read_admissible_paths")))
    known_paths_set.update(_collect_repo_paths(contract.get("covered_owner_paths")))
    known_paths_set.update(_collect_repo_paths(contract.get("candidate_owner_paths")))
    known_paths_set.update(_collect_repo_paths(contract.get("missing_owner_paths")))
    known_paths_set.update(_collect_repo_paths(contract.get("successful_repo_read_paths")))
    for item in (contract.get("file_memory") if isinstance(contract.get("file_memory"), list) else []):
        if isinstance(item, dict):
            token = repo_path_token(item.get("path"))
            if token:
                known_paths_set.add(token)
            for path in item.get("mentioned_paths", []) if isinstance(item.get("mentioned_paths"), list) else []:
                token = repo_path_token(path)
                if token:
                    known_paths_set.add(token)
    operational_notes = contract.get("operational_notes") if isinstance(contract.get("operational_notes"), dict) else {}
    for item in operational_notes.get("read_notes", []) if isinstance(operational_notes.get("read_notes"), list) else []:
        if isinstance(item, dict):
            token = repo_path_token(item.get("path"))
            if token:
                known_paths_set.add(token)
            for path in item.get("mentioned_paths", []) if isinstance(item.get("mentioned_paths"), list) else []:
                token = repo_path_token(path)
                if token:
                    known_paths_set.add(token)
    known_paths = sorted(known_paths_set)
    admissible_reads = set(str(x) for x in _collect_repo_paths(contract.get("validator_admissible_repo_read_paths")))
    admissible_reads.update(_collect_repo_paths(contract.get("read_admissible_paths")))
    read_ok = [str(x) for x in contract.get("successful_repo_read_paths") or []]
    apply_contract = contract.get("apply_write_contract") if isinstance(contract.get("apply_write_contract"), dict) else {}
    apply_required = bool(contract.get("goal_requests_apply")) or bool(apply_contract.get("required"))
    apply_patch_applied = bool(apply_contract.get("patch_applied"))
    post_write_contract = contract.get("post_write_validation_contract") if isinstance(contract.get("post_write_validation_contract"), dict) else {}
    post_write_validation_required = bool(post_write_contract.get("required"))
    post_write_validation_done = bool(post_write_contract.get("validation_done"))
    post_write_validation_failed = bool(post_write_contract.get("validation_failed"))
    code_product_contract = contract.get("code_product_contract") if isinstance(contract.get("code_product_contract"), dict) else {}
    apply_read_targets = {
        _repo_rel_token(path)
        for path in [
            *(apply_contract.get("target_files") if isinstance(apply_contract.get("target_files"), list) else []),
            *(apply_contract.get("unread_target_files") if isinstance(apply_contract.get("unread_target_files"), list) else []),
            *(apply_contract.get("verified_target_reads") if isinstance(apply_contract.get("verified_target_reads"), list) else []),
        ]
        if _repo_rel_token(path)
    }
    user_scope_claims = contract.get("user_scope_claims") if isinstance(contract.get("user_scope_claims"), list) else []

    if action in {"final", "done", "complete", "completed"}:
        final_contract = contract.get("finalization_contract") if isinstance(contract.get("finalization_contract"), dict) else {}
        final_rewrite_latch = _coerce_final_rewrite_latch(contract.get("final_rewrite_latch"))

        final_forced_block_payload = final_contract.get("planner_forced_terminal_block")
        planner_forced_terminal_block = False
        planner_forced_terminal_block_reason = ""
        if isinstance(final_forced_block_payload, dict):
            planner_forced_terminal_block = bool(final_forced_block_payload.get("enabled"))
            planner_forced_terminal_block_reason = str(final_forced_block_payload.get("reason") or "").strip()
            final_contract["planner_forced_terminal_block"] = planner_forced_terminal_block
        else:
            planner_forced_terminal_block = bool(final_forced_block_payload is True)
            planner_forced_terminal_block_reason = str(
                final_contract.get("planner_forced_terminal_block_reason") or ""
            ).strip()
            final_contract["planner_forced_terminal_block"] = planner_forced_terminal_block
        contract["finalization_contract"] = final_contract

        planner_may_choose_block = bool(contract.get("planner_may_choose_block")) or bool(
            final_contract.get("planner_may_choose_block")
        )
        if (final_rewrite_latch == "terminal_block_required" and planner_may_choose_block) or planner_forced_terminal_block:
            violations.append("terminal_block_required_final_disallowed")
            contract["terminal_block_final_retry_count"] = int(contract.get("terminal_block_final_retry_count") or 0) + 1
            contract["planner_cuda_rewrite_required"] = True
            contract["final_rewrite_latch"] = "terminal_block_required"
            contract["planner_may_choose_final"] = False
            contract["planner_may_choose_block"] = True
            contract["required_next_progress"] = (
                "Terminal block lane is active after repeated final-quality rejection. "
                "Return action=block with the remaining blocker; do not emit another final."
            )
            final_contract["final_allowed"] = False
            final_contract["planner_may_choose_final"] = False
            final_contract["planner_may_choose_block"] = True
            final_contract["planner_forced_terminal_block"] = True
            final_contract["planner_forced_terminal_block_reason"] = (
                planner_forced_terminal_block_reason or "terminal_block_required_final_disallowed"
            )
            final_contract["reason"] = "terminal_block_required_final_disallowed"
            return {"ok": False, "violations": violations, "evidence_contract": contract}

        if final_contract and final_contract.get("final_allowed") is False:
            violations.append("final_not_allowed_by_evidence_contract:" + str(final_contract.get("reason") or "insufficient evidence"))
        if post_write_validation_required and not post_write_validation_done:
            violations.append(
                "final_after_write_validation_failed"
                if post_write_validation_failed else
                "final_after_write_without_validation"
            )
        final_answer = str(decision.get("final_answer") or decision.get("answer") or decision.get("summary") or "")
        coverage_required = _minimum_read_coverage_required()
        coverage_satisfied = _minimum_read_coverage_satisfied()
        missing_owner_paths = _minimum_read_coverage_missing_owner_paths()
        if coverage_required and not coverage_satisfied:
            violations.append("final_without_minimum_read_coverage")
            contract["required_next_progress"] = (
                "coverage_required: minimum_read_coverage.coverage_satisfied=false. "
                "Read/search the missing owner/core paths or return a typed block; do not final."
            )
            contract["coverage_block"] = {
                "schema": "minimum_read_coverage.block.v1",
                "coverage_satisfied": False,
                "missing_owner_paths": missing_owner_paths,
            }
            if isinstance(final_contract, dict):
                final_contract["final_allowed"] = False
                final_contract["planner_may_choose_final"] = False
                final_contract["coverage_satisfied"] = False
                final_contract["missing_owner_paths"] = missing_owner_paths
                contract["finalization_contract"] = final_contract
            contract["planner_may_choose_final"] = False
        if _final_answer_declares_missing_coverage(final_answer):
            violations.append("final_declares_missing_read_coverage")
        code_product_contract = contract.get("code_product_contract") if isinstance(contract.get("code_product_contract"), dict) else {}
        action_plan_candidate = ""
        if code_product_contract.get("required"):
            if _final_answer_is_action_plan_without_code_product(final_answer):
                violations.append("final_action_plan_without_code_product")
                action_plan_candidate = final_answer
            verified_rows = contract.get("verified_content_reads") if isinstance(contract.get("verified_content_reads"), list) else []
            verified_paths = {
                _repo_rel_token(row.get("path"))
                for row in verified_rows
                if isinstance(row, dict) and row.get("path")
            }
            successful_code_edit_proposals = deps["successful_code_edit_proposals"]
            proposals = successful_code_edit_proposals(history)
            if not proposals:
                violations.append("missing_code_product_candidate")
            else:
                violations.extend(_code_product_payload_violations(proposals[-1], verified_paths))
        if target_kind == "file" and target_file:
            if target_file not in read_ok:
                violations.append(f"final_without_requested_file_read:{target_file}")
        if target_scope:
            listed_rows = contract.get("repo_list_files_evidence") if isinstance(contract.get("repo_list_files_evidence"), list) else []
            scope_listed = bool(contract.get("latest_in_scope_repo_list_path")) or any(
                _path_under_scope(str(row.get("path") or ""), target_scope)
                and str(row.get("path") or ".") not in ("", ".")
                for row in listed_rows if isinstance(row, dict)
            )
            scope_reads = [
                p for p in read_ok
                if _path_under_scope(p, target_scope)
                and _repo_readable_evidence_file(p)
            ]
            final_allowed = bool(final_contract.get("final_allowed")) if isinstance(final_contract, dict) else False
            if final_allowed and not scope_listed:
                internal_inconsistencies.append(f"quality_gate_internal_inconsistency:scope_listed_missing:{target_scope}")
            if final_allowed and not scope_reads:
                internal_inconsistencies.append(f"quality_gate_internal_inconsistency:scope_reads_missing:{target_scope}")
            if not scope_listed and not final_allowed:
                violations.append(f"final_without_in_scope_tree_or_list:{target_scope}")
            if not scope_reads and not final_allowed:
                violations.append(f"final_without_in_scope_concrete_read:{target_scope}")
        if (effective_repo_goal or semantic_audit_goal) and not final_answer.strip():
            violations.append("final_empty_answer")
        elif effective_repo_goal or semantic_audit_goal:
            deterministic_quality = _repo_analysis_final_answer_quality(final_answer, contract)
            contract["repo_analysis_final_deterministic_quality"] = deterministic_quality
            deterministic_violations = (
                deterministic_quality.get("violations")
                if isinstance(deterministic_quality.get("violations"), list)
                else []
            )
            if deterministic_violations:
                violations.extend(str(v) for v in deterministic_violations)
                _apply_final_quality_route(deterministic_quality)
            if callable(_repo_analysis_final_answer_model_quality):
                quality = _repo_analysis_final_answer_model_quality(
                    final_answer,
                    contract,
                    goal=goal,
                    history=history,
                )
            else:
                quality = {
                    "schema": "repo_analysis_final_model_quality.v1",
                    "model_decision_available": False,
                    "ok": False,
                    "decision": "invalid",
                    "violations": ["repo_analysis_final_model_quality_dependency_missing"],
                    "required_next_progress": (
                        "Final answer rejected because repo-analysis final quality has no model judge dependency. "
                        "Do not accept this final through deterministic heuristics."
                    ),
                }
            quality_violations = (
                quality.get("violations")
                if isinstance(quality.get("violations"), list)
                else []
            )
            contract["repo_analysis_final_quality"] = quality
            if quality_violations:
                violations.extend(str(v) for v in quality_violations)
                _apply_final_quality_route(quality if isinstance(quality, dict) else {})
        if review_goal and not read_ok:
            violations.append("final_without_successful_repo_read_for_python_review")
        if review_goal and target_scope and any(not _path_under_scope(p, target_scope) for p in read_ok):
            violations.append(f"final_uses_read_paths_outside_requested_scope:{target_scope}")
        if review_goal and requested_limit:
            expected = requested_limit
            latest_list = latest_file_list_result(history)
            total_matches = latest_list.get("total_matches") if isinstance(latest_list, dict) else None
            if isinstance(total_matches, int) and total_matches > 0:
                expected = min(expected, total_matches)
            if len(read_ok) < expected:
                violations.append(f"final_before_required_read_count:{len(read_ok)}/{expected}")
        if not violations:
            contract = _clear_final_terminal_block_state(contract)
        result = {
            "ok": not violations,
            "violations": violations,
            "evidence_contract": contract,
            "quality_gate_internal_inconsistency": internal_inconsistencies,
            "coverage_satisfied": _minimum_read_coverage_satisfied(),
            "missing_owner_paths": _minimum_read_coverage_missing_owner_paths(),
        }
        if action_plan_candidate:
            result["action_plan_candidate"] = action_plan_candidate
            result["semantic_goal_classification"] = contract.get("semantic_goal_classification")
        if isinstance(contract.get("required_next_tool_call"), dict):
            result["required_next_tool_call"] = contract["required_next_tool_call"]
        return result

    if action in {"block", "blocked", "need_user", "needs_user"}:
        # Planner-format failures are not accepted as a final loop result before
        # the controller classifies them. Plain terminal text is wrapped as a
        # final candidate in the turn owner; malformed JSON/tool-shaped output
        # stays rejected. The controller still does not invent a substitute tool.
        reason = str(decision.get("reason") or "")
        reason_low = reason.lower()
        if reason == "planner_final_required_empty_output":
            violations.append("planner_final_required_empty_output")
            contract["required_next_progress"] = (
                "Quality gate is satisfied and no tool surface was provided. "
                "Return a terminal final answer. Do not call tools."
            )
            return {"ok": False, "violations": violations, "evidence_contract": contract}
        if reason == "planner_native_tool_call_required":
            violations.append("planner_native_tool_call_required")
            contract["required_next_progress"] = (
                "Native tool mode is active and the planner emitted no message.tool_calls. "
                "Retry with one native tool_call from candidate_next_actions or return a real "
                "final/block answer when the evidence contract allows it."
            )
            return {"ok": False, "violations": violations, "evidence_contract": contract}
        if reason == "planner_native_mode_non_json_output":
            violations.append("planner_native_mode_non_json_output")
            contract["required_next_progress"] = (
                "Native tool mode is active and the planner emitted malformed protocol-shaped "
                "text. Retry with one native tool_call from candidate_next_actions, or return "
                "a terminal final/block answer when the evidence contract allows it."
            )
            return {"ok": False, "violations": violations, "evidence_contract": contract}
        raw_planner_text = str(
            decision.get("raw_planner_text")
            or decision.get("raw_planner_text_preview")
            or decision.get("partial_content")
            or ""
        )
        if raw_planner_text and (
            "invalid_planner_output_non_json" in reason_low
            or "non-json" in reason_low
            or "no_json" in reason_low
            or "degenerate" in reason_low
            or "timeout" in reason_low
            or reason.startswith("PLANNER_DEGENERATE_OUTPUT")
        ):
            violations.append("planner_block_requires_controller_classification:" + reason[:160])
            return {"ok": False, "violations": violations, "evidence_contract": contract}
        final_contract = (
            contract.get("finalization_contract")
            if isinstance(contract.get("finalization_contract"), dict)
            else {}
        )
        final_forced_block_payload = final_contract.get("planner_forced_terminal_block")
        planner_forced_terminal_block = False
        planner_forced_terminal_block_reason = ""
        if isinstance(final_forced_block_payload, dict):
            planner_forced_terminal_block = bool(final_forced_block_payload.get("enabled"))
            planner_forced_terminal_block_reason = str(final_forced_block_payload.get("reason") or "").strip()
            final_contract["planner_forced_terminal_block"] = planner_forced_terminal_block
        else:
            planner_forced_terminal_block = bool(final_forced_block_payload is True)
            planner_forced_terminal_block_reason = str(
                final_contract.get("planner_forced_terminal_block_reason") or ""
            ).strip()
            final_contract["planner_forced_terminal_block"] = planner_forced_terminal_block
        contract["finalization_contract"] = final_contract
        planner_may_choose_block = bool(contract.get("planner_may_choose_block")) or bool(
            final_contract.get("planner_may_choose_block")
        )
        block_override_reason = (
            planner_forced_terminal_block_reason
            if planner_forced_terminal_block and planner_forced_terminal_block_reason
            else "planner_forced_terminal_block"
        )
        if planner_forced_terminal_block:
            contract["planner_may_choose_block"] = True
            if block_override_reason and not contract.get("required_next_progress"):
                contract["required_next_progress"] = (
                    "Controller-forced terminal block is active: "
                    f"{block_override_reason}. Consume and pass through this terminal signal."
                )
            return {"ok": True, "violations": [], "evidence_contract": contract}
        if not planner_may_choose_block:
            final_quality_reject_count = int(contract.get("planner_final_quality_reject_count") or 0)
            coverage_required = _minimum_read_coverage_required()
            coverage_satisfied = _minimum_read_coverage_satisfied()
            coverage_missing = _minimum_read_coverage_missing_owner_paths()
            required_tool = ""
            required_next_tool_call = contract.get("required_next_tool_call")
            if isinstance(required_next_tool_call, dict):
                required_tool = str(required_next_tool_call.get("tool") or "").strip()
            coverage_progress = (
                f"Block is not authorized after {final_quality_reject_count} final-quality reject"
                f"{'s' if final_quality_reject_count != 1 else ''}; "
                "provide rewrite evidence before terminal."
            )
            final_rewrite_latch = _coerce_final_rewrite_latch(contract.get("final_rewrite_latch"))
            if required_tool:
                coverage_progress = (
                    "Block is not authorized by evidence contract while required_next_tool_call is pending. "
                    f"Required tool: {required_tool}. "
                    "Either execute the required tool path or return final only when final is explicitly allowed."
                )
            elif coverage_required and not coverage_satisfied:
                coverage_progress = (
                    "Block is not authorized by evidence contract because minimum read coverage is not satisfied; "
                    f"missing_owner_paths={coverage_missing[:12]}."
                )
            elif final_rewrite_latch:
                coverage_progress = (
                    "Block is not authorized by evidence contract while a final-rewrite/deadlock lane is active; "
                    f"required_next_progress: {str(contract.get('required_next_progress') or '')[:180] or 'resolve remaining lane'}. "
                    "Resume rewrite using verified evidence and required evidence gaps."
                )
            violations.append("block_not_allowed_by_evidence_contract")
            contract["required_next_progress"] = coverage_progress
            return {"ok": False, "violations": violations, "evidence_contract": contract}
        return {"ok": True, "violations": [], "evidence_contract": contract}

    if action != "tool":
        violations.append(f"invalid_action:{action or '<empty>'}")
        return {"ok": False, "violations": violations, "evidence_contract": contract}

    if not tool:
        violations.append("missing_tool")
        return {"ok": False, "violations": violations, "evidence_contract": contract}

    if tool not in VALID_INTERNAL_TOOLS:
        violations.append(f"invalid_tool:{tool}")
        return {"ok": False, "violations": violations, "evidence_contract": contract}

    if _contract_final_required_now(contract) and not prompt_context_continuation_matches:
        final_composition_tools = _final_composition_tool_names_from_candidates(contract)
        if tool not in SUPPORT_SUBTURN_TOOLS and tool not in final_composition_tools:
            violations.append("final_required_tool_call_disallowed")
            contract["required_next_progress"] = (
                "Quality gate is satisfied. The required next action is action=final. "
                "Do not call repo tools, validation tools, command tools or other external "
                "progress tools. Planner support primitives such as scratchpad, prompt windows "
                "and runtime memory remain allowed when their arguments pass validation."
            )

    final_reject_count = int(contract.get("planner_final_quality_reject_count") or 0)
    final_rewrite_latch = _coerce_final_rewrite_latch(contract.get("final_rewrite_latch"))
    rewrite_active = final_rewrite_latch != "inactive" and final_reject_count >= 1
    if rewrite_active:
        required_tool_call = contract.get("required_next_tool_call")
        if isinstance(required_tool_call, dict):
            required_tool = str(required_tool_call.get("tool") or "").strip()
        required_missing = contract.get("required_next_missing_evidences")
        required_tool = str(required_tool_call.get("tool") or "").strip()
        required_rewrite_paths = []
        if required_tool == "repo_read":
            args = required_tool_call.get("arguments") if isinstance(required_tool_call.get("arguments"), dict) else {}
            for raw_path in (args.get("paths", []) if isinstance(args.get("paths"), list) else []):
                path = _repo_rel_token(raw_path)
                if path:
                    required_rewrite_paths.append(path)
            if not required_rewrite_paths:
                path = _repo_rel_token(args.get("path"))
                if path:
                    required_rewrite_paths.append(path)
        if not required_tool_call and not required_tool:
            violations.append("tool_not_allowed_in_post_final_reject_rewrite_lane")
            contract["required_next_progress"] = (
                "Rewrite lane requires a concrete required_next_tool_call, but it has no tool or path arguments."
            )
            return {"ok": False, "violations": violations, "evidence_contract": contract}

        if tool != required_tool:
            if tool in SUPPORT_SUBTURN_TOOLS:
                if not (prompt_context_continuation_required and prompt_context_continuation_matches):
                    violations.append("support_subturn_validation_failed")
                    contract["support_subturn_rewrite_retry_count"] = int(
                        contract.get("support_subturn_rewrite_retry_count") or 0
                    ) + 1
                    if contract["support_subturn_rewrite_retry_count"] >= 2:
                        contract["final_rewrite_latch"] = "terminal_block_required"
                        contract["planner_may_choose_block"] = True
                        contract["planner_may_choose_final"] = False
                        contract["required_next_tool_call"] = {}
                        contract.pop("required_next_tool_call_validated", None)
                        contract.pop("required_next_tool_call_validation_source", None)
                        contract["required_next_progress"] = (
                            "Rewrite lane support-subturn loop detected. Return a rewritten terminal final "
                            "from verified evidence, or explicit block with remaining evidence gaps."
                        )
                    else:
                        contract["required_next_progress"] = (
                            f"Rewrite lane requires {required_tool} as the next tool, "
                            "or a rewritten final."
                        )
                    return {"ok": False, "violations": violations, "evidence_contract": contract}
            violations.append("tool_not_allowed_in_post_final_reject_rewrite_lane")
            contract["required_next_progress"] = (
                f"Rewrite lane requires {required_tool} before terminal action."
            )
            return {"ok": False, "violations": violations, "evidence_contract": contract}

        if required_tool == "repo_read":
            decision_paths = [_repo_rel_token(item) for item in _decision_paths(args) if _repo_rel_token(item)]

            def _matches_rewrite_gap(path: str) -> bool:
                if not required_missing:
                    return path in required_rewrite_paths
                for gap in required_rewrite_paths:
                    if (
                        path == gap
                        or path.startswith(f"{gap}/")
                        or gap.startswith(f"{path}/")
                    ) and _path_allowed_by_missing_evidence(path, required_missing):
                        return True
                return False

            if not decision_paths:
                violations.append("repo_read_not_allowed_post_final_reject_without_gap_match")
                contract["required_next_progress"] = (
                    "Rewrite lane requires repo_read on the remaining required missing path(s), "
                    f"{required_rewrite_paths}"
                )
            else:
                for path in decision_paths:
                    if not _matches_rewrite_gap(path):
                        violations.append(f"repo_read_not_allowed_post_final_reject_without_gap_match:{path}")
                if not violations:
                    pass
            if not violations and contract.get("final_rewrite_latch") == "terminal_block_required":
                contract["planner_may_choose_block"] = True
            if required_missing and not violations:
                required_tool_call["validated"] = True
                required_tool_call["validation_source"] = "deterministic_validator"
                contract["required_next_tool_call"] = required_tool_call
                contract["required_next_tool_call_validated"] = True
                contract["required_next_tool_call_validation_source"] = "deterministic_validator"
            elif required_rewrite_paths and not violations:
                required_tool_call["validated"] = True
                required_tool_call["validation_source"] = "deterministic_validator"
                contract["required_next_tool_call"] = required_tool_call
                contract["required_next_tool_call_validated"] = True
                contract["required_next_tool_call_validation_source"] = "deterministic_validator"
            elif not required_rewrite_paths and not violations:
                violations.append("repo_read_not_allowed_without_required_next_paths")
                contract.pop("required_next_tool_call_validated", None)
                contract.pop("required_next_tool_call_validation_source", None)
                contract["required_next_progress"] = (
                    "Rewrite lane requires a concrete required_next_tool_call, but it has no path arguments."
                )

    if tool == "repo_search" and not _any_argument_group_present(args, [["query"], ["pattern"], ["symbol"]]):
        violations.append("repo_search_missing_query_pattern_or_symbol")
    elif tool == "repo_semantic_search" and not _argument_value_present(args, "query"):
        violations.append("repo_semantic_search_missing_query")
    elif tool == "repo_rg_search" and not _any_argument_group_present(args, [["query"], ["pattern"]]):
        violations.append("repo_rg_search_missing_pattern")
    elif tool == "repo_jq_query" and not _any_argument_group_present(args, [["query"], ["filter"]]):
        violations.append("repo_jq_query_missing_query")
    elif tool == "repo_ast_grep_search" and not _any_argument_group_present(args, [["pattern"], ["kind"]]):
        violations.append("repo_ast_grep_search_missing_pattern_or_kind")
    elif tool == "repo_ast_grep_dry_run" and not _any_argument_group_present(args, [["pattern", "rewrite"]]):
        violations.append("repo_ast_grep_dry_run_missing_pattern_or_rewrite")
    elif tool == "repo_tree_sitter_parse" and not _argument_value_present(args, "path"):
        violations.append("repo_tree_sitter_parse_missing_path")
    elif tool == "repo_unidiff_validate" and not _any_argument_group_present(args, [["unified_diff"], ["diff"]]):
        violations.append("repo_unidiff_validate_missing_diff")
    elif tool == "repo_git_apply_check" and not _any_argument_group_present(args, [["unified_diff"], ["diff"], ["patch"]]):
        violations.append("repo_git_apply_check_missing_diff")
    elif tool == "repo_shellcheck" and not _any_argument_group_present(args, [["path"], ["paths"]]):
        violations.append("repo_shellcheck_missing_path")
    elif tool == "repo_semgrep_scan" and not _any_argument_group_present(args, [["pattern"], ["config"]]):
        violations.append("repo_semgrep_scan_missing_pattern_or_config")
    elif tool == "repo_hyperfine_benchmark" and not _argument_value_present(args, "commands"):
        violations.append("repo_hyperfine_benchmark_missing_commands")
    elif tool == "repo_read" and not _repo_read_selector_present(args):
        violations.append("repo_read_missing_path_or_paths_items")
    elif tool == "planner_scratchpad_write" and not _any_argument_group_present(args, [["text"], ["content"]]):
        violations.append("planner_scratchpad_write_missing_text")
    elif tool == "planner_scratchpad_read" and not _planner_scratchpad_read_selector_present(args):
        violations.append("planner_scratchpad_read_missing_selector")
    elif tool == "runtime_sqlite_memory_search" and not _any_argument_group_present(args, [["query"], ["tag"], ["kind"]]):
        violations.append("runtime_sqlite_memory_search_missing_query_tag_or_kind")
    elif tool == "runtime_sqlite_memory_write" and not _any_argument_group_present(args, [["text"], ["content"]]):
        violations.append("runtime_sqlite_memory_write_missing_text")
    elif tool == "terminal_search_files" and not _argument_value_present(args, "query"):
        violations.append("terminal_search_files_missing_query")
    elif tool == "terminal_run_command_wait" and not _argument_value_present(args, "command"):
        violations.append("terminal_run_command_wait_missing_command")
    elif tool == "repo_command" and not _argument_value_present(args, "command"):
        violations.append("repo_command_missing_command")
    if tool == "planner_scratchpad_write":
        kind = str(args.get("kind") or "").strip()
        text = str(args.get("text") or args.get("content") or "")
        if kind in {"answer_chunk", "final_answer_chunk"}:
            final_composition_tools = _final_composition_tool_names_from_candidates(contract)
            if tool not in final_composition_tools:
                violations.append("planner_answer_chunk_without_final_composition_contract")
            if _answer_chunk_misuses_terminal_payload_shape(text):
                violations.append("planner_answer_chunk_tool_misused_for_terminal_payload")
            tag = str(args.get("tag") or "").strip()
            if tag and f"{kind}:{tag}" in _successful_answer_chunk_signatures():
                violations.append("planner_answer_chunk_tag_already_written_without_progress")
    if violations:
        return {"ok": False, "violations": violations, "evidence_contract": contract}

    if tool == "planner_scratchpad_write" and str(args.get("kind") or "") == CODE_PRODUCT_BUILD_STATE_KIND:
        if not code_product_contract.get("required"):
            violations.append("code_product_build_state_write_outside_code_product_contract")
        state_text = str(args.get("text") or args.get("content") or "")
        state = _code_product_build_state_parse(state_text)
        if not state:
            violations.append("code_product_build_state_invalid_payload")
        else:
            state_target = _repo_rel_token(args.get("target_file") or args.get("path") or state.get("target_file") or "")
            if not state_target or state_target == ".":
                violations.append("code_product_build_state_missing_target")
            elif state_target not in set(read_ok):
                violations.append(f"code_product_build_state_target_not_read:{state_target}")
            status = str(state.get("status") or "")
            if status not in {"collecting_source", "ready_for_propose", "blocked_incomplete"}:
                violations.append("code_product_build_state_invalid_status")
            if status == "collecting_source" and not _code_product_build_state_has_collecting_progress(state):
                violations.append("code_product_build_state_collecting_source_without_progress")
            if _code_product_build_state_duplicate_write(history, target_file=state_target, text=state_text):
                violations.append("code_product_build_state_duplicate_without_progress")
            if status == "ready_for_propose" and not _code_product_build_state_ready_payload(state):
                violations.append("code_product_build_state_ready_without_complete_payload")
            if status == "blocked_incomplete" and not str(state.get("blocker") or "").strip():
                violations.append("code_product_build_state_blocked_without_blocker")
        if violations:
            return {"ok": False, "violations": violations, "evidence_contract": contract}

    target_scope = _agentic_v2_goal_scope(str(goal or ""), contract)
    if target_scope and tool in {
        "repo_list_files",
        "repo_fd_files",
        "repo_rg_search",
        "repo_ast_grep_search",
        "repo_ast_grep_dry_run",
        "repo_tree_sitter_parse",
        "repo_ctags_symbols",
        "repo_semgrep_scan",
        "repo_shellcheck",
        "repo_validate",
        "repo_ruff_check",
        "repo_pyright_check",
        "repo_pytest_run",
        "repo_read",
        "repo_search",
        "repo_semantic_search",
        "repo_write_file",
        "repo_apply_patch",
        "repo_propose_code_edit",
    }:
        out_of_scope = [
            p for p in _agentic_v2_decision_paths(tool, args)
            if p and not _path_under_scope(p, target_scope)
        ]
        if out_of_scope:
            for p in out_of_scope[:5]:
                violations.append(f"{tool}_scope_mismatch:path={p}:expected_under={target_scope}")
            return {"ok": False, "violations": violations, "evidence_contract": contract}

    if tool == "repo_read":
        final_reject_count = int(contract.get("planner_final_quality_reject_count") or 0)
        final_rewrite_latch = _coerce_final_rewrite_latch(contract.get("final_rewrite_latch"))
        rewrite_only = final_rewrite_latch != "inactive" and final_reject_count >= 1
        if rewrite_only:
            required_tool_call = contract.get("required_next_tool_call")
            required_tool = str(required_tool_call.get("tool") or "").strip()
            required_missing = contract.get("required_next_missing_evidences")
            decision_paths = [_repo_rel_token(item) for item in _decision_paths(args) if _repo_rel_token(item)]
            if required_tool and required_tool != "repo_read":
                violations.append("repo_read_not_allowed_post_final_reject_without_explicit_repo_read_gap")
            elif required_missing:
                for path in decision_paths:
                    if not _path_allowed_by_missing_evidence(path, required_missing):
                        violations.append(f"repo_read_not_allowed_without_gap_match:{path}")
            else:
                if final_rewrite_latch in {"rewrite_required", "required_gap_only"}:
                    violations.append("repo_read_not_allowed_post_final_reject_without_explicit_repo_read_gap")
                else:
                    violations.append("repo_read_disallowed_post_final_reject_without_missing_gap")
            if violations:
                return {"ok": False, "violations": violations, "evidence_contract": contract}
        window_signature = _repo_read_window_signature(args)
        if window_signature and window_signature in _successful_window_signatures(history, "repo_read"):
            violation = "repo_read_window_already_successful_without_progress"
            violations.append(violation)
            contract = _apply_duplicate_window_replan_contract(
                contract,
                violation=violation,
                tool=tool,
                args=args,
                history=history,
            )
            return {"ok": False, "violations": violations, "evidence_contract": contract}

    if tool == "planner_scratchpad_read":
        window_signature = _planner_scratchpad_window_signature(args)
        if window_signature and window_signature in _successful_window_signatures(history, "planner_scratchpad_read"):
            violation = "planner_scratchpad_window_already_successful_without_progress"
            violations.append(violation)
            contract = _apply_duplicate_window_replan_contract(
                contract,
                violation=violation,
                tool=tool,
                args=args,
                history=history,
            )
            return {"ok": False, "violations": violations, "evidence_contract": contract}

    if tool == "repo_read" and not _agentic_v2_read_has_window(args):
        already_read = set(_agentic_v2_successful_read_paths(history))
        repeated_reads = [p for p in _agentic_v2_decision_paths(tool, args) if p in already_read]
        if repeated_reads:
            violations.append("repo_read_already_successful:" + ",".join(repeated_reads[:5]))
            contract = _apply_duplicate_repo_read_path_recovery_contract(
                contract,
                repeated_reads=repeated_reads,
                history=history,
            )
            return {"ok": False, "violations": violations, "evidence_contract": contract}

    if tool == "repo_list_files":
        path = _repo_rel_token(args.get("path") or ".")
        suffix = str(args.get("suffix") or args.get("glob") or "")
        if not _path_exists_repo_relative(path):
            violations.append(f"non_existing_path:{path}")
        if _repo_path_kind(path) == "file":
            violations.append(f"repo_list_files_on_file_path_use_repo_read:{path}")
        if target_scope and not _path_under_scope(path, target_scope):
            violations.append(f"repo_list_files_scope_mismatch:path={path}:expected_under={target_scope}")
        if review_goal and requested_limit:
            try:
                limit = int(args.get("limit") or args.get("max_files") or 0)
            except Exception:
                limit = 0
            if limit != requested_limit:
                violations.append(f"repo_list_files_limit_mismatch:got={limit or '<missing>'}:expected={requested_limit}")
        if review_goal and suffix and ".py" not in suffix and "*.py" not in suffix:
            violations.append(f"repo_list_files_suffix_not_python:{suffix}")
        if review_goal and target_file and not _path_under_scope(target_file, target_scope):
            violations.append(f"repo_list_files_target_file_outside_scope:{target_file}:expected_under={target_scope}")
        if repeated_tool_call_count(history, tool, args) >= 1 and known_paths:
            violations.append("repeated_repo_list_files_after_useful_file_list")

    if tool == "repo_tree" and repeated_tool_call_count(history, tool, args) >= 1:
        violations.append("repeated_same_tool_arguments_without_progress")

    if tool in {"repo_read", "repo_apply_patch", "repo_write_file", "repo_propose_code_edit"}:
        paths = _decision_paths(args)
        if tool == "repo_apply_patch" and args.get("path"):
            paths = [str(args.get("path"))]
        if tool == "repo_propose_code_edit" and (args.get("target_file") or args.get("path")):
            paths = [_repo_rel_token(args.get("target_file") or args.get("path"))]
        if not paths:
            if tool == "repo_read":
                violations.append("repo_read_missing_path_or_paths_items")
            else:
                violations.append(f"{tool}_missing_path_or_paths")
        for path in paths:
            path = _repo_rel_token(path)
            if target_scope and tool == "repo_read" and not _path_under_scope(path, target_scope):
                violations.append(f"repo_read_path_outside_requested_scope:{path}:expected_under={target_scope}")
            if tool == "repo_read" and apply_required and not apply_patch_applied:
                if not apply_read_targets:
                    violations.append(f"repo_read_not_allowed_without_apply_targets:{path}")
                elif path not in apply_read_targets:
                    violations.append(f"repo_read_outside_apply_write_targets:{path}")
            if tool == "repo_read" and known_paths and path not in known_paths and path not in admissible_reads:
                # Existing files are valid only if they have been discovered in tree/list evidence.
                violations.append(f"repo_read_path_not_from_prior_file_evidence:{path}")
                contract = _escalate_final_terminal_block_state(
                    contract,
                    has_gap_route=bool(
                        contract.get("required_next_tool_call")
                        or contract.get("required_next_missing_evidences")
                    ),
                )
            if tool in {"repo_read", "repo_apply_patch", "repo_propose_code_edit"} and not _path_exists_repo_relative(path):
                violations.append(f"non_existing_path:{path}")
            if tool == "repo_apply_patch":
                old_value = args.get("old_text")
                new_value = args.get("new_text")
                if _copyable_example_text(old_value) or _copyable_example_text(new_value):
                    violations.append("repo_apply_patch_placeholder_text")
                    contract = _apply_unverified_old_text_replan_contract(
                        contract,
                        target_file=path,
                        violation="repo_apply_patch_placeholder_text",
                        history=history,
                    )
                elif isinstance(old_value, str) and old_value and not _old_text_verified_by_repo_read(history, path, old_value):
                    violations.append("repo_apply_patch_old_text_not_from_verified_read")
                    contract = _apply_unverified_old_text_replan_contract(
                        contract,
                        target_file=path,
                        violation="repo_apply_patch_old_text_not_from_verified_read",
                        history=history,
                    )
            if tool == "repo_propose_code_edit" and path not in set(read_ok):
                violations.append(f"code_product_target_not_read:{path}")
            if tool == "repo_propose_code_edit":
                claim_conflict = _scope_claim_conflict_for_path(path, user_scope_claims)
                if claim_conflict and not _target_scope_conflict_resolved(path, args, contract):
                    if "target_scope_conflict_unresolved" not in violations:
                        violations.append("target_scope_conflict_unresolved")
            if (
                tool == "repo_propose_code_edit"
                and not target_file
                and goal_requires_code_product_report(goal)
                and _code_product_low_signal_target(path, contract)
            ):
                violations.append(f"code_product_low_signal_target:{path}")
        if tool == "repo_propose_code_edit":
            edit_kind = str(args.get("edit_kind") or "")
            if edit_kind not in {"unified_diff", "structured_edit", "no_op"}:
                violations.append("repo_propose_code_edit_invalid_edit_kind")
            if not str(args.get("rationale") or "").strip():
                violations.append("repo_propose_code_edit_missing_rationale")
            if edit_kind == "unified_diff":
                diff_text = args.get("unified_diff")
                if not isinstance(diff_text, str) or not diff_text.strip():
                    old_value = args.get("old_text")
                    new_value = args.get("new_text")
                    if not (isinstance(old_value, str) and isinstance(new_value, str)):
                        violations.append("repo_propose_code_edit_missing_unified_diff")
                        if repeated_tool_call_count(history, tool, args) >= 1:
                            violations.append("code_product_route_shift_required")
                    elif _copyable_example_text(old_value) or _copyable_example_text(new_value):
                        violations.append("repo_propose_code_edit_placeholder_text")
                        if paths:
                            contract = _apply_unverified_old_text_replan_contract(
                                contract,
                                target_file=paths[0],
                                violation="repo_propose_code_edit_placeholder_text",
                                history=history,
                            )
                        if repeated_tool_call_count(history, tool, args) >= 1:
                            violations.append("code_product_route_shift_required")
                    elif paths and not _old_text_verified_by_repo_read(history, paths[0], old_value):
                        violations.append("repo_propose_code_edit_old_text_not_from_verified_read")
                        contract = _apply_unverified_old_text_replan_contract(
                            contract,
                            target_file=paths[0],
                            violation="repo_propose_code_edit_old_text_not_from_verified_read",
                            history=history,
                        )
                        if repeated_tool_call_count(history, tool, args) >= 1:
                            violations.append("code_product_route_shift_required")
                else:
                    diff_errors = validate_unified_diff_text(
                        unified_diff=diff_text,
                        target_file=paths[0] if paths else str(args.get("target_file") or args.get("path") or ""),
                        require_unidiff=True,
                    )
                    blocking_diff_errors = [
                        str(error)
                        for error in diff_errors
                        if str(error) != "unidiff_dependency_missing"
                    ]
                    if blocking_diff_errors:
                        violations.append("invalid_code_product_candidate")
                        violations.extend(
                            f"repo_propose_code_edit_unified_diff_error:{error}"
                            for error in blocking_diff_errors[:6]
                        )
                        if repeated_tool_call_count(history, tool, args) >= 1:
                            violations.append("code_product_route_shift_required")
            if edit_kind == "structured_edit" and not isinstance(args.get("structured_operations"), list):
                violations.append("repo_propose_code_edit_missing_structured_operations")
                if repeated_tool_call_count(history, tool, args) >= 1:
                    violations.append("code_product_route_shift_required")
            if edit_kind == "no_op" and (
                args.get("unified_diff")
                or args.get("structured_operations")
                or args.get("old_text")
                or args.get("new_text")
            ):
                violations.append("repo_propose_code_edit_no_op_has_patch_payload")

    if repeated_tool_call_count(history, tool, args) >= 2:
        violations.append("repeated_same_tool_arguments_without_progress")

    invalid_signature = _canonical_invalid_code_product_decision_signature(decision, violations)
    invalid_repeat_count = _invalid_code_product_decision_signature_count(history, invalid_signature)
    if invalid_signature:
        code_contract = contract.get("code_product_contract") if isinstance(contract.get("code_product_contract"), dict) else {}
        code_contract["latest_invalid_decision_signature"] = invalid_signature
        code_contract["latest_invalid_decision_repeat_count"] = invalid_repeat_count + 1
        if invalid_repeat_count >= 1:
            raw_disallowed = contract.get("disallowed_next_decision_signatures")
            disallowed = [
                item for item in (raw_disallowed if isinstance(raw_disallowed, list) else [])
                if isinstance(item, dict)
            ]
            disallowed_entry = {
                **invalid_signature,
                "repeat_count": invalid_repeat_count + 1,
                "rule": "do_not_repeat_invalid_code_product_decision",
            }
            if _invalid_decision_signature_key(invalid_signature) not in {
                _invalid_decision_signature_key(item) for item in disallowed
            }:
                disallowed.append(disallowed_entry)
            contract["disallowed_next_decision_signatures"] = disallowed
            code_contract["disallowed_next_decision_signatures"] = disallowed
        if invalid_repeat_count >= 2 and "planner_repeated_invalid_code_product_decision" not in violations:
            violations.append("planner_repeated_invalid_code_product_decision")
            code_contract["terminal_blocker"] = "planner_repeated_invalid_code_product_decision"
        contract["code_product_contract"] = code_contract

    response = {"ok": not violations, "violations": violations, "evidence_contract": contract}
    if invalid_signature:
        response["invalid_decision_signature"] = invalid_signature
        response["invalid_decision_repeat_count"] = invalid_repeat_count + 1
    return response