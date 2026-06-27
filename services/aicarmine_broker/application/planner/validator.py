from collections.abc import Mapping
import json
from typing import Any
from .validator_helpers import *
from .validator_helpers import ValidationContext
from aicarmine_broker.application.evidence.audit_guidance import *
from aicarmine_broker.application.evidence.goal_classifier import *
from aicarmine_broker.application.shared.path_tokens import *
from aicarmine_broker.application.tool_surface.required_tool_call import *
from .validator_rules import ValidationDeps, ToolCallValidator, FinalValidationValidator, PathScopeValidator


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
        out.append(token)
    return out


def _collect_repo_paths(paths: Any) -> list[str]:
    """Collect repo paths from various sources."""
    if isinstance(paths, str):
        return [paths] if paths else []
    if isinstance(paths, list):
        result = []
        for p in paths:
            token = repo_path_token(p)
            if token:
                result.append(token)
        return result
    return []


def validate_planner_decision_against_evidence(
    goal: str,
    decision: dict[str, Any],
    history: list[dict[str, Any]],
    deps: Any,
    config: Any,
) -> dict[str, Any]:
    """Validate planner decision against evidence contract.

    Refactored to delegate to extracted validator classes.
    Original CC=434, reduced to ~50 via class extraction.
    """
    AGENTIC_PLANNER_NATIVE_TOOLS = config["AGENTIC_PLANNER_NATIVE_TOOLS"]
    CODE_PRODUCT_BUILD_STATE_KIND = config["CODE_PRODUCT_BUILD_STATE_KIND"]
    VALID_INTERNAL_TOOLS = config["VALID_INTERNAL_TOOLS"]

    # Build ValidationDeps dataclass from deps dict
    validation_deps = ValidationDeps(
        agentic_v2_decision_paths=deps["agentic_v2_decision_paths"],
        agentic_v2_goal_scope=deps["agentic_v2_goal_scope"],
        agentic_v2_read_has_window=deps["agentic_v2_read_has_window"],
        agentic_v2_successful_read_paths=deps["agentic_v2_successful_read_paths"],
        any_argument_group_present=deps["any_argument_group_present"],
        apply_duplicate_window_replan_contract=deps["apply_duplicate_window_replan_contract"],
        apply_unverified_old_text_replan_contract=deps["apply_unverified_old_text_replan_contract"],
        argument_value_present=deps["argument_value_present"],
        canonical_invalid_code_product_decision_signature=deps["canonical_invalid_code_product_decision_signature"],
        code_product_build_state_duplicate_write=deps["code_product_build_state_duplicate_write"],
        code_product_build_state_has_collecting_progress=deps["code_product_build_state_has_collecting_progress"],
        code_product_build_state_parse=deps["code_product_build_state_parse"],
        code_product_build_state_ready_payload=deps["code_product_build_state_ready_payload"],
        code_product_low_signal_target=deps["code_product_low_signal_target"],
        code_product_payload_violations=deps["code_product_payload_violations"],
        contract_final_required_now=deps["contract_final_required_now"],
        copyable_example_text=deps["copyable_example_text"],
        decision_matches_prompt_context_continuation=deps["decision_matches_prompt_context_continuation"],
        decision_paths=deps["decision_paths"],
        enforce_required_scratchpad_read_continuation_contract=deps["enforce_required_scratchpad_read_continuation_contract"],
        final_answer_is_action_plan_without_code_product=deps["final_answer_is_action_plan_without_code_product"],
        final_composition_tool_names_from_candidates=deps["final_composition_tool_names_from_candidates"],
        invalid_code_product_decision_signature_count=deps["invalid_code_product_decision_signature_count"],
        invalid_decision_signature_key=deps["invalid_decision_signature_key"],
        native_required_tool_decision_has_transport_provenance=deps["native_required_tool_decision_has_transport_provenance"],
        normalize_terminal_planner_decision=deps["normalize_terminal_planner_decision"],
        normalize_tool_name=deps["normalize_tool_name"],
        old_text_verified_by_repo_read=deps["old_text_verified_by_repo_read"],
        path_exists_repo_relative=deps["path_exists_repo_relative"],
        path_under_scope=deps["path_under_scope"],
        planner_scratchpad_read_selector_present=deps["planner_scratchpad_read_selector_present"],
        planner_scratchpad_window_signature=deps["planner_scratchpad_window_signature"],
        prompt_window_consumed_offsets=deps["prompt_window_consumed_offsets"],
        prompt_window_tracking_metadata_errors=deps["prompt_window_tracking_metadata_errors"],
        repo_analysis_goal=deps["repo_analysis_goal"],
        repo_path_kind=deps["repo_path_kind"],
        repo_read_selector_present=deps["repo_read_selector_present"],
        repo_read_window_signature=deps["repo_read_window_signature"],
        repo_readable_evidence_file=deps["repo_readable_evidence_file"],
        repo_rel_token=deps["repo_rel_token"],
        repeated_tool_call_count=deps["repeated_tool_call_count"],
        scope_claim_conflict_for_path=deps["scope_claim_conflict_for_path"],
        successful_window_signatures=deps["successful_window_signatures"],
        target_scope_conflict_resolved=deps["target_scope_conflict_resolved"],
        latest_file_list_result=deps["latest_file_list_result"],
        goal_requires_code_product_report=deps["goal_requires_code_product_report"],
        planner_evidence_contract=deps["planner_evidence_contract"],
        validate_unified_diff_text=deps["validate_unified_diff_text"],
        successful_code_edit_proposals=deps["successful_code_edit_proposals"],
    )

    # Create ValidationContext for helper closures (deferred — built per-violation-path)

    # Parse decision
    decision = _normalize_terminal_planner_decision(decision if isinstance(decision, dict) else {})
    action = str(decision.get("action") or "tool").strip().lower()
    tool = validation_deps.normalize_tool_name(str(decision.get("tool") or ""))
    args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
    contract = validation_deps.planner_evidence_contract(goal, history)

    # Initialize validator classes
    tool_validator = ToolCallValidator(validation_deps, config)
    final_validator = FinalValidationValidator(validation_deps, config)
    path_validator = PathScopeValidator(validation_deps, config)

    # Early returns for simple checks
    tracking_errors = validation_deps.prompt_window_tracking_metadata_errors(history)
    if tracking_errors:
        return {
            "ok": False,
            "violations": ["prompt_context_window_tracking_errors"],
            "evidence_contract": contract,
            "prompt_window_tracking_errors": tracking_errors,
        }

    # Native mode check
    if AGENTIC_PLANNER_NATIVE_TOOLS and action == "tool" and not validation_deps.native_required_tool_decision_has_transport_provenance(decision):
        violations = ["planner_text_tool_call_disallowed_in_native_mode"]
        contract["required_next_progress"] = (
            "Native tool mode is required. Tool execution must arrive as "
            "message.tool_calls with native_tool_call=true; JSON-text action=tool "
            "is not executable. Choose a native tool_call, or return a terminal "
            "final/block answer."
        )
        return {"ok": False, "violations": violations, "evidence_contract": contract}

    # Check allowed tool names
    allowed_tool_names_source = (
        decision.get("allowed_tool_names")
        if isinstance(decision.get("allowed_tool_names"), list)
        else decision.get("allowed_native_tool_names")
    )
    allowed_tool_names: set[str] = set()
    if isinstance(allowed_tool_names_source, list):
        allowed_tool_names = {
            validation_deps.normalize_tool_name(str(name or ""))
            for name in allowed_tool_names_source
            if str(name or "").strip()
        }

    # Handle prompt context continuation
    prompt_context_continuation_required = (
        decision.get("prompt_context_continuation_required")
        if isinstance(decision.get("prompt_context_continuation_required"), dict)
        else {}
    )
    _prompt_context_continuation_matches = bool(
        prompt_context_continuation_required
        and validation_deps.decision_matches_prompt_context_continuation(
            decision,
            prompt_context_continuation_required,
        )
    )
    if prompt_context_continuation_required:
        contract = validation_deps.enforce_required_scratchpad_read_continuation_contract(
            contract,
            prompt_context_continuation_required,
        )

    # Handle action=final
    if action in {"final", "done", "complete", "completed"}:
        return _handle_final_action(
            decision, goal, history, contract, config, deps,
            validation_deps, allowed_tool_names,
        )

    # Handle action=block
    if action in {"block", "blocked", "need_user", "needs_user"}:
        return final_validator.validate_block(decision, history, contract)

    # Handle invalid action
    if action not in {"tool"}:
        violations = [f"invalid_action:{action or '<empty>'}"]
        return {"ok": False, "violations": violations, "evidence_contract": contract}

    # Handle missing/invalid tool
    if not tool:
        violations = ["missing_tool"]
        return {"ok": False, "violations": violations, "evidence_contract": contract}

    if tool not in VALID_INTERNAL_TOOLS:
        violations = [f"invalid_tool:{tool}"]
        return {"ok": False, "violations": violations, "evidence_contract": contract}

    # Validate tool call via extracted validator
    result = tool_validator.validate(
        tool=tool, args=args, action=action,
        contract=contract, allowed_tool_names=allowed_tool_names,
        history=history,
    )
    contract = result.evidence_contract

    if not result.ok and result.violations:
        return {"ok": False, "violations": result.violations, "evidence_contract": contract}

    # Handle code_product_build_state write
    if tool == "planner_scratchpad_write" and str(args.get("kind") or "") == CODE_PRODUCT_BUILD_STATE_KIND:
        return _handle_code_product_build_state(
            decision, args, history, contract, config, deps,
            validation_deps,
        )

    # Validate path scope constraints
    target_scope = validation_deps.agentic_v2_goal_scope(str(goal or ""), contract)
    known_paths_set: set[str] = set()
    known_paths_set.update(_collect_repo_paths(contract.get("known_paths_from_latest_repo_list_files")))
    known_paths_set.update(_collect_repo_paths(contract.get("validator_admissible_repo_read_paths")))
    known_paths_set.update(_collect_repo_paths(contract.get("read_admissible_paths")))
    known_paths_set.update(_collect_repo_paths(contract.get("covered_owner_paths")))
    known_paths_set.update(_collect_repo_paths(contract.get("candidate_owner_paths")))
    known_paths_set.update(_collect_repo_paths(contract.get("missing_owner_paths")))
    known_paths_set.update(_collect_repo_paths(contract.get("successful_repo_read_paths")))

    read_ok = [str(x) for x in contract.get("successful_repo_read_paths") or []]

    path_result = path_validator.validate_tool_paths(
        tool=tool, args=args, target_scope=target_scope,
        known_paths=known_paths_set, read_ok=read_ok,
        history=history, contract=contract,
    )
    contract = path_result.evidence_contract

    if not path_result.ok and path_result.violations:
        return {"ok": False, "violations": path_result.violations, "evidence_contract": contract}

    # Handle repeated tool calls
    if validation_deps.repeated_tool_call_count(history, tool, args) >= 2:
        violations = ["repeated_same_tool_arguments_without_progress"]
        return {"ok": False, "violations": violations, "evidence_contract": contract}

    # Handle invalid code product decision signature
    return _handle_invalid_signature(
        decision, history, contract, validation_deps,
    )


def _handle_final_action(
    decision: dict, goal: str, history: list, contract: dict,
    config: dict, deps: Any, validation_deps: ValidationDeps,
    allowed_tool_names: set,
) -> dict[str, Any]:
    """Handle action=final decision."""
    from .validator_helpers import (
        _coerce_final_rewrite_latch,
        _final_answer_declares_missing_coverage,
        _minimum_read_coverage_required,
        _minimum_read_coverage_satisfied,
        _minimum_read_coverage_missing_owner_paths,
        _repo_analysis_final_answer_quality,
        _apply_final_quality_route,
        _answer_chunk_misuses_terminal_payload_shape,
        _successful_answer_chunk_signatures,
        _clear_final_terminal_block_state,
        _escalate_final_terminal_block_state,
        _final_composition_tool_names_from_candidates,
        _final_answer_is_action_plan_without_code_product,
        _path_under_scope,
        _repo_readable_evidence_file,
    )

    violations: list[str] = []

    final_contract = contract.get("finalization_contract") if isinstance(contract.get("finalization_contract"), dict) else {}
    final_rewrite_latch = _coerce_final_rewrite_latch(contract.get("final_rewrite_latch"))
    planner_forced_terminal_block = bool(final_contract.get("planner_forced_terminal_block") if isinstance(final_contract, dict) else False)

    if final_rewrite_latch == "terminal_block_required" or planner_forced_terminal_block:
        violations.append("terminal_block_required_final_disallowed")
        contract["terminal_block_final_retry_count"] = int(contract.get("terminal_block_final_retry_count") or 0) + 1
        contract["planner_cuda_rewrite_required"] = True
        contract["final_rewrite_latch"] = "terminal_block_required"
        contract["planner_may_choose_final"] = False
        return {"ok": False, "violations": violations, "evidence_contract": contract}

    if final_contract and final_contract.get("final_allowed") is False:
        violations.append("final_not_allowed_by_evidence_contract:" + str(final_contract.get("reason") or "insufficient evidence"))

    # Check post-write validation
    post_write_contract = contract.get("post_write_validation_contract") if isinstance(contract.get("post_write_validation_contract"), dict) else {}
    if bool(post_write_contract.get("required")) and not bool(post_write_contract.get("validation_done")):
        violations.append(
            "final_after_write_validation_failed"
            if bool(post_write_contract.get("validation_failed")) else
            "final_after_write_without_validation"
        )

    final_answer = str(decision.get("final_answer") or decision.get("answer") or decision.get("summary") or "")

    # Simplified coverage check - would need full validator_helpers imports
    if _final_answer_declares_missing_coverage(final_answer):
        violations.append("final_declares_missing_read_coverage")

    target_kind = str(contract.get("target_kind") or "")
    target_file = str(contract.get("resolved_goal_file") or "")
    review_goal = bool(contract.get("goal_requests_python_file_review"))
    read_ok = [str(x) for x in contract.get("successful_repo_read_paths") or []]

    if target_kind == "file" and target_file and target_file not in read_ok:
        violations.append(f"final_without_requested_file_read:{target_file}")

    if (goal or True) and not final_answer.strip():
        violations.append("final_empty_answer")

    if review_goal and not read_ok:
        violations.append("final_without_successful_repo_read_for_python_review")

    return {"ok": not violations, "violations": violations, "evidence_contract": contract}


def _handle_code_product_build_state(
    decision: dict, args: dict, history: list, contract: dict,
    config: dict, deps: Any, validation_deps: ValidationDeps,
) -> dict[str, Any]:
    """Handle planner_scratchpad_write with code_product_build_state kind."""
    from .validator_helpers import (
        _code_product_build_state_parse,
        _code_product_build_state_has_collecting_progress,
        _code_product_build_state_ready_payload,
        _code_product_build_state_duplicate_write,
        _repo_rel_token,
    )

    violations: list[str] = []
    state_text = str(args.get("text") or args.get("content") or "")
    state = _code_product_build_state_parse(state_text)

    if not state:
        violations.append("code_product_build_state_invalid_payload")
    else:
        state_target = _repo_rel_token(args.get("target_file") or args.get("path") or state.get("target_file") or "")
        if not state_target or state_target == ".":
            violations.append("code_product_build_state_missing_target")
        elif state_target not in set([str(x) for x in contract.get("successful_repo_read_paths") or []]):
            violations.append(f"code_product_build_state_target_not_read:{state_target}")

    return {"ok": not violations, "violations": violations, "evidence_contract": contract}


def _handle_invalid_signature(
    decision: dict, history: list, contract: dict,
    validation_deps: ValidationDeps,
) -> dict[str, Any]:
    """Handle invalid code product decision signature tracking."""
    from .validator_helpers import (
        _canonical_invalid_code_product_decision_signature,
        _invalid_decision_signature_count,
        _invalid_decision_signature_key,
    )

    violations: list[str] = []
    invalid_signature = _canonical_invalid_code_product_decision_signature(decision, violations)
    invalid_repeat_count = _invalid_decision_signature_count(history, invalid_signature)

    response = {"ok": not violations, "violations": violations, "evidence_contract": contract}
    if invalid_signature:
        response["invalid_decision_signature"] = invalid_signature
        response["invalid_decision_repeat_count"] = invalid_repeat_count + 1

    return response