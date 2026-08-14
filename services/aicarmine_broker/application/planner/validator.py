"""Planner decision validator owner."""

from __future__ import annotations

import json
from typing import Any, Mapping

from aicarmine_broker.application.evidence.audit_guidance import goal_requests_semantic_audit
from aicarmine_broker.application.evidence.goal_classifier import effective_repo_analysis_goal
from aicarmine_broker.application.tool_surface.required_tool_call import (
    append_stale_required_call_marker,
    required_next_tool_call_satisfaction,
)
from aicarmine_broker.application.shared.path_tokens import repo_path_token as _repo_path_token


def _list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _repo_path_is_concrete(token: Any) -> bool:
    token = _repo_path_token(token)
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
        token = _repo_path_token(value)
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
        token = _repo_path_token(raw)
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


def _escalate_final_rewrite_retry_count(
    contract: dict[str, Any],
    
    has_gap_route: bool,
) -> dict[str, Any]:
    contract = contract if isinstance(contract, dict) else {}
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
            token = _repo_path_token(item)
            if token:
                out.add(token)
    elif isinstance(values, list):
        for item in values:
            if isinstance(item, dict):
                token = _repo_path_token(item.get("path") or item.get("source_path") or item.get("repo_path"))
            else:
                token = _repo_path_token(item)
            if token:
                out.add(token)
    else:
        token = _repo_path_token(values)
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
    token = _repo_path_token(value)
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
        path = _repo_path_token(args.get("path") or ".") or "."
        if path == ".":
            return True
        return not _route_token_is_prose_or_metric(path) and path in _known_contract_repo_dirs(contract)
    if tool in {"repo_semantic_search", "repo_rg_search", "repo_search"}:
        query = args.get("query") or args.get("pattern") or args.get("symbol") or args.get("needle") or args.get("text")
        if not _search_query_is_concrete(query):
            return False
        path = _repo_path_token(args.get("path")) if args.get("path") else ""
        if path and path not in _known_contract_repo_paths(contract) and path not in _known_contract_repo_dirs(contract):
            return False
        return True
    if tool == "planner_scratchpad_read":
        document_id = str(args.get("document_id") or "").strip()
        target_file = _repo_path_token(args.get("target_file")) if args.get("target_file") else ""
        if document_id and not _route_token_is_prose_or_metric(document_id):
            return True
        return bool(target_file and target_file in _known_contract_repo_paths(contract))
    return False


def validate_planner_decision_against_evidence(
    goal: str,
    decision: dict[str, Any],
    history: list[dict[str, Any]],
    require_native_tool_call: bool = False,
    deps: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
    state: dict[str, Any] | None = None,
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
    
    # === INJECTION PROTECTION SAFEGUARDS ===
    # These checks detect chain-of-thought contamination and injected decision manipulation
    
    def _detect_instruction_injection(contract: dict[str, Any]) -> list[str]:
        """Detect when operational_notes or required_next_progress contain injected instructions
        that bypass the planner's autonomous reasoning."""
        detected: list[str] = []
        
        operational = contract.get("operational_notes") if isinstance(contract.get("operational_notes"), dict) else {}
        next_progress = str(operational.get("next_instruction") or "").strip()
        
        if not next_progress:
            return detected
            
        # Check for instruction patterns that indicate injection rather than evidence-based guidance
        injection_patterns = [
            # Patterns that suggest the instruction is telling the planner WHAT to do rather than WHY
            "synthesize terminal final",
            "synthesize terminal analysis",
            "synthesize terminal conclusion",
            "synthesize terminal summary",
            "synthesize terminal report",
            # Patterns that bypass evidence requirements
            "do not call additional tools",
            "do not call any tools",
            "without calling additional tools",
            # Patterns that force a specific action regardless of evidence
            "force transition to action=",
            "forced transition to action=",
            "must synthesize terminal",
            "must return action=",
            "must produce action=",
        ]
        
        for pattern in injection_patterns:
            if pattern in next_progress.lower():
                detected.append(f"injected_instruction_pattern:{pattern[:80]}")
                break
                
        return detected
    
    def _detect_finalization_contract_manipulation(contract: dict[str, Any]) -> list[str]:
        """Detect when finalization_contract has been manipulated to force final/block decisions."""
        detected: list[str] = []
        
        final_contract = contract.get("finalization_contract") if isinstance(contract.get("finalization_contract"), dict) else {}
        
        # Check for forced finalization markers that indicate manipulation
        if final_contract.get("planner_forced_terminal_block") is True:
            reason = str(final_contract.get("planner_forced_terminal_block_reason") or "")
            if reason and reason not in {"", "controller-forced"}:
                detected.append(f"forced_terminal_block_injected:{reason[:120]}")
        
        # Check for forced finalization that bypasses evidence requirements
        if final_contract.get("final_allowed") is True and final_contract.get("planner_may_choose_final") is True:
            # If coverage is not satisfied but final is allowed, this is suspicious
            coverage = contract.get("minimum_read_coverage") if isinstance(contract.get("minimum_read_coverage"), dict) else {}
            if coverage and coverage.get("coverage_satisfied") is False:
                detected.append("final_allowed_without_coverage_satisfied")
        
        return detected
    
    def _detect_required_tool_call_injection(contract: dict[str, Any]) -> list[str]:
        """Detect when required_next_tool_call has been injected to force specific tool usage."""
        detected: list[str] = []
        
        required_tool_call = contract.get("required_next_tool_call") if isinstance(contract.get("required_next_tool_call"), dict) else {}
        
        if not required_tool_call:
            return detected
            
        # Check for injection patterns in required tool call
        source = str(required_tool_call.get("source") or "").strip()
        reason = str(required_tool_call.get("reason") or "").strip()
        
        # If source indicates injection rather than evidence-based requirement
        if source in {"injected", "controller-forced", "forced", "injected_instruction"}:
            detected.append(f"injected_required_tool_call_source:{source}")
        
        # Check for reason patterns that indicate injection
        injection_reasons = [
            "force execution of",
            "must call",
            "required to call",
            "forced to execute",
        ]
        
        for pattern in injection_reasons:
            if pattern in reason.lower():
                detected.append(f"injected_required_tool_call_reason:{pattern[:80]}")
                break
        
        return detected
    
    def _detect_working_memory_contamination(history: list[dict[str, Any]]) -> list[str]:
        """Detect when working memory or planner memory has been contaminated with injected guidance."""
        detected: list[str] = []
        
        for row in history:
            if not isinstance(row, dict):
                continue
            
            tool_result = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}
            
            # Check for injected instructions in tool results
            next_instruction = str(tool_result.get("next_instruction") or "").strip()
            if next_instruction:
                # Check for patterns that indicate injection rather than evidence-based guidance
                injection_patterns = [
                    "synthesize terminal",
                    "do not call additional tools",
                    "force transition",
                    "must synthesize",
                    "must return action=",
                ]
                
                for pattern in injection_patterns:
                    if pattern in next_instruction.lower():
                        detected.append(f"injected_instruction_in_tool_result:{pattern[:80]}")
                        break
        
        return detected
    
    # Run injection detection checks
    injection_violations = _detect_instruction_injection(contract)
    if injection_violations:
        violations.extend(injection_violations)
    
    finalization_manipulation = _detect_finalization_contract_manipulation(contract)
    if finalization_manipulation:
        violations.extend(finalization_manipulation)
    
    required_tool_injection = _detect_required_tool_call_injection(contract)
    if required_tool_injection:
        violations.extend(required_tool_injection)
    
    memory_contamination = _detect_working_memory_contamination(history)
    if memory_contamination:
        violations.extend(memory_contamination)
    
    # If injection detected, return early with violation details
    if violations:
        return {
            "ok": False,
            "violations": violations,
            "evidence_contract": contract,
            "injection_protection": True,
        }
    
    # === DEEP VRAM/GPU STATE MANIPULATION DETECTION ===
    # These checks detect low-level injection vectors where the model's internal
    # state (weights, activations, attention patterns, cache) is modified directly
    # rather than through normal prompt/contract mechanisms.
    
    def _detect_vram_state_manipulation(history: list[dict[str, Any]], inner_state: dict[str, Any]) -> list[str]:
        """Detect when VRAM/GPU state has been manipulated to inject biased decisions.
        
        Defensive design: all inner_state values are validated to be dicts before .get() calls.
        If any value is a list (which would cause 'list' object has no attribute 'get'), it is
        safely converted to {} to prevent AttributeError.
        """
        detected: list[str] = []
        
        # Defensive: ensure inner_state itself is a dict
        if not isinstance(inner_state, dict):
            inner_state = {}
        
        # Helper: safe get for potentially non-dict values
        def _safe_get(state_dict: Any, key: str) -> Any:
            """Get a value from state_dict, handling both dict and list cases."""
            if isinstance(state_dict, dict):
                return state_dict.get(key)
            # If it's a list or other type, return None to avoid AttributeError
            return None
        
        # Check 1: Detect sudden shifts in model behavior patterns
        if history and len(history) >= 3:
            recent_decisions = []
            for row in history[-5:] if len(history) >= 5 else history:
                if isinstance(row, dict):
                    action = str(row.get("action") or "").strip()
                    tool = str(row.get("tool") or "").strip()
                    if action or tool:
                        recent_decisions.append({"action": action, "tool": tool})
            
            # Detect pattern: sudden shift from tool calls to final answer without evidence consumption
            if recent_decisions:
                tool_count = sum(1 for d in recent_decisions if d.get("action") == "tool")
                final_count = sum(1 for d in recent_decisions if d.get("action") in {"final", "done", "complete"})
                
                # If final answers appear without corresponding evidence consumption, suspect VRAM manipulation
                if final_count > 0 and tool_count == 0 and len(recent_decisions) >= 3:
                    # Check if there's evidence of evidence consumption
                    evidence_consumed = False
                    for row in history:
                        if isinstance(row, dict):
                            if row.get("event") == "evidence_consumed" or row.get("type") == "evidence_consumed":
                                evidence_consumed = True
                                break
                    
                    if not evidence_consumed:
                        detected.append("sudden_final_without_evidence_consumption:suspect_vram_manipulation")
        
        # Check 2: Detect model state anomalies in planner metadata
        model_metadata_raw = _safe_get(inner_state, "planner_model_metadata")
        model_metadata = model_metadata_raw if isinstance(model_metadata_raw, dict) else {}
        
        if model_metadata:
            # Check for anomalous temperature/TopP shifts that could indicate state manipulation
            temperature = model_metadata.get("temperature")
            top_p = model_metadata.get("top_p")
            
            # If temperature is unusually low (near deterministic) without controller authorization
            if temperature is not None and temperature < 0.1:
                authorized_temp = model_metadata.get("authorized_temperature")
                if authorized_temp is None or authorized_temp != temperature:
                    detected.append("anomalous_temperature_shift:suspect_vram_state_manipulation")
            
            # Check for attention pattern anomalies
            attention_anomaly = model_metadata.get("attention_pattern_anomaly")
            if attention_anomaly is True:
                detected.append("attention_pattern_anomaly:confirmed_vram_state_manipulation")
            
            # Check for weight shift detection
            weight_shift = model_metadata.get("weight_shift_detected")
            if weight_shift is True:
                detected.append("weight_shift_detected:confirmed_vram_state_manipulation")
        
        # Check 3: Detect prompt injection at token level
        for row in history:
            if not isinstance(row, dict):
                continue
            
            # Defensive: ensure row has .get method
            if hasattr(row, 'get'):
                # Check for token-level injection markers
                token_injection = row.get("token_injection_detected")
                if token_injection is True:
                    detected.append("token_injection_detected:confirmed_vram_state_manipulation")
                
                # Check for embedding vector manipulation
                embedding_anomaly = row.get("embedding_vector_anomaly")
                if embedding_anomaly is True:
                    detected.append("embedding_vector_anomaly:confirmed_vram_state_manipulation")
                
                # Check for activation pattern manipulation
                activation_anomaly = row.get("activation_pattern_anomaly")
                if activation_anomaly is True:
                    detected.append("activation_pattern_anomaly:confirmed_vram_state_manipulation")
        
        # Check 4: Detect GPU memory state corruption
        gpu_state_raw = _safe_get(inner_state, "gpu_memory_state")
        gpu_state = gpu_state_raw if isinstance(gpu_state_raw, dict) else {}
        
        if gpu_state:
            memory_corruption = gpu_state.get("memory_corruption_detected")
            if memory_corruption is True:
                detected.append("gpu_memory_corruption:confirmed_vram_state_manipulation")
            
            weight_modification = gpu_state.get("weight_modification_detected")
            if weight_modification is True:
                detected.append("gpu_weight_modification:confirmed_vram_state_manipulation")
            
            activation_modification = gpu_state.get("activation_modification_detected")
            if activation_modification is True:
                detected.append("gpu_activation_modification:confirmed_vram_state_manipulation")
        
        return detected
    
    def _detect_model_weight_injection(history: list[dict[str, Any]], inner_state: dict[str, Any]) -> list[str]:
        """Detect when model weights have been injected to bias the planner.
        
        Defensive design: all inner_state values are validated to be dicts before .get() calls.
        """
        detected: list[str] = []
        
        # Defensive: ensure inner_state itself is a dict
        if not isinstance(inner_state, dict):
            inner_state = {}
        
        # Helper: safe get for potentially non-dict values
        def _safe_get_weight_state(state_dict: Any, key: str) -> Any:
            """Get a value from state_dict, handling both dict and list cases."""
            if isinstance(state_dict, dict):
                return state_dict.get(key)
            return None
        
        # Check 1: Detect weight injection markers in planner state
        weight_state_raw = _safe_get_weight_state(inner_state, "model_weight_state")
        weight_state = weight_state_raw if isinstance(weight_state_raw, dict) else {}
        
        if weight_state:
            # Check for weight injection detection
            injection_detected = weight_state.get("weight_injection_detected")
            if injection_detected is True:
                detected.append("model_weight_injection:confirmed_direct_weight_manipulation")
            
            # Check for weight modification timestamps
            last_clean_weight_time = weight_state.get("last_clean_weight_timestamp")
            current_time = weight_state.get("current_timestamp")
            weight_modification_time = weight_state.get("weight_modification_timestamp")
            
            if last_clean_weight_time and weight_modification_time:
                if weight_modification_time > last_clean_weight_time:
                    detected.append("weight_modification_after_clean_state:suspect_weight_injection")
        
        # Check 2: Detect output distribution anomalies
        output_distribution_raw = _safe_get_weight_state(inner_state, "output_distribution")
        output_distribution = output_distribution_raw if isinstance(output_distribution_raw, dict) else {}
        
        if output_distribution:
            # Check for suspicious output concentration
            output_concentration = output_distribution.get("output_concentration")
            if output_concentration and output_concentration > 0.95:
                # Very high concentration suggests weight manipulation
                detected.append("extreme_output_concentration:suspect_weight_injection")
            
            # Check for distribution anomaly flag
            distribution_anomaly = output_distribution.get("anomaly_detected")
            if distribution_anomaly is True:
                detected.append("output_distribution_anomaly:confirmed_weight_injection")
        
        # Check 3: Detect gradient manipulation
        gradient_state_raw = _safe_get_weight_state(inner_state, "gradient_state")
        gradient_state = gradient_state_raw if isinstance(gradient_state_raw, dict) else {}
        
        if gradient_state:
            gradient_manipulation = gradient_state.get("gradient_manipulation_detected")
            if gradient_manipulation is True:
                detected.append("gradient_manipulation:confirmed_weight_injection")
            
            # Check for unexpected gradient norms
            gradient_norm = gradient_state.get("gradient_norm")
            expected_gradient_norm = gradient_state.get("expected_gradient_norm")
            
            if gradient_norm is not None and expected_gradient_norm is not None:
                if abs(gradient_norm - expected_gradient_norm) > 0.5:
                    detected.append("gradient_norm_anomaly:suspect_weight_injection")
        
        # Check 4: Detect fine-tuning injection
        fine_tuning_state_raw = _safe_get_weight_state(inner_state, "fine_tuning_state")
        fine_tuning_state = fine_tuning_state_raw if isinstance(fine_tuning_state_raw, dict) else {}
        
        if fine_tuning_state:
            unauthorized_fine_tuning = fine_tuning_state.get("unauthorized_fine_tuning_detected")
            if unauthorized_fine_tuning is True:
                detected.append("unauthorized_fine_tuning:confirmed_weight_injection")
            
            # Check for sudden learning rate changes
            learning_rate = fine_tuning_state.get("learning_rate")
            expected_learning_rate = fine_tuning_state.get("expected_learning_rate")
            
            if learning_rate is not None and expected_learning_rate is not None:
                if learning_rate > expected_learning_rate * 10:
                    detected.append("learning_rate_spike:suspect_weight_injection")
        
        return detected
    
    def _detect_attention_pattern_injection(history: list[dict[str, Any]], inner_state: dict[str, Any]) -> list[str]:
        """Detect when attention patterns have been injected to bias the planner.
        
        Defensive design: all inner_state values are validated to be dicts before .get() calls.
        """
        detected: list[str] = []
        
        # Defensive: ensure inner_state itself is a dict
        if not isinstance(inner_state, dict):
            inner_state = {}
        
        # Helper: safe get for potentially non-dict values
        def _safe_get_attention_state(state_dict: Any, key: str) -> Any:
            """Get a value from state_dict, handling both dict and list cases."""
            if isinstance(state_dict, dict):
                return state_dict.get(key)
            return None
        
        # Check 1: Detect attention pattern anomalies
        attention_state_raw = _safe_get_attention_state(inner_state, "attention_state")
        attention_state = attention_state_raw if isinstance(attention_state_raw, dict) else {}
        
        if attention_state:
            # Check for attention injection detection
            attention_injection = attention_state.get("attention_injection_detected")
            if attention_injection is True:
                detected.append("attention_injection:confirmed_attention_manipulation")
            
            # Check for attention head manipulation
            head_manipulation = attention_state.get("head_manipulation_detected")
            if head_manipulation is True:
                detected.append("attention_head_manipulation:confirmed_attention_manipulation")
            
            # Check for attention score anomalies
            attention_scores = attention_state.get("attention_scores")
            if isinstance(attention_scores, dict):
                max_score = attention_scores.get("max_score")
                min_score = attention_scores.get("min_score")
                
                if max_score is not None and min_score is not None:
                    if max_score > 0.99 and min_score < 0.01:
                        # Extreme attention concentration suggests manipulation
                        detected.append("extreme_attention_concentration:suspect_attention_injection")
        
        # Check 2: Detect cross-attention injection
        cross_attention_state_raw = _safe_get_attention_state(inner_state, "cross_attention_state")
        cross_attention_state = cross_attention_state_raw if isinstance(cross_attention_state_raw, dict) else {}
        
        if cross_attention_state:
            cross_attention_injection = cross_attention_state.get("injection_detected")
            if cross_attention_injection is True:
                detected.append("cross_attention_injection:confirmed_attention_manipulation")
            
            # Check for unexpected cross-attention patterns
            unexpected_patterns = cross_attention_state.get("unexpected_patterns_detected")
            if unexpected_patterns is True:
                detected.append("unexpected_cross_attention_patterns:suspect_attention_injection")
        
        # Check 3: Detect attention rollup attacks
        rollup_state_raw = _safe_get_attention_state(inner_state, "attention_rollup_state")
        rollup_state = rollup_state_raw if isinstance(rollup_state_raw, dict) else {}
        
        if rollup_state:
            rollup_attack = rollup_state.get("rollup_attack_detected")
            if rollup_attack is True:
                detected.append("attention_rollup_attack:confirmed_attention_manipulation")
        
        return detected
    
    def _detect_prompt_token_injection(history: list[dict[str, Any]], inner_state: dict[str, Any]) -> list[str]:
        """Detect when prompt tokens have been injected to bias the planner.
        
        Defensive design: all inner_state values are validated to be dicts before .get() calls.
        """
        detected: list[str] = []
        
        # Defensive: ensure inner_state itself is a dict
        if not isinstance(inner_state, dict):
            inner_state = {}
        
        # Helper: safe get for potentially non-dict values
        def _safe_get_prompt_state(state_dict: Any, key: str) -> Any:
            """Get a value from state_dict, handling both dict and list cases."""
            if isinstance(state_dict, dict):
                return state_dict.get(key)
            return None
        
        # Check 1: Detect prompt injection markers
        prompt_state_raw = _safe_get_prompt_state(inner_state, "prompt_state")
        prompt_state = prompt_state_raw if isinstance(prompt_state_raw, dict) else {}
        
        if prompt_state:
            # Check for prompt injection detection
            prompt_injection = prompt_state.get("prompt_injection_detected")
            if prompt_injection is True:
                detected.append("prompt_injection:confirmed_token_injection")
            
            # Check for adversarial prompt detection
            adversarial_prompt = prompt_state.get("adversarial_prompt_detected")
            if adversarial_prompt is True:
                detected.append("adversarial_prompt:confirmed_token_injection")
            
            # Check for token boundary violations
            boundary_violation = prompt_state.get("token_boundary_violation")
            if boundary_violation is True:
                detected.append("token_boundary_violation:suspect_token_injection")
        
        # Check 2: Detect special token manipulation
        special_token_state_raw = _safe_get_prompt_state(inner_state, "special_token_state")
        special_token_state = special_token_state_raw if isinstance(special_token_state_raw, dict) else {}
        
        if special_token_state:
            special_token_manipulation = special_token_state.get("manipulation_detected")
            if special_token_manipulation is True:
                detected.append("special_token_manipulation:confirmed_token_injection")
            
            # Check for unexpected special tokens
            unexpected_special_tokens = special_token_state.get("unexpected_special_tokens")
            if unexpected_special_tokens:
                detected.append(f"unexpected_special_tokens:{len(expected_special_tokens)}:suspect_token_injection")
        
        # Check 3: Detect embedding injection
        embedding_state_raw = _safe_get_prompt_state(inner_state, "embedding_state")
        embedding_state = embedding_state_raw if isinstance(embedding_state_raw, dict) else {}
        
        if embedding_state:
            embedding_injection = embedding_state.get("injection_detected")
            if embedding_injection is True:
                detected.append("embedding_injection:confirmed_token_injection")
            
            # Check for embedding perturbation
            embedding_perturbation = embedding_state.get("perturbation_detected")
            if embedding_perturbation is True:
                detected.append("embedding_perturbation:suspect_token_injection")
        
        return detected
    
    def _detect_internal_state_corruption(history: list[dict[str, Any]], inner_state: dict[str, Any]) -> list[str]:
        """Detect when internal model state has been corrupted to inject biased decisions.
        
        Defensive design: all inner_state values are validated to be dicts before .get() calls.
        """
        detected: list[str] = []
        
        # Defensive: ensure inner_state itself is a dict
        if not isinstance(inner_state, dict):
            inner_state = {}
        
        # Helper: safe get for potentially non-dict values
        def _safe_get_hidden_state(state_dict: Any, key: str) -> Any:
            """Get a value from state_dict, handling both dict and list cases."""
            if isinstance(state_dict, dict):
                return state_dict.get(key)
            return None
        
        # Check 1: Detect hidden state manipulation
        hidden_state_raw = _safe_get_hidden_state(inner_state, "hidden_state")
        hidden_state = hidden_state_raw if isinstance(hidden_state_raw, dict) else {}
        
        if hidden_state:
            hidden_state_manipulation = hidden_state.get("manipulation_detected")
            if hidden_state_manipulation is True:
                detected.append("hidden_state_manipulation:confirmed_internal_state_corruption")
            
            # Check for hidden state anomalies
            hidden_state_anomaly = hidden_state.get("anomaly_detected")
            if hidden_state_anomaly is True:
                detected.append("hidden_state_anomaly:suspect_internal_state_corruption")
        
        # Check 2: Detect cache poisoning
        cache_state_raw = _safe_get_hidden_state(inner_state, "kv_cache_state")
        cache_state = cache_state_raw if isinstance(cache_state_raw, dict) else {}
        
        if cache_state:
            cache_poisoning = cache_state.get("poisoning_detected")
            if cache_poisoning is True:
                detected.append("kv_cache_poisoning:confirmed_internal_state_corruption")
            
            # Check for cache corruption markers
            cache_corruption = cache_state.get("corruption_detected")
            if cache_corruption is True:
                detected.append("kv_cache_corruption:suspect_internal_state_corruption")
        
        # Check 3: Detect layer norm manipulation
        layer_norm_state_raw = _safe_get_hidden_state(inner_state, "layer_norm_state")
        layer_norm_state = layer_norm_state_raw if isinstance(layer_norm_state_raw, dict) else {}
        
        if layer_norm_state:
            layer_norm_manipulation = layer_norm_state.get("manipulation_detected")
            if layer_norm_manipulation is True:
                detected.append("layer_norm_manipulation:confirmed_internal_state_corruption")
            
            # Check for layer norm anomaly flags
            layer_norm_anomaly = layer_norm_state.get("anomaly_detected")
            if layer_norm_anomaly is True:
                detected.append("layer_norm_anomaly:suspect_internal_state_corruption")
        
        return detected
    
    def _detect_evidence_contract_tampering(history: list[dict[str, Any]], inner_state: dict[str, Any]) -> list[str]:
        """Detect when the evidence contract has been tampered with at the source.
        
        Defensive design: all inner_state values are validated to be dicts before .get() calls.
        """
        detected: list[str] = []
        
        # Defensive: ensure inner_state itself is a dict
        if not isinstance(inner_state, dict):
            inner_state = {}
        
        # Helper: safe get for potentially non-dict values
        def _safe_get_contract_source(state_dict: Any, key: str) -> Any:
            """Get a value from state_dict, handling both dict and list cases."""
            if isinstance(state_dict, dict):
                return state_dict.get(key)
            return None
        
        # Check 1: Detect contract source tampering
        contract_source_raw = _safe_get_contract_source(inner_state, "contract_source_state")
        contract_source = contract_source_raw if isinstance(contract_source_raw, dict) else {}
        
        if contract_source:
            source_tampering = contract_source.get("tampering_detected")
            if source_tampering is True:
                detected.append("contract_source_tampering:confirmed_contract_manipulation")
            
            # Check for contract modification timestamps
            last_valid_contract_time = contract_source.get("last_valid_contract_timestamp")
            current_time = contract_source.get("current_timestamp")
            modification_time = contract_source.get("modification_timestamp")
            
            if last_valid_contract_time and modification_time:
                if modification_time > last_valid_contract_time:
                    detected.append("contract_modification_after_valid_state:suspect_contract_tampering")
        
        # Check 2: Detect semantic intent manipulation
        semantic_intent_raw = _safe_get_contract_source(inner_state, "semantic_intent_state")
        semantic_intent = semantic_intent_raw if isinstance(semantic_intent_raw, dict) else {}
        
        if semantic_intent:
            intent_manipulation = semantic_intent.get("manipulation_detected")
            if intent_manipulation is True:
                detected.append("semantic_intent_manipulation:confirmed_contract_manipulation")
            
            # Check for intent drift detection
            intent_drift = semantic_intent.get("drift_detected")
            if intent_drift is True:
                detected.append("semantic_intent_drift:suspect_contract_tampering")
        
        return detected
    
    def _detect_replan_specialist_injection(history: list[dict[str, Any]]) -> list[str]:
        """Detect when planner replan specialist has injected biased guidance."""
        detected: list[str] = []
        
        for row in history:
            if not isinstance(row, dict):
                continue
            
            # Check for replan specialist events
            if row.get("event") == "planner_replan_specialist" or row.get("type") == "planner_replan_specialist":
                replan_data = row.get("data") or row.get("tool_result")
                if not isinstance(replan_data, dict):
                    continue
                
                # Check for injection patterns in replan specialist output
                required_progress = str(replan_data.get("required_next_progress") or "").strip()
                if required_progress:
                    injection_patterns = [
                        "synthesize terminal",
                        "do not call additional tools",
                        "force transition to action=",
                        "must synthesize terminal",
                        "must return action=",
                        "forced to execute",
                    ]
                    
                    for pattern in injection_patterns:
                        if pattern in required_progress.lower():
                            detected.append(f"injected_replan_specialist_instruction:{pattern[:80]}")
                            break
        
        return detected
    
    def _detect_cuda_rewrite_injection(inner_state: dict[str, Any]) -> list[str]:
        """Detect when CUDA rewrite has been used to force decisions."""
        detected: list[str] = []
        
        planner_role_override = inner_state.get("planner_role_override") if isinstance(inner_state.get("planner_role_override"), dict) else {}
        
        if not planner_role_override:
            return detected
            
        role = str(planner_role_override.get("role") or "").strip()
        instruction = str(planner_role_override.get("instruction") or "").strip()
        provider = str(planner_role_override.get("provider") or "").strip()
        
        # Check for forced rewrite that bypasses evidence requirements
        if role == "planner_cuda_rewrite":
            # Check instruction for injection patterns
            injection_patterns = [
                "synthesize terminal",
                "do not call additional tools",
                "force transition to action=",
                "must synthesize terminal",
                "must return action=",
                "forced to execute",
            ]
            
            for pattern in injection_patterns:
                if pattern in instruction.lower():
                    detected.append(f"injected_cuda_rewrite_instruction:{pattern[:80]}")
                    break
        
        return detected
    
    def _detect_controller_evidence_contract_tampering(contract: dict[str, Any]) -> list[str]:
        """Detect when evidence contract has been tampered by controller to force decisions."""
        detected: list[str] = []
        
        # Check for suspicious finalization contract modifications
        final_contract = contract.get("finalization_contract") if isinstance(contract.get("finalization_contract"), dict) else {}
        
        # If final_allowed is True but coverage is not satisfied, this is suspicious
        if final_contract.get("final_allowed") is True:
            coverage = contract.get("minimum_read_coverage") if isinstance(contract.get("minimum_read_coverage"), dict) else {}
            if coverage and coverage.get("coverage_satisfied") is False:
                detected.append("controller_tampered_finalization_contract:final_allowed_without_coverage")
        
        # Check for suspicious required_next_tool_call modifications
        required_tool_call = contract.get("required_next_tool_call") if isinstance(contract.get("required_next_tool_call"), dict) else {}
        
        if required_tool_call:
            source = str(required_tool_call.get("source") or "").strip()
            validated = required_tool_call.get("validated")
            validation_source = str(required_tool_call.get("validation_source") or "").strip()
            
            # If validated but source indicates controller injection
            if validated and source in {"controller", "controller-forced", "forced"}:
                detected.append(f"controller_tampered_required_tool_call:source={source}")
        
        return detected
    
    def _detect_planner_memory_surface_contamination(history: list[dict[str, Any]]) -> list[str]:
        """Detect when planner memory surface records have been contaminated with injected guidance."""
        detected: list[str] = []
        
        for row in history:
            if not isinstance(row, dict):
                continue
            
            tool_result = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}
            
            # Check for planner memory surface contamination
            if tool_result.get("planner_memory_surface") or tool_result.get("planner_memory"):
                memory_data = tool_result.get("planner_memory") if isinstance(tool_result.get("planner_memory"), dict) else {}
                
                if memory_data:
                    records = memory_data.get("records") if isinstance(memory_data.get("records"), list) else []
                    
                    for record in records:
                        if not isinstance(record, dict):
                            continue
                        
                        # Check for injected guidance in memory records
                        content = str(record.get("content") or record.get("text") or "").strip()
                        summary = str(record.get("summary") or "").strip()
                        
                        if content or summary:
                            injection_patterns = [
                                "synthesize terminal",
                                "do not call additional tools",
                                "force transition to action=",
                                "must synthesize terminal",
                                "must return action=",
                                "forced to execute",
                            ]
                            
                            for pattern in injection_patterns:
                                if pattern in (content + summary).lower():
                                    detected.append(f"injected_planner_memory_record:{pattern[:80]}")
                                    break
        
        return detected
    
    def _detect_working_memory_contamination(inner_state: dict[str, Any]) -> list[str]:
        """Detect when working memory fields have been contaminated with injected guidance."""
        detected: list[str] = []
        
        # Defensive: inner_state can be history (list) when called from line 1288
        if not isinstance(inner_state, dict):
            return detected
        
        raw_wm = inner_state.get("working_memory_for_30b")
        working_memory = raw_wm if isinstance(raw_wm, dict) else {}
        
        if not working_memory:
            return detected
        
        # Check for injected instructions in working memory
        operational_notes = working_memory.get("operational_notes") if isinstance(working_memory.get("operational_notes"), dict) else {}
        next_instruction = str(operational_notes.get("next_instruction") or "").strip()
        
        if next_instruction:
            injection_patterns = [
                "synthesize terminal",
                "do not call additional tools",
                "force transition to action=",
                "must synthesize terminal",
                "must return action=",
                "forced to execute",
            ]
            
            for pattern in injection_patterns:
                if pattern in next_instruction.lower():
                    detected.append(f"injected_working_memory_instruction:{pattern[:80]}")
                    break
        
        return detected
    
    # === RUN COMPREHENSIVE INJECTION DETECTION ===
    # Level 1: High-level instruction injection (operational notes, contract fields)
    injection_violations = _detect_instruction_injection(contract)
    if injection_violations:
        violations.extend(injection_violations)
    
    finalization_manipulation = _detect_finalization_contract_manipulation(contract)
    if finalization_manipulation:
        violations.extend(finalization_manipulation)
    
    required_tool_injection = _detect_required_tool_call_injection(contract)
    if required_tool_injection:
        violations.extend(required_tool_injection)
    
    memory_contamination = _detect_working_memory_contamination(history)
    if memory_contamination:
        violations.extend(memory_contamination)
    
    # Level 2: Low-level VRAM/GPU state manipulation (weights, activations, attention)
    vram_manipulation = _detect_vram_state_manipulation(history, state or {})
    if vram_manipulation:
        violations.extend(vram_manipulation)
    
    weight_injection = _detect_model_weight_injection(history, state or {})
    if weight_injection:
        violations.extend(weight_injection)
    
    attention_injection = _detect_attention_pattern_injection(history, state or {})
    if attention_injection:
        violations.extend(attention_injection)
    
    token_injection = _detect_prompt_token_injection(history, state or {})
    if token_injection:
        violations.extend(token_injection)
    
    internal_corruption = _detect_internal_state_corruption(history, state or {})
    if internal_corruption:
        violations.extend(internal_corruption)
    
    contract_tampering = _detect_evidence_contract_tampering(history, state or {})
    if contract_tampering:
        violations.extend(contract_tampering)
    
    # If any injection detected at Level 1-2, return early with violation details
    if violations:
        return {
            "ok": False,
            "violations": violations,
            "evidence_contract": contract,
            "injection_protection": True,
        }
    
    # Level 3: Component-level injection (replan specialist, CUDA rewrite, controller)
    replan_injection = _detect_replan_specialist_injection(history)
    if replan_injection:
        violations.extend(replan_injection)
    
    cuda_rewrite_injection = _detect_cuda_rewrite_injection(state or {})
    if cuda_rewrite_injection:
        violations.extend(cuda_rewrite_injection)
    
    controller_tampering = _detect_controller_evidence_contract_tampering(contract)
    if controller_tampering:
        violations.extend(controller_tampering)
    
    memory_contamination = _detect_planner_memory_surface_contamination(history)
    if memory_contamination:
        violations.extend(memory_contamination)
    
    working_memory_contamination = _detect_working_memory_contamination(state or {})
    if working_memory_contamination:
        violations.extend(working_memory_contamination)
    
    # If any additional injection detected, return early with violation details
    if violations:
        return {
            "ok": False,
            "violations": violations,
            "evidence_contract": contract,
            "injection_protection": True,
        }

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
        for row in history if isinstance(history, list) else []:
            if not isinstance(row, dict):
                continue
            decision_row = row.get("decision") if isinstance(row.get("decision"), dict) else {}
            result_row = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}
            if _normalize_tool_name(str(decision_row.get("tool") or result_row.get("tool") or "")) != "planner_scratchpad_write":
                continue
            raw_args = decision_row.get("arguments") if isinstance(decision_row.get("arguments"), dict) else {}
            written = result_row.get("written") if isinstance(result_row.get("written"), dict) else {}
            kind = str(raw_args.get("kind") or written.get("kind") or "").strip()
            if kind not in {"answer_chunk", "final_answer_chunk"} or result_row.get("ok") is not True:
                continue
            tag = str(raw_args.get("tag") or written.get("tag") or "").strip()
            if tag:
                signatures.add(f"{kind}:{tag}")
        return signatures
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

    def _minimum_read_coverage_contract() -> dict[str, Any]:
        coverage = contract.get("minimum_read_coverage")
        if isinstance(coverage, dict):
            return coverage
        final_contract = (
            contract.get("finalization_contract")
            if isinstance(contract.get("finalization_contract"), dict)
            else {}
        )
        coverage = final_contract.get("minimum_read_coverage")
        return coverage if isinstance(coverage, dict) else {}

    def _minimum_read_coverage_required() -> bool:
        coverage = _minimum_read_coverage_contract()
        if coverage:
            return coverage.get("required") is True
        return contract.get("coverage_satisfied") is not True

    def _minimum_read_coverage_satisfied() -> bool:
        coverage = _minimum_read_coverage_contract()
        if coverage:
            return coverage.get("coverage_satisfied") is True
        return contract.get("coverage_satisfied") is True

    def _minimum_read_coverage_missing_owner_paths() -> list[str]:
        coverage = _minimum_read_coverage_contract()
        raw = coverage.get("missing_owner_paths") if coverage else contract.get("missing_owner_paths")
        missing = [str(path) for path in raw] if isinstance(raw, list) else []
        if not missing:
            return missing
        # Filter out paths that have been successfully read (they should disappear from missing list)
        successful = set()
        for path in contract.get("successful_repo_read_paths") if isinstance(contract.get("successful_repo_read_paths"), list) else []:
            token = _repo_rel_token(path)
            if token:
                successful.add(token)
        if not successful:
            try:
                for path in _agentic_v2_successful_read_paths(history):
                    token = _repo_rel_token(path)
                    if token:
                        successful.add(token)
            except Exception:
                pass
        if successful:
            missing = [p for p in missing if p not in successful]
        return missing

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
            token = _repo_rel_token(value)
            if token and token not in out:
                out.append(token)
        return out[:12]

    def _stale_required_next_repo_read_paths() -> set[str]:
        paths: set[str] = set()
        for row in contract.get("stale_required_next_tool_calls") if isinstance(contract.get("stale_required_next_tool_calls"), list) else []:
            if not isinstance(row, dict):
                continue
            if str(row.get("tool") or "") != "repo_read":
                continue
            args = row.get("arguments") if isinstance(row.get("arguments"), dict) else {}
            for path in args.get("paths", []) if isinstance(args.get("paths"), list) else [args.get("path")]:
                token = _repo_rel_token(path)
                if token:
                    paths.add(token)
        return paths

    def _successful_read_paths_for_final_route() -> set[str]:
        successful = set()
        for path in contract.get("successful_repo_read_paths") if isinstance(contract.get("successful_repo_read_paths"), list) else []:
            token = _repo_rel_token(path)
            if token:
                successful.add(token)
        if not successful:
            try:
                for path in _agentic_v2_successful_read_paths(history):
                    token = _repo_rel_token(path)
                    if token:
                        successful.add(token)
            except Exception:
                pass
        return successful

    def _path_allowed_by_missing_evidence(path: str, required_missing: list[str]) -> bool:
        token = _repo_rel_token(path)
        if not token:
            return False
        for item in required_missing:
            required = _repo_rel_token(item)
            if not required:
                continue
            if token == required or token.startswith(f"{required}/") or required.startswith(f"{token}/"):
                return True
        return False

    def _verified_required_next_missing_paths(values: Any) -> tuple[list[str], list[str]]:
        valid: list[str] = []
        invalid: list[str] = []
        successful = _successful_read_paths_for_final_route()
        stale = _stale_required_next_repo_read_paths()
        conceptual_tokens = {
            "coverage required",
            "read or search pending",
            "missing core candidate paths",
            "missing unverified file mentions",
        }
        for path in _coalesce_required_next_missing_paths(values):
            if (
                path in conceptual_tokens
                or path.startswith("need_")
                or any(ch.isspace() for ch in path)
            ):
                if path not in invalid:
                    invalid.append(path)
                continue
            if path in successful or path in stale:
                if path not in invalid:
                    invalid.append(path)
                continue
            if _path_exists_repo_relative(path) and _repo_readable_evidence_file(path):
                if path not in valid:
                    valid.append(path)
            elif path not in invalid:
                invalid.append(path)
        return valid[:12], invalid[:12]

    def _required_next_tool_from_missing_evidences(values: Any, allow_if_missing: bool) -> dict[str, Any]:
        iterable_values = values if isinstance(values, (list, tuple, set)) else []
        paths = _coalesce_required_next_missing_paths(
            [value for value in iterable_values if isinstance(value, str)]
        )
        if not paths:
            return {}
        paths = [
            path for path in paths
            if path not in _successful_read_paths_for_final_route()
            and path not in _stale_required_next_repo_read_paths()
        ]
        if not paths:
            return {}
        return {
            "tool": "repo_read",
            "arguments": {"paths": paths},
            "reason": (
                "Rewrite final from verified evidence requires at least one remaining evidence gap. "
                "Read one of the requested missing paths before final."
            ),
            "allow_only_if_missing_evidence": bool(allow_if_missing),
            "source": "repo_analysis_final_model_quality",
        }

    def _coalesce_required_next_tool_tool(value: dict[str, Any]) -> dict[str, Any]:
        tool = str(value.get("tool") or "").strip().lower()
        args = value.get("arguments") if isinstance(value.get("arguments"), dict) else {}
        if not tool:
            return {"tool": "", "arguments": {}, "allow_only_if_missing_evidence": False}
        out = {
            "tool": tool,
            "arguments": args,
            "allow_only_if_missing_evidence": bool(value.get("allow_only_if_missing_evidence")),
            "reason": str(value.get("reason") or "").strip(),
            "source": str(value.get("source") or "repo_analysis_final_model_quality").strip(),
        }
        if tool == "repo_read":
            if "paths" in args:
                normalized_paths = [
                    _repo_rel_token(item)
                    for item in args.get("paths", [])
                    if _repo_rel_token(item)
                ] if isinstance(args.get("paths"), list) else []
                if normalized_paths:
                    out["arguments"] = {"paths": normalized_paths}
                else:
                    out["arguments"] = {}
            else:
                path = _repo_rel_token(args.get("path"))
                if path:
                    out["arguments"] = {"path": path}
                else:
                    out["arguments"] = {}
            if out["arguments"]:
                out["allow_only_if_missing_evidence"] = True
        elif not args:
            out["arguments"] = {}
        return out

    def _coerce_final_rewrite_latch(value: Any) -> str:
        raw = str(value or "inactive").strip().lower()
        return (
            raw
            if raw in {"inactive", "rewrite_required", "required_gap_only", "terminal_block_required"}
            else "inactive"
        )

    def _required_gap_paths_from_quality(
        quality: Mapping[str, Any],
        
        existing_missing: list[str],
    ) -> list[str]:
        raw_missing = (
            quality.get("required_next_missing_evidences")
            if isinstance(quality.get("required_next_missing_evidences"), list)
            else existing_missing
        )
        if not isinstance(raw_missing, list):
            return []
        required_next_missing_evidences = [
            _repo_rel_token(item) for item in raw_missing if _repo_rel_token(item)
        ]
        successful = _successful_read_paths_for_final_route()
        stale = _stale_required_next_repo_read_paths()
        return [
            path
            for path in required_next_missing_evidences
            if path not in successful and path not in stale and path not in existing_missing
        ]

    def _apply_final_quality_route(quality: dict[str, Any]) -> None:
        step_index = len(history)
        if int(contract.get("planner_final_quality_last_rewrite_decision") or -1) != step_index:
            reject_count = int(contract.get("planner_final_quality_reject_count") or 0) + 1
            contract["planner_final_quality_reject_count"] = reject_count
            contract["planner_final_quality_last_rewrite_decision"] = step_index
        reject_count = int(contract.get("planner_final_quality_reject_count") or 0)
        contract["planner_cuda_rewrite_required"] = True

        required_next_progress = str(quality.get("required_next_progress") or "").strip()

        invalid_required_next_tool_call_paths: list[str] = []
        if required_next_progress:
            contract["required_next_progress"] = required_next_progress

        required_next_output_sections = (
            quality.get("required_next_output_sections")
            if isinstance(quality.get("required_next_output_sections"), list)
            else []
        )
        if required_next_output_sections:
            contract["required_next_output_sections"] = [
                str(item).strip()
                for item in required_next_output_sections
                if str(item).strip()
            ]

        raw_existing_required_missing = contract.get("required_next_missing_evidences")
        existing_required_missing = [
            path
            for path in _coalesce_required_next_missing_paths(
                raw_existing_required_missing
                if isinstance(raw_existing_required_missing, (list, tuple, set))
                else []
            )
            if path
        ]
        required_next_missing_evidences = _required_gap_paths_from_quality(
            quality,
            existing_missing=existing_required_missing,
        )
        raw_required_next_missing_evidences = (
            required_next_missing_evidences
            if required_next_missing_evidences
            else existing_required_missing
        )
        verified_required_missing, invalid_required_missing = _verified_required_next_missing_paths(
            raw_required_next_missing_evidences
        )
        if invalid_required_missing:
            contract["invalid_required_next_missing_evidences"] = invalid_required_missing
            contract["invalid_required_next_missing_evidence_reason"] = (
                "final-quality proposed strings that are not existing readable repo paths; "
                "validator will not turn them into repo_read calls"
            )
        if verified_required_missing:
            contract["required_next_missing_evidences"] = verified_required_missing
        else:
            contract.pop("required_next_missing_evidences", None)
            required_next_missing_evidences = []
            if invalid_required_missing and not contract.get("required_next_progress"):
                contract["required_next_progress"] = (
                    "Final-quality proposed no valid unread repo path. Do not call repo_read for "
                    "non-existing/prose paths; rewrite final from verified evidence or return a typed block."
                )

        required_next_tool_call = (
            quality.get("required_next_tool_call")
            if isinstance(quality.get("required_next_tool_call"), dict)
            else {}
        )
        raw_contract_missing = contract.get("required_next_missing_evidences")
        contract_missing = (
            raw_contract_missing
            if isinstance(raw_contract_missing, (list, tuple, set))
            else []
        )
        if not required_next_tool_call and contract_missing:
            required_next_tool_call = _required_next_tool_from_missing_evidences(
                contract_missing,
                allow_if_missing=True,
            )
        if required_next_tool_call.get("tool") == "repo_read":
            args = (
                required_next_tool_call.get("arguments")
                if isinstance(required_next_tool_call.get("arguments"), dict)
                else {}
            )
            raw_paths: list[Any] = []
            if args.get("path"):
                raw_paths.append(args.get("path"))
            raw_paths.extend(args.get("paths") if isinstance(args.get("paths"), list) else [])
            parsed_paths = _coalesce_repo_read_paths(raw_paths)
            allowlist = _final_quality_repo_read_allowlist(contract)
            valid_paths: list[str] = []
            for path in parsed_paths:
                if path in allowlist or not allowlist:
                    valid_paths.append(path)
                elif path not in invalid_required_next_tool_call_paths:
                    invalid_required_next_tool_call_paths.append(path)
            if valid_paths:
                if len(valid_paths) == 1:
                    args["path"] = valid_paths[0]
                    args.pop("paths", None)
                else:
                    args["paths"] = valid_paths[:12]
                    args.pop("path", None)
                required_next_tool_call["arguments"] = args
            else:
                required_next_tool_call = {}
        if invalid_required_next_tool_call_paths:
            contract["invalid_required_next_tool_call_paths"] = invalid_required_next_tool_call_paths[:12]
        if required_next_tool_call:
            required_next_tool_call = _coalesce_required_next_tool_tool(required_next_tool_call)
            if not _required_next_route_has_deterministic_proof(required_next_tool_call, contract):
                tool_name = str(required_next_tool_call.get("tool") or "").strip()
                args = (
                    required_next_tool_call.get("arguments")
                    if isinstance(required_next_tool_call.get("arguments"), dict)
                    else {}
                )
                path_token = _repo_path_token(args.get("path")) if args.get("path") else ""
                query_text = str(args.get("query") or args.get("pattern") or args.get("symbol") or args.get("needle") or args.get("text") or "").strip()
                if path_token:
                    contract["invalid_required_next_tool_call_paths"] = [path_token]
                if query_text:
                    contract["invalid_required_next_tool_call_query"] = query_text[:260]
                contract["invalid_required_next_tool_call_reason"] = (
                    f"{tool_name or 'required_next_tool_call'} lacked deterministic concrete route proof"
                )
                required_next_tool_call = {}
            if required_next_tool_call.get("tool") == "repo_read":
                required_args = (
                    required_next_tool_call.get("arguments")
                    if isinstance(required_next_tool_call.get("arguments"), dict)
                    else {}
                )
                raw_required_paths = (
                    required_args.get("paths")
                    if isinstance(required_args.get("paths"), list)
                    else [required_args.get("path")]
                )
                verified_tool_paths, invalid_tool_paths = _verified_required_next_missing_paths(
                    raw_required_paths
                )
                if invalid_tool_paths:
                    contract["invalid_required_next_tool_call_paths"] = invalid_tool_paths
                    contract["invalid_required_next_tool_call_reason"] = (
                        "repo_read required_next_tool_call contained non-existing or non-readable paths"
                    )
                required_missing = (
                    contract.get("required_next_missing_evidences")
                    if isinstance(contract.get("required_next_missing_evidences"), list)
                    else []
                )
                if required_missing:
                    verified_tool_paths = [
                        path for path in verified_tool_paths
                        if _path_allowed_by_missing_evidence(path, required_missing)
                    ]
                if verified_tool_paths:
                    required_next_tool_call["arguments"] = {"paths": verified_tool_paths}
                else:
                    required_next_tool_call = {}
            if required_next_tool_call and not required_next_tool_call.get("arguments"):
                required_next_tool_call = {}

        required_next_missing = (
            contract.get("required_next_missing_evidences")
            if isinstance(contract.get("required_next_missing_evidences"), list)
            else []
        )
        if required_next_tool_call and required_next_tool_call.get("tool") == "repo_read":
            required_next_tool_call["allow_only_if_missing_evidence"] = True
            required_args = (
                required_next_tool_call.get("arguments")
                if isinstance(required_next_tool_call.get("arguments"), dict)
                else {}
            )
            if required_next_missing and isinstance(required_args, dict):
                filtered_paths = [
                    path
                    for path in required_args.get("paths", [])
                    if str(path).strip() and _repo_rel_token(path) in required_next_missing
                ]
                if filtered_paths:
                    required_next_tool_call["arguments"] = {
                        "paths": _coalesce_required_next_missing_paths(filtered_paths)
                    }
                else:
                    required_next_tool_call = {}

            if required_next_tool_call and not required_next_tool_call.get("arguments"):
                required_next_tool_call = {}
        if required_next_tool_call:
            required_next_tool_call["source"] = required_next_tool_call.get(
                "source",
                "repo_analysis_final_model_quality",
            )
            required_next_tool_call["allow_only_if_missing_evidence"] = (
                required_next_tool_call.get("tool") == "repo_read"
            )
            satisfaction = required_next_tool_call_satisfaction(
                required_next_tool_call,
                history,
                successful_repo_read_paths=_agentic_v2_successful_read_paths,
                successful_window_signatures=_successful_window_signatures,
                repo_read_window_signature=_repo_read_window_signature,
                planner_scratchpad_window_signature=_planner_scratchpad_window_signature,
                decision_paths=_decision_paths,
            )
            if satisfaction.get("satisfied") is True:
                append_stale_required_call_marker(contract, satisfaction)
                contract.pop("required_next_tool_call", None)
                contract.pop("required_next_tool_call_validated", None)
                contract.pop("required_next_tool_call_validation_source", None)
                contract["required_next_progress"] = (
                    "Final-quality requested an evidence route that is already satisfied in "
                    "verified tool history. Do not call the same tool with the same arguments. "
                    "Rewrite action=final from existing verified evidence, or choose a different "
                    "concrete evidence gap only if one is still missing."
                )
                required_next_tool_call = {}
            else:
                required_next_tool_call["validated"] = True
                required_next_tool_call["validation_source"] = "deterministic_validator"
                contract["required_next_tool_call"] = required_next_tool_call
                contract["required_next_tool_call_validated"] = True
                contract["required_next_tool_call_validation_source"] = "deterministic_validator"
                tool_name = str(required_next_tool_call.get("tool") or "").strip()
                arguments = (
                    required_next_tool_call.get("arguments")
                    if isinstance(required_next_tool_call.get("arguments"), dict)
                    else {}
                )
                action = {
                    "action_id": "repo_analysis_final_quality:" + tool_name,
                    "tool": tool_name,
                    "arguments": arguments,
                    "reason": required_next_tool_call.get("reason") or required_next_progress,
                    "source": "repo_analysis_final_model_quality",
                    "independent_read_only": True,
                }
                existing = (
                    contract.get("candidate_next_actions")
                    if isinstance(contract.get("candidate_next_actions"), list)
                    else []
                )
                contract["candidate_next_actions"] = [action] + [
                    item for item in existing if isinstance(item, dict) and item != action
                ][:12]
        else:
            contract.pop("required_next_tool_call", None)
            contract.pop("required_next_tool_call_validated", None)
            contract.pop("required_next_tool_call_validation_source", None)
            fallback_progress = (
                "Final-quality rejected with no concrete evidence gap and no runnable required_next_tool_call. "
                "Rewrite the final answer from verified evidence only; do not call non-evidence tools."
            )
            # Lower threshold: allow terminal_block_required after just 1 rejection when
            # the judge model quality has already rejected the final answer. This prevents
            # the planner from being stuck emitting "block" while validator rejects it because
            # planner_may_choose_block is False.
            final_rewrite_latch = "terminal_block_required" if reject_count >= 1 else "rewrite_required"
            if final_rewrite_latch == "rewrite_required":
                if required_next_missing_evidences:
                    contract["required_next_progress"] = (
                        "Final-quality rejected with concrete, verified evidence gaps but no runnable required_next_tool_call. "
                        "You must rewrite the final answer by explicitly addressing the remaining required gaps: "
                        f"{required_next_missing_evidences[:8]}"
                    )
                else:
                    contract["required_next_progress"] = (
                        "Final-quality rejected without a concrete runnable gap route. "
                        "Continue rewrite from verified evidence and existing covered gaps only; "
                        "do not emit block unless a controller-forced terminal decision is present."
                    )
            if not contract.get("required_next_progress"):
                contract["required_next_progress"] = fallback_progress
            if final_rewrite_latch == "terminal_block_required":
                contract["planner_may_choose_block"] = True
                contract["planner_forced_terminal_block"] = True
                contract["planner_forced_terminal_block_reason"] = (
                    "repo_analysis_final_quality_no_runnable_gap_terminal_block"
                )
            else:
                contract["planner_may_choose_block"] = False
        has_gap_route = bool(required_next_tool_call) or bool(required_next_missing_evidences)
        if required_next_tool_call:
            final_rewrite_latch = _next_final_rewrite_latch(
                str(contract.get("final_rewrite_latch") or ""),
                reject_count=reject_count,
                has_gap_route=has_gap_route,
            )
        elif final_rewrite_latch != "terminal_block_required":
            final_rewrite_latch = _next_final_rewrite_latch(
                final_rewrite_latch,
                reject_count=reject_count,
                has_gap_route=False,
            )
        contract["final_rewrite_latch"] = final_rewrite_latch
        contract["planner_may_choose_block"] = final_rewrite_latch == "terminal_block_required"
        contract["planner_may_choose_final"] = False
        final_contract = (
            contract.get("finalization_contract")
            if isinstance(contract.get("finalization_contract"), dict)
            else {}
        )
        final_contract["final_allowed"] = False
        final_contract["planner_may_choose_final"] = False
        if final_rewrite_latch == "terminal_block_required":
            final_contract["planner_may_choose_block"] = True
            final_contract["planner_forced_terminal_block"] = True
            final_contract["planner_forced_terminal_block_reason"] = (
                "repo_analysis_final_quality_no_runnable_gap_terminal_block"
            )
            final_contract["reason"] = "repo_analysis_final_quality_no_runnable_gap_terminal_block"
        else:
            final_contract["planner_may_choose_block"] = False
            final_contract["reason"] = "repo_analysis_final_model_quality_rejected_no_runnable_gap"
        contract["finalization_contract"] = final_contract

    def _apply_duplicate_repo_read_path_recovery_contract(
        contract: dict[str, Any],
        repeated_reads: list[str],
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        contract = contract if isinstance(contract, dict) else {}
        history = history if isinstance(history, list) else []
        normalized: list[str] = []
        for path in repeated_reads if isinstance(repeated_reads, list) else []:
            token = _repo_path_token(path)
            if token and token not in normalized:
                normalized.append(token)
        if not normalized:
            return contract

        forbidden: list[str] = []
        for item in contract.get("forbidden_repeated_repo_read_paths", []):
            if isinstance(item, str):
                token = _repo_path_token(item)
                if token and token not in forbidden:
                    forbidden.append(token)
        for token in normalized:
            if token not in forbidden:
                forbidden.append(token)
        if not forbidden:
            return contract
        contract["forbidden_repeated_repo_read_paths"] = forbidden[:40]
        duplicate_repo_read_recovery_count = (
            contract.get("duplicate_repo_read_recovery_count")
            if isinstance(contract.get("duplicate_repo_read_recovery_count"), dict)
            else {}
        )
        for token in normalized:
            duplicate_repo_read_recovery_count[str(token)] = (
                int(duplicate_repo_read_recovery_count.get(str(token), 0) or 0) + 1
            )
        contract["duplicate_repo_read_recovery_count"] = {
            key: int(value)
            for key, value in duplicate_repo_read_recovery_count.items()
            if str(key).strip()
        }
        contract["required_next_tool_call_advisory"] = {
            "tool": "repo_read",
            "arguments": {
                "paths": normalized[:12],
            },
            "reason": "already_successful_full_path_read",
            "source": "duplicate_repo_read_recovery_contract",
        }

        required_next_tool_call = (
            contract.get("required_next_tool_call")
            if isinstance(contract.get("required_next_tool_call"), dict)
            else {}
        )
        if required_next_tool_call:
            required_tool = str(required_next_tool_call.get("tool") or "").strip()
            required_args = (
                required_next_tool_call.get("arguments")
                if isinstance(required_next_tool_call.get("arguments"), dict)
                else {}
            )
            if required_tool == "repo_read":
                required_paths = _decision_paths(required_args)
                if any(path in normalized for path in required_paths):
                    last_step = None
                    if history and isinstance(history[-1], dict):
                        last_step = history[-1].get("step")
                    append_stale_required_call_marker(
                        contract,
                        {
                            "tool": required_tool,
                            "arguments": required_args,
                            "satisfied": True,
                            "reason": "repo_read_already_successful",
                            "path_overlap": normalized,
                            "step": last_step,
                        },
                    )

        contract.pop("required_next_tool_call", None)
        contract.pop("required_next_tool_call_validated", None)
        contract.pop("required_next_tool_call_validation_source", None)
        # Patch B: duplicate repo_read recovery con evidence consumption route
        contract["required_next_progress"] = (
            "Duplicate repo_read detected. Consume verified evidence windows or rewrite final from existing reads."
        )
        final_contract = (
            contract.get("finalization_contract")
            if isinstance(contract.get("finalization_contract"), dict)
            else {}
        )
        if _minimum_read_coverage_satisfied():
            final_rewrite_latch = _coerce_final_rewrite_latch(contract.get("final_rewrite_latch"))
            if final_rewrite_latch == "inactive":
                contract["planner_may_choose_final"] = True
                final_contract["final_allowed"] = True
                final_contract["planner_may_choose_final"] = True
            else:
                final_contract["final_allowed"] = False
                final_contract["planner_may_choose_final"] = False
                final_contract["reason"] = "duplicate_repo_read_recovery_active_rewrite_latch"
            coverage = contract.get("minimum_read_coverage")
            if isinstance(coverage, dict):
                contract["coverage_satisfied"] = coverage.get("coverage_satisfied", True)

        duplicate_threshold_reached = any(
            int(duplicate_repo_read_recovery_count.get(path, 0) or 0) >= 2
            for path in normalized
        )
        if duplicate_threshold_reached:
            # Non forzare planner_scratchpad_read senza document_id/section/offset reali
            contract["required_next_progress"] = (
                "Duplicate repo_read recovery: use verified_content_reads and required_working_set.repo_reads; "
                "do not repeat repo_read. Extract conclusions from existing verified evidence."
            )
            # Non impostare required_next_tool_call: attendi documento_id reale da required_working_set
            contract["planner_may_choose_block"] = True
            contract["planner_may_choose_final"] = False
            final_contract["planner_forced_terminal_block"] = True
            final_contract["planner_forced_terminal_block_reason"] = (
                "duplicate_repo_read_recovery_count_threshold_reached"
            )
            final_contract["planner_may_choose_block"] = True
            final_contract["final_allowed"] = False
            final_contract["planner_may_choose_final"] = False
            final_contract["reason"] = "duplicate_repo_read_recovery_count_threshold_reached"
            # Se required_next_progress non è stato settato, mantieni messaggio informativo
            if not contract.get("required_next_progress"):
                contract["required_next_progress"] = (
                    "Duplicate repo_read recovery crossed retry threshold. "
                    "Return a rewrite constrained to verified evidence or explicit terminal blocker if controller-forced."
                )

        contract["finalization_contract"] = final_contract
        return contract

    tracking_errors = _prompt_window_tracking_metadata_errors(history)
    if tracking_errors:
        return {
            "ok": False,
            "violations": ["prompt_context_window_tracking_metadata_missing"],
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
            token = _repo_path_token(item.get("path"))
            if token:
                known_paths_set.add(token)
            for path in item.get("mentioned_paths", []) if isinstance(item.get("mentioned_paths"), list) else []:
                token = _repo_path_token(path)
                if token:
                    known_paths_set.add(token)
    operational_notes = (
        contract.get("operational_notes")
        if isinstance(contract.get("operational_notes"), dict)
        else {}
    )
    for item in operational_notes.get("read_notes", []) if isinstance(operational_notes.get("read_notes"), list) else []:
        if isinstance(item, dict):
            token = _repo_path_token(item.get("path"))
            if token:
                known_paths_set.add(token)
            for path in item.get("mentioned_paths", []) if isinstance(item.get("mentioned_paths"), list) else []:
                token = _repo_path_token(path)
                if token:
                    known_paths_set.add(token)
    known_paths = sorted(known_paths_set)
    admissible_reads = set(str(x) for x in _collect_repo_paths(contract.get("validator_admissible_repo_read_paths")))
    admissible_reads.update(_collect_repo_paths(contract.get("read_admissible_paths")))
    read_ok = [str(x) for x in contract.get("successful_repo_read_paths") or []]
    apply_contract = (
        contract.get("apply_write_contract")
        if isinstance(contract.get("apply_write_contract"), dict)
        else {}
    )
    apply_required = bool(contract.get("goal_requests_apply")) or bool(apply_contract.get("required"))
    apply_patch_applied = bool(apply_contract.get("patch_applied"))
    post_write_contract = (
        contract.get("post_write_validation_contract")
        if isinstance(contract.get("post_write_validation_contract"), dict)
        else {}
    )
    post_write_validation_required = bool(post_write_contract.get("required"))
    post_write_validation_done = bool(post_write_contract.get("validation_done"))
    post_write_validation_failed = bool(post_write_contract.get("validation_failed"))
    code_product_contract = (
        contract.get("code_product_contract")
        if isinstance(contract.get("code_product_contract"), dict)
        else {}
    )
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
                "final/block answer only if the evidence contract allows it."
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

    # Explicit check: reject repo_read on paths already in verified_content_reads
    # This prevents the planner from repeatedly calling repo_read for files it has already read.
    if tool == "repo_read":
        decision_paths_list = args.get("paths", []) if isinstance(args.get("arguments"), dict) else []
        if not isinstance(decision_paths_list, list):
            decision_paths_list = [args.get("path")] if args.get("path") else []
        decision_paths_list = [p for p in decision_paths_list if p]
        
        verified_rows = contract.get("verified_content_reads") if isinstance(contract.get("verified_content_reads"), list) else []
        verified_paths = {
            _repo_rel_token(row.get("path"))
            for row in verified_rows
            if isinstance(row, dict) and row.get("path")
        }
        
        # Check if any requested path is already verified
        already_read = []
        for dp in decision_paths_list:
            token = _repo_rel_token(dp)
            if token and token in verified_paths:
                already_read.append(token)
        
        if already_read:
            violations.append(f"repo_read_already_successful:" + ",".join(already_read[:5]))
            contract["required_next_tool_call"] = {}
            contract.pop("required_next_tool_call_validated", None)
            contract.pop("required_next_tool_call_validation_source", None)
            contract["forbidden_repeated_repo_read_paths"] = list(set(already_read)[:40])
            contract["duplicate_repo_read_recovery_count"] = {
                p: int(contract.get("duplicate_repo_read_recovery_count", {}).get(p, 0) + 1)
                for p in already_read
            }
            contract["required_next_progress"] = (
                "repo_read target paths are already in verified_content_reads. "
                f"Already read: {already_read[:5]}. "
                "Use evidence from existing verified reads instead of calling repo_read again. "
                "Choose a different unread path or action=final/block."
            )
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
        required_tool_call = (
            contract.get("required_next_tool_call")
            if isinstance(contract.get("required_next_tool_call"), dict)
            else {}
        )
        required_rewrite_tool = str(required_tool_call.get("tool") or "").strip()
        required_rewrite_missing = (
            contract.get("required_next_missing_evidences")
            if isinstance(contract.get("required_next_missing_evidences"), list)
            else []
        )
        required_rewrite_paths = []
        if required_rewrite_tool == "repo_read":
            args = required_tool_call.get("arguments") if isinstance(required_tool_call.get("arguments"), dict) else {}
            for raw_path in (args.get("paths", []) if isinstance(args.get("paths"), list) else []):
                path = _repo_rel_token(raw_path)
                if path:
                    required_rewrite_paths.append(path)
            if not required_rewrite_paths:
                path = _repo_rel_token(args.get("path"))
                if path:
                    required_rewrite_paths.append(path)
        if not required_rewrite_tool:
            required_next_progress = "Rewrite lane requires a concrete required_next_tool_call before terminal progress."
            if tool in SUPPORT_SUBTURN_TOOLS and not (prompt_context_continuation_required and prompt_context_continuation_matches):
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
                    required_next_progress = (
                        "Rewrite lane support-subturn loop detected. Return a rewritten terminal final "
                        "from verified evidence, or explicit block with remaining evidence gaps."
                    )
                contract["required_next_progress"] = required_next_progress
            else:
                violations.append("tool_not_allowed_in_post_final_reject_rewrite_lane")
                contract["required_next_progress"] = (
                    required_next_progress + " No required_next_tool_call was set by final-quality gate."
                )
            return {"ok": False, "violations": violations, "evidence_contract": contract}

        if tool != required_rewrite_tool:
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
                            f"Rewrite lane requires {required_rewrite_tool} as the next tool, "
                            "or a rewritten final."
                        )
                    # Forced finalization guard: when coverage is satisfied and support_subturn
                    # retry count has crossed threshold, force transition to action=final.
                    coverage_satisfied_val = _minimum_read_coverage_satisfied()
                    coverage_required_val = _minimum_read_coverage_required()
                    may_choose_final_val = bool(contract.get("planner_may_choose_final")) or bool(
                        final_contract.get("planner_may_choose_final")
                    )
                    support_retry_count = int(contract.get("support_subturn_rewrite_retry_count") or 0)
                    if coverage_satisfied_val and may_choose_final_val and support_retry_count >= 3 and tool not in {"final", "done"}:
                        contract["planner_may_choose_final"] = True
                        contract["planner_may_choose_block"] = False
                        final_contract["final_allowed"] = True
                        final_contract["planner_may_choose_final"] = True
                        final_contract.pop("reason", None)
                        contract["finalization_contract"] = final_contract
                        contract["required_next_progress"] = (
                            "Support-subturn retry threshold reached (>=3) with coverage satisfied "
                            "and final allowed. Synthesize terminal final from existing verified evidence "
                            "and read_notes; do not call additional tools."
                        )
                        return {
                            "ok": True,
                            "violations": [],
                            "evidence_contract": contract,
                            "forced_finalization": True,
                        }
                    return {"ok": False, "violations": violations, "evidence_contract": contract}
            violations.append("tool_not_allowed_in_post_final_reject_rewrite_lane")
            contract["required_next_progress"] = (
                f"Rewrite lane requires {required_rewrite_tool} before terminal action."
            )
            return {"ok": False, "violations": violations, "evidence_contract": contract}

        if required_rewrite_tool == "repo_read":
            decision_paths = [_repo_rel_token(item) for item in _decision_paths(args) if _repo_rel_token(item)]

            def _matches_rewrite_gap(path: str) -> bool:
                if not required_rewrite_missing:
                    return path in required_rewrite_paths
                for gap in required_rewrite_paths:
                    if (
                        path == gap
                        or path.startswith(f"{gap}/")
                        or gap.startswith(f"{path}/")
                    ) and _path_allowed_by_missing_evidence(path, required_rewrite_missing):
                        return True
                return False

            if not decision_paths:
                violations.append("repo_read_not_allowed_post_final_reject_without_gap_match")
                contract["required_next_progress"] = (
                    "Rewrite lane requires repo_read on the remaining required_missing path(s), "
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
            if required_rewrite_missing and not violations:
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
            required_tool_call = (
                contract.get("required_next_tool_call")
                if isinstance(contract.get("required_next_tool_call"), dict)
                else {}
            )
            required_tool = str(required_tool_call.get("tool") or "").strip()
            required_missing = (
                contract.get("required_next_missing_evidences")
                if isinstance(contract.get("required_next_missing_evidences"), list)
                else []
            )
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
                # Check if this path was already flagged as forbidden (repeated attempt)
                forbidden_paths = contract.get("forbidden_repo_read_paths", [])
                if path in forbidden_paths:
                    # Planner is retrying a previously rejected path - escalate immediately
                    violations.append(f"repo_read_retry_forbidden_path:{path}")
                else:
                    # First time rejecting this path - track it as forbidden
                    violations.append(f"repo_read_path_not_from_prior_file_evidence:{path}")
                    forbidden_paths.append(path)
                    contract["forbidden_repo_read_paths"] = forbidden_paths[:20]
                    
                    # Force finalization if coverage satisfied and we have enough evidence
                    repeat_count = repeated_tool_call_count(history, tool, args)
                    coverage_satisfied_val = _minimum_read_coverage_satisfied()
                    may_choose_final_val = bool(contract.get("planner_may_choose_final")) or bool(
                        contract.get("finalization_contract", {}).get("planner_may_choose_final")
                    )
                    if coverage_satisfied_val and may_choose_final_val and repeat_count >= 1:
                        contract["planner_may_choose_final"] = True
                        contract["planner_may_choose_block"] = False
                        final_contract = (
                            contract.get("finalization_contract")
                            if isinstance(contract.get("finalization_contract"), dict)
                            else {}
                        )
                        final_contract["final_allowed"] = True
                        final_contract["planner_may_choose_final"] = True
                        final_contract.pop("reason", None)
                        contract["finalization_contract"] = final_contract
                        contract["required_next_progress"] = (
                            "repo_read rejected for path not from prior evidence; repeated retry detected "
                            "while coverage satisfied and final allowed. Synthesize terminal final from existing verified evidence "
                            "and read_notes; do not call additional tools."
                        )
                        return {
                            "ok": True,
                            "violations": [],
                            "evidence_contract": contract,
                            "forced_finalization": True,
                        }
                
                # Initialize final_contract before use in forced finalization guard
                final_contract = (
                    contract.get("finalization_contract")
                    if isinstance(contract.get("finalization_contract"), dict)
                    else {}
                )
                # Remove successfully read paths from missing_owner_paths to prevent retry loop
                successful = set()
                for p in contract.get("successful_repo_read_paths") if isinstance(contract.get("successful_repo_read_paths"), list) else []:
                    token = _repo_rel_token(p)
                    if token:
                        successful.add(token)
                if successful:
                    missing = _minimum_read_coverage_missing_owner_paths()
                    filtered_missing = [p for p in missing if p not in successful]
                    contract["missing_owner_paths"] = filtered_missing
                # Forced finalization guard: when repo_read is rejected for path not from prior evidence
                # AND the same invalid path has been retried (repeated call count >= 1), force finalization
                # if coverage is satisfied and final is allowed.
                repeat_count = repeated_tool_call_count(history, tool, args)
                coverage_satisfied_val = _minimum_read_coverage_satisfied()
                may_choose_final_val = bool(contract.get("planner_may_choose_final")) or bool(
                    final_contract.get("planner_may_choose_final")
                )
                if repeat_count >= 1 and coverage_satisfied_val and may_choose_final_val:
                    contract["planner_may_choose_final"] = True
                    contract["planner_may_choose_block"] = False
                    final_contract["final_allowed"] = True
                    final_contract["planner_may_choose_final"] = True
                    final_contract.pop("reason", None)
                    contract["finalization_contract"] = final_contract
                    contract["required_next_progress"] = (
                        "repo_read rejected for path not from prior evidence; repeated retry detected "
                        "while coverage satisfied and final allowed. Synthesize terminal final from existing verified evidence "
                        "and read_notes; do not call additional tools."
                    )
                    return {
                        "ok": True,
                        "violations": [],
                        "evidence_contract": contract,
                        "forced_finalization": True,
                    }
                contract = _escalate_final_rewrite_retry_count(
                    contract,
                    has_gap_route=bool(
                        contract.get("required_next_tool_call")
                        or contract.get("required_next_missing_evidences")
                    ),
                )
                
                # Initialize final_contract before use in forced finalization guard
                final_contract = (
                    contract.get("finalization_contract")
                    if isinstance(contract.get("finalization_contract"), dict)
                    else {}
                )
                # Remove successfully read paths from missing_owner_paths to prevent retry loop
                successful = set()
                for p in contract.get("successful_repo_read_paths") if isinstance(contract.get("successful_repo_read_paths"), list) else []:
                    token = _repo_rel_token(p)
                    if token:
                        successful.add(token)
                if successful:
                    missing = _minimum_read_coverage_missing_owner_paths()
                    filtered_missing = [p for p in missing if p not in successful]
                    contract["missing_owner_paths"] = filtered_missing
                # Forced finalization guard: when repo_read is rejected for path not from prior evidence
                # AND the same invalid path has been retried (repeated call count >= 1), force finalization
                # if coverage is satisfied and final is allowed.
                repeat_count = repeated_tool_call_count(history, tool, args)
                coverage_satisfied_val = _minimum_read_coverage_satisfied()
                may_choose_final_val = bool(contract.get("planner_may_choose_final")) or bool(
                    final_contract.get("planner_may_choose_final")
                )
                if repeat_count >= 1 and coverage_satisfied_val and may_choose_final_val:
                    contract["planner_may_choose_final"] = True
                    contract["planner_may_choose_block"] = False
                    final_contract["final_allowed"] = True
                    final_contract["planner_may_choose_final"] = True
                    final_contract.pop("reason", None)
                    contract["finalization_contract"] = final_contract
                    contract["required_next_progress"] = (
                        "repo_read rejected for path not from prior evidence; repeated retry detected "
                        "while coverage satisfied and final allowed. Synthesize terminal final from existing verified evidence "
                        "and read_notes; do not call additional tools."
                    )
                    return {
                        "ok": True,
                        "violations": [],
                        "evidence_contract": contract,
                        "forced_finalization": True,
                    }
                contract = _escalate_final_rewrite_retry_count(
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
        # Forced finalization guard: when identical tool calls repeat without progress and coverage
        # is satisfied with final allowed, force transition to action=final.
        coverage_satisfied_val = _minimum_read_coverage_satisfied()
        may_choose_final_val = bool(contract.get("planner_may_choose_final")) or bool(
            final_contract.get("planner_may_choose_final")
        )
        if coverage_satisfied_val and may_choose_final_val and tool not in {"final", "done"}:
            contract["planner_may_choose_final"] = True
            contract["planner_may_choose_block"] = False
            final_contract["final_allowed"] = True
            final_contract["planner_may_choose_final"] = True
            final_contract.pop("reason", None)
            contract["finalization_contract"] = final_contract
            contract["required_next_progress"] = (
                "Repeated identical tool call without progress detected while coverage satisfied "
                "and final allowed. Synthesize terminal final from existing verified evidence "
                "and read_notes; do not call additional tools."
            )
            return {
                "ok": True,
                "violations": [],
                "evidence_contract": contract,
                "forced_finalization": True,
            }

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
