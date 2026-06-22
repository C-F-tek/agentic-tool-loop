"""
validate_decision.py
====================
Orchestrator for ``validate_planner_decision_against_evidence``.

This module owns the **public API** of the original monolithic file.
All signatures and return-dict shapes are preserved exactly.

Internal logic has been split into:
  - path_utils.py          — pure path helpers
  - contract_utils.py      — contract read helpers
  - rewrite_latch.py       — latch state-machine
  - final_quality_route.py — apply_final_quality_route + duplicate recovery
  - action_validators.py   — per-action validation (final / block / tool)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aicarmine_broker.application.evidence.audit_guidance import goal_requests_semantic_audit
from aicarmine_broker.application.evidence.goal_classifier import effective_repo_analysis_goal
from aicarmine_broker.application.shared.path_tokens import repo_path_token

from .contract_utils import known_contract_repo_paths, known_contract_repo_dirs
from .final_quality_route import (
    apply_final_quality_route,
    apply_duplicate_repo_read_path_recovery_contract,
)
from .path_utils import coalesce_repo_read_paths, collect_repo_paths, is_concrete_repo_path
from .rewrite_latch import coerce_latch_state, escalate_terminal_block_state


# ---------------------------------------------------------------------------
# Module-level helpers preserved from the original (public surface)
# ---------------------------------------------------------------------------

def _normalize_terminal_planner_decision(
    decision: dict[str, Any],
) -> dict[str, Any]:
    """Normalize terminal planner decision (lazy-import pattern preserved)."""
    from ...import_refs import _resolve_lazy

    _resolve_lazy(".tool_dispatch", ["dispatch_tool"])
    _resolve_lazy(".tool_contract", ["normalize_tool_name"])
    _resolve_lazy(".tool_contract", ["sanitize_tool_args"])
    return decision


def _list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _repo_path_is_concrete(token: Any) -> bool:
    """Preserved public name; delegates to path_utils."""
    return is_concrete_repo_path(token)


def _coalesce_repo_read_paths(values: Any) -> list[str]:
    """Preserved public name; delegates to path_utils."""
    return coalesce_repo_read_paths(values)


def _final_quality_repo_read_allowlist(contract: dict[str, Any]) -> set[str]:
    from .contract_utils import final_quality_repo_read_allowlist
    return final_quality_repo_read_allowlist(contract)


def _next_final_rewrite_latch(
    current: str,
    *,
    reject_count: int,
    has_gap_route: bool,
) -> str:
    from .rewrite_latch import next_latch_state
    return next_latch_state(current, reject_count=reject_count, has_gap_route=has_gap_route)


def _escalate_final_terminal_block_state(
    contract: dict[str, Any],
    *,
    has_gap_route: bool,
) -> dict[str, Any]:
    return escalate_terminal_block_state(contract, has_gap_route=has_gap_route)


def _clear_final_terminal_block_state(contract: dict[str, Any]) -> dict[str, Any]:
    from .rewrite_latch import clear_terminal_block_state
    return clear_terminal_block_state(contract)


def _collect_repo_paths(values: Any) -> set[str]:
    return collect_repo_paths(values)


def _known_contract_repo_paths(contract: dict[str, Any]) -> set[str]:
    return known_contract_repo_paths(contract)


def _known_contract_repo_dirs(contract: dict[str, Any]) -> set[str]:
    return known_contract_repo_dirs(contract)


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def validate_planner_decision_against_evidence(
    goal: str,
    decision: dict[str, Any],
    history: list[dict[str, Any]],
    require_native_tool_call: bool = False,
    *,
    deps: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Validate a planner decision against accumulated evidence.

    Parameters, return shape and all violation keys are identical to the
    original implementation.
    """
    # ------------------------------------------------------------------
    # 1. Unpack configuration
    # ------------------------------------------------------------------
    AGENTIC_PLANNER_NATIVE_TOOLS = config["AGENTIC_PLANNER_NATIVE_TOOLS"]
    CODE_PRODUCT_BUILD_STATE_KIND = config["CODE_PRODUCT_BUILD_STATE_KIND"]
    VALID_INTERNAL_TOOLS = config["VALID_INTERNAL_TOOLS"]
    SUPPORT_SUBTURN_TOOLS = frozenset(
        {
            "planner_scratchpad_read",
            "planner_scratchpad_write",
            "runtime_sqlite_memory_search",
            "runtime_sqlite_memory_write",
        }
    )

    # ------------------------------------------------------------------
    # 2. Unpack injected dependencies
    # ------------------------------------------------------------------
    _agentic_v2_decision_paths = deps["agentic_v2_decision_paths"]
    _agentic_v2_goal_scope = deps["agentic_v2_goal_scope"]
    _agentic_v2_read_has_window = deps["agentic_v2_read_has_window"]
    _agentic_v2_successful_read_paths = deps["agentic_v2_successful_read_paths"]
    _any_argument_group_present = deps["any_argument_group_present"]
    _apply_duplicate_window_replan_contract = deps["apply_duplicate_window_replan_contract"]
    _apply_unverified_old_text_replan_contract = deps["apply_unverified_old_text_replan_contract"]
    _argument_value_present = deps["argument_value_present"]
    _canonical_invalid_code_product_decision_signature = deps[
        "canonical_invalid_code_product_decision_signature"
    ]
    _code_product_build_state_duplicate_write = deps["code_product_build_state_duplicate_write"]
    _code_product_build_state_has_collecting_progress = deps[
        "code_product_build_state_has_collecting_progress"
    ]
    _code_product_build_state_parse = deps["code_product_build_state_parse"]
    _code_product_build_state_ready_payload = deps["code_product_build_state_ready_payload"]
    _code_product_low_signal_target = deps["code_product_low_signal_target"]
    _code_product_payload_violations = deps["code_product_payload_violations"]
    _contract_final_required_now = deps["contract_final_required_now"]
    _copyable_example_text = deps["copyable_example_text"]
    _decision_matches_prompt_context_continuation = deps[
        "decision_matches_prompt_context_continuation"
    ]
    _decision_paths = deps["decision_paths"]
    _enforce_required_scratchpad_read_continuation_contract = deps[
        "enforce_required_scratchpad_read_continuation_contract"
    ]
    _final_answer_is_action_plan_without_code_product = deps[
        "final_answer_is_action_plan_without_code_product"
    ]
    _final_composition_tool_names_from_candidates = deps[
        "final_composition_tool_names_from_candidates"
    ]
    _repo_analysis_final_answer_model_quality = deps.get(
        "repo_analysis_final_answer_model_quality"
    )
    _repo_analysis_final_answer_quality = deps["repo_analysis_final_answer_quality"]
    _invalid_code_product_decision_signature_count = deps[
        "invalid_code_product_decision_signature_count"
    ]
    _invalid_decision_signature_key = deps["invalid_decision_signature_key"]
    _native_required_tool_decision_has_transport_provenance = deps[
        "native_required_tool_decision_has_transport_provenance"
    ]
    _normalize_terminal_planner_decision_dep = deps["normalize_terminal_planner_decision"]
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
    _repeated_tool_call_count = deps["repeated_tool_call_count"]
    _scope_claim_conflict_for_path = deps["scope_claim_conflict_for_path"]
    _successful_window_signatures = deps["successful_window_signatures"]
    _target_scope_conflict_resolved = deps["target_scope_conflict_resolved"]
    _latest_file_list_result = deps["latest_file_list_result"]
    _goal_requires_code_product_report = deps["goal_requires_code_product_report"]
    _planner_evidence_contract = deps["planner_evidence_contract"]
    _validate_unified_diff_text = deps["validate_unified_diff_text"]

    # ------------------------------------------------------------------
    # 3. Normalise decision and extract top-level fields
    # ------------------------------------------------------------------
    decision = _normalize_terminal_planner_decision_dep(
        decision if isinstance(decision, dict) else {}
    )
    action = str(decision.get("action") or "tool").strip().lower()
    tool = _normalize_tool_name(str(decision.get("tool") or ""))
    args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}

    # ------------------------------------------------------------------
    # 4. Build evidence contract and semantic context
    # ------------------------------------------------------------------
    contract = _planner_evidence_contract(goal, history)
    semantic_contract = (
        contract.get("semantic_goal_classification")
        if isinstance(contract.get("semantic_goal_classification"), dict)
        else {}
    )
    effective_repo_goal = effective_repo_analysis_goal(
        goal, semantic_contract, repo_analysis_goal=_repo_analysis_goal
    )
    semantic_audit_goal = goal_requests_semantic_audit(goal)
    violations: list[str] = []

    # ------------------------------------------------------------------
    # 5. Prompt-context continuation
    # ------------------------------------------------------------------
    prompt_context_continuation_required = (
        decision.get("prompt_context_continuation_required")
        if isinstance(decision.get("prompt_context_continuation_required"), dict)
        else {}
    )
    prompt_context_continuation_matches = bool(
        prompt_context_continuation_required
        and _decision_matches_prompt_context_continuation(
            decision, prompt_context_continuation_required
        )
    )
    if prompt_context_continuation_required:
        contract = _enforce_required_scratchpad_read_continuation_contract(
            contract, prompt_context_continuation_required
        )

    # ------------------------------------------------------------------
    # 6. Prompt-window tracking guard
    # ------------------------------------------------------------------
    tracking_errors = _prompt_window_tracking_metadata_errors(history)
    if tracking_errors:
        return {
            "ok": False,
            "violations": ["prompt_context_window_tracking_errors"],
            "evidence_contract": contract,
            "prompt_window_tracking_errors": tracking_errors,
        }

    # ------------------------------------------------------------------
    # 7. Native-tool mode guard
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 8. Tool-surface guard
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 9. Scratchpad-read duplicate-window guard
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 10. Prompt-context continuation match guard
    # ------------------------------------------------------------------
    if prompt_context_continuation_required and not prompt_context_continuation_matches:
        violations.append("prompt_context_continuation_required")
        return {
            "ok": False,
            "violations": violations,
            "evidence_contract": contract,
            "required_prompt_context_continuation": prompt_context_continuation_required,
        }

    # ------------------------------------------------------------------
    # 11. Optional prompt-context window blocked when final required
    # ------------------------------------------------------------------
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
            "in the prompt and prior verified evidence. Do not consume optional "
            "prompt_context_window repo_read offsets linearly; if a concrete evidence gap "
            "remains, it must be named and resolved before the terminal final-required state "
            "with selective repo/RAG/search tools."
        )
        return {"ok": False, "violations": violations, "evidence_contract": contract}

    # ------------------------------------------------------------------
    # 12. Pre-compute common context for action routing
    # ------------------------------------------------------------------
    requested_limit = int(contract.get("requested_file_limit") or 0)
    target_scope = str(contract.get("resolved_goal_scope") or "")
    target_file = str(contract.get("resolved_goal_file") or "")
    target_kind = str(contract.get("target_kind") or "")
    review_goal = bool(contract.get("goal_requests_python_file_review"))

    known_paths_set: set[str] = set()
    for key in (
        "known_paths_from_latest_repo_list_files",
        "validator_admissible_repo_read_paths",
        "read_admissible_paths",
        "covered_owner_paths",
        "candidate_owner_paths",
        "missing_owner_paths",
        "successful_repo_read_paths",
    ):
        known_paths_set.update(collect_repo_paths(contract.get(key)))

    for item in contract.get("file_memory") if isinstance(contract.get("file_memory"), list) else []:
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
    admissible_reads = set(str(x) for x in collect_repo_paths(contract.get("validator_admissible_repo_read_paths")))
    admissible_reads.update(collect_repo_paths(contract.get("read_admissible_paths")))
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

    # ------------------------------------------------------------------
    # 13. Build closures needed by inner helpers
    # ------------------------------------------------------------------

    def _successful_read_paths_for_final_route() -> set[str]:
        successful: set[str] = set()
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

    def _stale_required_next_repo_read_paths() -> set[str]:
        paths: set[str] = set()
        for row in contract.get("stale_required_next_tool_calls") if isinstance(contract.get("stale_required_next_tool_calls"), list) else []:
            if not isinstance(row, dict) or str(row.get("tool") or "") != "repo_read":
                continue
            row_args = row.get("arguments") if isinstance(row.get("arguments"), dict) else {}
            for path in row_args.get("paths", []) if isinstance(row_args.get("paths"), list) else [row_args.get("path")]:
                token = _repo_rel_token(path)
                if token:
                    paths.add(token)
        return paths

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

    # Partial apply_final_quality_route with all injected deps pre-bound
    def _apply_final_quality_route(quality: dict[str, Any]) -> None:
        apply_final_quality_route(
            quality,
            contract,
            repo_rel_token=_repo_rel_token,
            path_exists_repo_relative=_path_exists_repo_relative,
            repo_readable_evidence_file=_repo_readable_evidence_file,
            successful_read_paths_for_final_route=_successful_read_paths_for_final_route,
            stale_required_next_repo_read_paths=_stale_required_next_repo_read_paths,
            history=history,
        )

    # ------------------------------------------------------------------
    # 14. Route to action-specific validator
    # ------------------------------------------------------------------

    if action in {"final", "done", "complete", "completed"}:
        return _handle_final_action(
            decision=decision,
            contract=contract,
            violations=violations,
            history=history,
            effective_repo_goal=effective_repo_goal,
            semantic_audit_goal=semantic_audit_goal,
            apply_final_quality_route=_apply_final_quality_route,
            repo_analysis_final_answer_quality=_repo_analysis_final_answer_quality,
            repo_analysis_final_answer_model_quality=_repo_analysis_final_answer_model_quality,
            contract_final_required_now=_contract_final_required_now,
            final_answer_is_action_plan_without_code_product=_final_answer_is_action_plan_without_code_product,
            final_composition_tool_names_from_candidates=_final_composition_tool_names_from_candidates,
            successful_code_edit_proposals=deps["successful_code_edit_proposals"],
            code_product_payload_violations=_code_product_payload_violations,
            code_product_low_signal_target=_code_product_low_signal_target,
            goal_requires_code_product_report=_goal_requires_code_product_report,
            path_under_scope=_path_under_scope,
            repo_readable_evidence_file=_repo_readable_evidence_file,
            repo_rel_token=_repo_rel_token,
            target_kind=target_kind,
            target_file=target_file,
            target_scope=target_scope,
            review_goal=review_goal,
            requested_limit=requested_limit,
            read_ok=read_ok,
            post_write_validation_required=post_write_validation_required,
            post_write_validation_done=post_write_validation_done,
            post_write_validation_failed=post_write_validation_failed,
            latest_file_list_result=_latest_file_list_result,
            user_scope_claims=user_scope_claims,
        )

    if action in {"block", "blocked", "need_user", "needs_user"}:
        return _handle_block_action(
            decision=decision,
            contract=contract,
            violations=violations,
            contract_coverage_required=lambda: (
                not contract.get("minimum_read_coverage", {}).get("coverage_satisfied")
                if isinstance(contract.get("minimum_read_coverage"), dict)
                else contract.get("coverage_satisfied") is not True
            ),
            contract_coverage_satisfied=lambda: (
                contract.get("minimum_read_coverage", {}).get("coverage_satisfied") is True
                if isinstance(contract.get("minimum_read_coverage"), dict)
                else contract.get("coverage_satisfied") is True
            ),
            contract_coverage_missing=lambda: (
                [str(p) for p in contract.get("minimum_read_coverage", {}).get("missing_owner_paths", [])]
                if isinstance(contract.get("minimum_read_coverage"), dict)
                else [str(p) for p in contract.get("missing_owner_paths", [])]
            ),
            repo_rel_token=_repo_rel_token,
        )

    # ------------------------------------------------------------------
    # 15. action=tool validation
    # ------------------------------------------------------------------
    if action != "tool":
        violations.append(f"invalid_action:{action or '<empty>'}")
        return {"ok": False, "violations": violations, "evidence_contract": contract}

    if not tool:
        violations.append("missing_tool")
        return {"ok": False, "violations": violations, "evidence_contract": contract}

    if tool not in VALID_INTERNAL_TOOLS:
        violations.append(f"invalid_tool:{tool}")
        return {"ok": False, "violations": violations, "evidence_contract": contract}

    # Final-required gate
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

    # Rewrite-lane enforcement
    final_reject_count = int(contract.get("planner_final_quality_reject_count") or 0)
    final_rewrite_latch = coerce_latch_state(contract.get("final_rewrite_latch"))
    rewrite_active = final_rewrite_latch != "inactive" and final_reject_count >= 1

    if rewrite_active:
        contract, violations, early = _enforce_rewrite_lane(
            tool=tool,
            args=args,
            contract=contract,
            violations=violations,
            history=history,
            SUPPORT_SUBTURN_TOOLS=SUPPORT_SUBTURN_TOOLS,
            prompt_context_continuation_required=prompt_context_continuation_required,
            prompt_context_continuation_matches=prompt_context_continuation_matches,
            repo_rel_token=_repo_rel_token,
            decision_paths=_decision_paths,
        )
        if early:
            return {"ok": False, "violations": violations, "evidence_contract": contract}

    # Per-tool argument checks
    from .action_validators import validate_tool_arguments, validate_scratchpad_write
    validate_tool_arguments(
        tool,
        args,
        violations,
        any_argument_group_present=_any_argument_group_present,
        argument_value_present=_argument_value_present,
        repo_read_selector_present=_repo_read_selector_present,
        planner_scratchpad_read_selector_present=_planner_scratchpad_read_selector_present,
    )
    if tool == "planner_scratchpad_write":
        validate_scratchpad_write(
            args,
            violations,
            contract=contract,
            final_composition_tool_names_from_candidates=_final_composition_tool_names_from_candidates,
            successful_answer_chunk_signatures=_successful_answer_chunk_signatures(),
        )

    if violations:
        return {"ok": False, "violations": violations, "evidence_contract": contract}

    # Code-product build-state write
    if tool == "planner_scratchpad_write" and str(args.get("kind") or "") == CODE_PRODUCT_BUILD_STATE_KIND:
        violations = _validate_code_product_build_state(
            args=args,
            contract=contract,
            violations=violations,
            code_product_contract=code_product_contract,
            read_ok=read_ok,
            target_file=target_file,
            repo_rel_token=_repo_rel_token,
            code_product_build_state_parse=_code_product_build_state_parse,
            code_product_build_state_has_collecting_progress=_code_product_build_state_has_collecting_progress,
            code_product_build_state_duplicate_write=_code_product_build_state_duplicate_write,
            code_product_build_state_ready_payload=_code_product_build_state_ready_payload,
            history=history,
        )
        if violations:
            return {"ok": False, "violations": violations, "evidence_contract": contract}

    # Scope check
    computed_target_scope = _agentic_v2_goal_scope(str(goal or ""), contract)
    if computed_target_scope and tool in _SCOPE_CHECKED_TOOLS:
        out_of_scope = [
            p for p in _agentic_v2_decision_paths(tool, args)
            if p and not _path_under_scope(p, computed_target_scope)
        ]
        if out_of_scope:
            for p in out_of_scope[:5]:
                violations.append(
                    f"{tool}_scope_mismatch:path={p}:expected_under={computed_target_scope}"
                )
            return {"ok": False, "violations": violations, "evidence_contract": contract}

    # repo_read specific checks
    if tool == "repo_read":
        contract, violations, early = _validate_repo_read(
            args=args,
            contract=contract,
            violations=violations,
            history=history,
            final_reject_count=final_reject_count,
            final_rewrite_latch=final_rewrite_latch,
            rewrite_active=rewrite_active,
            known_paths=known_paths,
            admissible_reads=admissible_reads,
            apply_required=apply_required,
            apply_patch_applied=apply_patch_applied,
            apply_read_targets=apply_read_targets,
            target_scope=target_scope,
            repo_rel_token=_repo_rel_token,
            decision_paths=_decision_paths,
            agentic_v2_read_has_window=_agentic_v2_read_has_window,
            agentic_v2_successful_read_paths=_agentic_v2_successful_read_paths,
            agentic_v2_decision_paths=_agentic_v2_decision_paths,
            repo_read_window_signature=_repo_read_window_signature,
            successful_window_signatures=_successful_window_signatures,
            apply_duplicate_window_replan_contract=_apply_duplicate_window_replan_contract,
            path_exists_repo_relative=_path_exists_repo_relative,
            duplicate_repo_read_recovery=lambda repeated: apply_duplicate_repo_read_path_recovery_contract(
                contract,
                repeated,
                history,
                repo_rel_token=_repo_rel_token,
                decision_paths=_decision_paths,
                minimum_read_coverage_satisfied=lambda: (
                    contract.get("minimum_read_coverage", {}).get("coverage_satisfied") is True
                    if isinstance(contract.get("minimum_read_coverage"), dict)
                    else contract.get("coverage_satisfied") is True
                ),
            ),
            escalate_final_terminal_block_state=lambda: escalate_terminal_block_state(
                contract,
                has_gap_route=bool(
                    contract.get("required_next_tool_call")
                    or contract.get("required_next_missing_evidences")
                ),
            ),
        )
        if early:
            return {"ok": False, "violations": violations, "evidence_contract": contract}

    if tool == "planner_scratchpad_read":
        window_signature = _planner_scratchpad_window_signature(args)
        if window_signature and window_signature in _successful_window_signatures(history, "planner_scratchpad_read"):
            violation = "planner_scratchpad_window_already_successful_without_progress"
            violations.append(violation)
            contract = _apply_duplicate_window_replan_contract(
                contract, violation=violation, tool=tool, args=args, history=history
            )
            return {"ok": False, "violations": violations, "evidence_contract": contract}

    # repo_list_files checks
    if tool == "repo_list_files":
        violations = _validate_repo_list_files(
            args=args,
            contract=contract,
            violations=violations,
            known_paths=known_paths,
            target_scope=target_scope,
            review_goal=review_goal,
            requested_limit=requested_limit,
            target_file=target_file,
            history=history,
            path_exists_repo_relative=_path_exists_repo_relative,
            repo_path_kind=_repo_path_kind,
            path_under_scope=_path_under_scope,
            repo_rel_token=_repo_rel_token,
            repeated_tool_call_count=_repeated_tool_call_count,
        )

    if tool == "repo_tree" and _repeated_tool_call_count(history, tool, args) >= 1:
        violations.append("repeated_same_tool_arguments_without_progress")

    # Write tools
    if tool in {"repo_read", "repo_apply_patch", "repo_write_file", "repo_propose_code_edit"}:
        violations = _validate_write_tools(
            tool=tool,
            args=args,
            contract=contract,
            violations=violations,
            history=history,
            read_ok=read_ok,
            target_scope=target_scope,
            apply_required=apply_required,
            apply_patch_applied=apply_patch_applied,
            apply_read_targets=apply_read_targets,
            known_paths=known_paths,
            admissible_reads=admissible_reads,
            user_scope_claims=user_scope_claims,
            goal_requires_code_product_report=_goal_requires_code_product_report,
            goal=goal,
            repo_rel_token=_repo_rel_token,
            decision_paths=_decision_paths,
            path_exists_repo_relative=_path_exists_repo_relative,
            path_under_scope=_path_under_scope,
            copyable_example_text=_copyable_example_text,
            old_text_verified_by_repo_read=_old_text_verified_by_repo_read,
            scope_claim_conflict_for_path=_scope_claim_conflict_for_path,
            target_scope_conflict_resolved=_target_scope_conflict_resolved,
            code_product_low_signal_target=_code_product_low_signal_target,
            apply_unverified_old_text_replan_contract=_apply_unverified_old_text_replan_contract,
            validate_unified_diff_text=_validate_unified_diff_text,
            repeated_tool_call_count=_repeated_tool_call_count,
            escalate_terminal_block_state=lambda: escalate_terminal_block_state(
                contract,
                has_gap_route=bool(
                    contract.get("required_next_tool_call")
                    or contract.get("required_next_missing_evidences")
                ),
            ),
        )

    if _repeated_tool_call_count(history, tool, args) >= 2:
        violations.append("repeated_same_tool_arguments_without_progress")

    # Invalid signature tracking
    invalid_signature = _canonical_invalid_code_product_decision_signature(decision, violations)
    invalid_repeat_count = _invalid_code_product_decision_signature_count(history, invalid_signature)
    if invalid_signature:
        contract, violations = _track_invalid_signature(
            contract=contract,
            violations=violations,
            invalid_signature=invalid_signature,
            invalid_repeat_count=invalid_repeat_count,
            invalid_decision_signature_key=_invalid_decision_signature_key,
        )

    response: dict[str, Any] = {
        "ok": not violations,
        "violations": violations,
        "evidence_contract": contract,
    }
    if invalid_signature:
        response["invalid_decision_signature"] = invalid_signature
        response["invalid_decision_repeat_count"] = invalid_repeat_count + 1
    return response


# ---------------------------------------------------------------------------
# Action routing helpers (keep orchestrator lean)
# ---------------------------------------------------------------------------

def _handle_final_action(*, decision, contract, violations, history, **kwargs) -> dict[str, Any]:
    """Route action=final through action_validators and return full result dict."""
    from .action_validators import validate_final_action

    # validate_final_action returns (violations, updated_contract)
    # but also builds the full result dict internally via its sub-helpers.
    # We re-build it here so the orchestrator owns the final shape.
    final_violations, contract = validate_final_action(
        decision=decision,
        contract=contract,
        history=history,
        **kwargs,
    )
    from .contract_utils import is_coverage_satisfied, missing_coverage_owner_paths
    result: dict[str, Any] = {
        "ok": not final_violations,
        "violations": final_violations,
        "evidence_contract": contract,
        "quality_gate_internal_inconsistency": [],
        "coverage_satisfied": is_coverage_satisfied(contract),
        "missing_owner_paths": missing_coverage_owner_paths(contract),
    }
    if isinstance(contract.get("required_next_tool_call"), dict):
        result["required_next_tool_call"] = contract["required_next_tool_call"]
    return result


def _handle_block_action(
    *, decision, contract, violations, repo_rel_token, **kwargs
) -> dict[str, Any]:
    from .action_validators import validate_block_action

    block_violations, contract = validate_block_action(
        decision=decision,
        contract=contract,
        violations=violations,
        minimum_read_coverage_required=kwargs["contract_coverage_required"],
        minimum_read_coverage_satisfied=kwargs["contract_coverage_satisfied"],
        minimum_read_coverage_missing_owner_paths=kwargs["contract_coverage_missing"],
        repo_rel_token=repo_rel_token,
    )
    return {
        "ok": not block_violations,
        "violations": block_violations,
        "evidence_contract": contract,
    }


def _enforce_rewrite_lane(
    *,
    tool,
    args,
    contract,
    violations,
    history,
    SUPPORT_SUBTURN_TOOLS,
    prompt_context_continuation_required,
    prompt_context_continuation_matches,
    repo_rel_token,
    decision_paths,
) -> tuple[dict[str, Any], list[str], bool]:
    """
    Enforce the post-final-reject rewrite lane rules.
    Returns (contract, violations, should_return_early).
    """
    required_tool_call = contract.get("required_next_tool_call") if isinstance(contract.get("required_next_tool_call"), dict) else {}
    required_missing = contract.get("required_next_missing_evidences")
    required_tool = str(required_tool_call.get("tool") or "").strip()
    required_rewrite_paths: list[str] = []

    if required_tool == "repo_read":
        tool_args = required_tool_call.get("arguments") if isinstance(required_tool_call.get("arguments"), dict) else {}
        for raw_path in (tool_args.get("paths", []) if isinstance(tool_args.get("paths"), list) else []):
            path = repo_rel_token(raw_path)
            if path:
                required_rewrite_paths.append(path)
        if not required_rewrite_paths:
            path = repo_rel_token(tool_args.get("path"))
            if path:
                required_rewrite_paths.append(path)

    if not required_tool_call and not required_tool:
        violations.append("tool_not_allowed_in_post_final_reject_rewrite_lane")
        contract["required_next_progress"] = (
            "Rewrite lane requires a concrete required_next_tool_call, "
            "but it has no tool or path arguments."
        )
        return contract, violations, True

    if tool != required_tool:
        if tool in SUPPORT_SUBTURN_TOOLS:
            if not (prompt_context_continuation_required and prompt_context_continuation_matches):
                violations.append("support_subturn_validation_failed")
                contract["support_subturn_rewrite_retry_count"] = (
                    int(contract.get("support_subturn_rewrite_retry_count") or 0) + 1
                )
                if contract["support_subturn_rewrite_retry_count"] >= 2:
                    contract.update(
                        {
                            "final_rewrite_latch": "terminal_block_required",
                            "planner_may_choose_block": True,
                            "planner_may_choose_final": False,
                            "required_next_tool_call": {},
                            "required_next_progress": (
                                "Rewrite lane support-subturn loop detected. "
                                "Return a rewritten terminal final from verified evidence, "
                                "or explicit block with remaining evidence gaps."
                            ),
                        }
                    )
                    contract.pop("required_next_tool_call_validated", None)
                    contract.pop("required_next_tool_call_validation_source", None)
                else:
                    contract["required_next_progress"] = (
                        f"Rewrite lane requires {required_tool} as the next tool, "
                        "or a rewritten final."
                    )
                return contract, violations, True
        violations.append("tool_not_allowed_in_post_final_reject_rewrite_lane")
        contract["required_next_progress"] = (
            f"Rewrite lane requires {required_tool} before terminal action."
        )
        return contract, violations, True

    if required_tool == "repo_read":
        decision_path_tokens = [
            repo_rel_token(item) for item in decision_paths(args) if repo_rel_token(item)
        ]

        def _matches_rewrite_gap(path: str) -> bool:
            if not required_missing:
                return path in required_rewrite_paths
            for gap in required_rewrite_paths:
                if (
                    path == gap
                    or path.startswith(f"{gap}/")
                    or gap.startswith(f"{path}/")
                ) and _path_allowed_by_missing_evidence(path, required_missing, repo_rel_token):
                    return True
            return False

        if not decision_path_tokens:
            violations.append("repo_read_not_allowed_post_final_reject_without_gap_match")
            contract["required_next_progress"] = (
                f"Rewrite lane requires repo_read on the remaining required missing path(s), "
                f"{required_rewrite_paths}"
            )
        else:
            for path in decision_path_tokens:
                if not _matches_rewrite_gap(path):
                    violations.append(
                        f"repo_read_not_allowed_post_final_reject_without_gap_match:{path}"
                    )

        if not violations:
            if coerce_latch_state(contract.get("final_rewrite_latch")) == "terminal_block_required":
                contract["planner_may_choose_block"] = True
            if required_missing or required_rewrite_paths:
                required_tool_call["validated"] = True
                required_tool_call["validation_source"] = "deterministic_validator"
                contract["required_next_tool_call"] = required_tool_call
                contract["required_next_tool_call_validated"] = True
                contract["required_next_tool_call_validation_source"] = "deterministic_validator"
            else:
                violations.append("repo_read_not_allowed_without_required_next_paths")
                contract.pop("required_next_tool_call_validated", None)
                contract.pop("required_next_tool_call_validation_source", None)
                contract["required_next_progress"] = (
                    "Rewrite lane requires a concrete required_next_tool_call, "
                    "but it has no path arguments."
                )

        if violations:
            return contract, violations, True

    return contract, violations, False


def _path_allowed_by_missing_evidence(
    path: str, required_missing: Any, repo_rel_token
) -> bool:
    token = repo_rel_token(path)
    if not token:
        return False
    for item in (required_missing if isinstance(required_missing, (list, tuple, set)) else []):
        required = repo_rel_token(item)
        if not required:
            continue
        if (
            token == required
            or token.startswith(f"{required}/")
            or required.startswith(f"{token}/")
        ):
            return True
    return False


def _validate_repo_read(
    *,
    args,
    contract,
    violations,
    history,
    final_reject_count,
    final_rewrite_latch,
    rewrite_active,
    known_paths,
    admissible_reads,
    apply_required,
    apply_patch_applied,
    apply_read_targets,
    target_scope,
    repo_rel_token,
    decision_paths,
    agentic_v2_read_has_window,
    agentic_v2_successful_read_paths,
    agentic_v2_decision_paths,
    repo_read_window_signature,
    successful_window_signatures,
    apply_duplicate_window_replan_contract,
    path_exists_repo_relative,
    duplicate_repo_read_recovery,
    escalate_final_terminal_block_state,
) -> tuple[dict[str, Any], list[str], bool]:
    """Return (contract, violations, should_return_early)."""
    # Rewrite-only repo_read gate
    if rewrite_active:
        required_tool_call = contract.get("required_next_tool_call") if isinstance(contract.get("required_next_tool_call"), dict) else {}
        required_tool = str(required_tool_call.get("tool") or "").strip()
        required_missing = contract.get("required_next_missing_evidences")
        decision_path_tokens = [repo_rel_token(item) for item in decision_paths(args) if repo_rel_token(item)]

        if required_tool and required_tool != "repo_read":
            violations.append("repo_read_not_allowed_post_final_reject_without_explicit_repo_read_gap")
        elif required_missing:
            for path in decision_path_tokens:
                if not _path_allowed_by_missing_evidence(path, required_missing, repo_rel_token):
                    violations.append(f"repo_read_not_allowed_without_gap_match:{path}")
        else:
            if final_rewrite_latch in {"rewrite_required", "required_gap_only"}:
                violations.append("repo_read_not_allowed_post_final_reject_without_explicit_repo_read_gap")
            else:
                violations.append("repo_read_disallowed_post_final_reject_without_missing_gap")

        if violations:
            return contract, violations, True

    # Duplicate window check
    window_signature = repo_read_window_signature(args)
    if window_signature and window_signature in successful_window_signatures(history, "repo_read"):
        violation = "repo_read_window_already_successful_without_progress"
        violations.append(violation)
        contract = apply_duplicate_window_replan_contract(
            contract, violation=violation, tool="repo_read", args=args, history=history
        )
        return contract, violations, True

    # Already-successful path check
    if not agentic_v2_read_has_window(args):
        already_read = set(agentic_v2_successful_read_paths(history))
        repeated_reads = [p for p in agentic_v2_decision_paths("repo_read", args) if p in already_read]
        if repeated_reads:
            violations.append("repo_read_already_successful:" + ",".join(repeated_reads[:5]))
            contract = duplicate_repo_read_recovery(repeated_reads)
            return contract, violations, True

    return contract, violations, False


def _validate_repo_list_files(
    *,
    args,
    contract,
    violations,
    known_paths,
    target_scope,
    review_goal,
    requested_limit,
    target_file,
    history,
    path_exists_repo_relative,
    repo_path_kind,
    path_under_scope,
    repo_rel_token,
    repeated_tool_call_count,
) -> list[str]:
    path = repo_rel_token(args.get("path") or ".") or "."
    suffix = str(args.get("suffix") or args.get("glob") or "")

    if not path_exists_repo_relative(path):
        violations.append(f"non_existing_path:{path}")
    if repo_path_kind(path) == "file":
        violations.append(f"repo_list_files_on_file_path_use_repo_read:{path}")
    if target_scope and not path_under_scope(path, target_scope):
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
    if review_goal and target_file and not path_under_scope(target_file, target_scope):
        violations.append(f"repo_list_files_target_file_outside_scope:{target_file}:expected_under={target_scope}")
    if repeated_tool_call_count(history, "repo_list_files", args) >= 1 and known_paths:
        violations.append("repeated_repo_list_files_after_useful_file_list")

    return violations


def _validate_write_tools(
    *,
    tool,
    args,
    contract,
    violations,
    history,
    read_ok,
    target_scope,
    apply_required,
    apply_patch_applied,
    apply_read_targets,
    known_paths,
    admissible_reads,
    user_scope_claims,
    goal_requires_code_product_report,
    goal,
    repo_rel_token,
    decision_paths,
    path_exists_repo_relative,
    path_under_scope,
    copyable_example_text,
    old_text_verified_by_repo_read,
    scope_claim_conflict_for_path,
    target_scope_conflict_resolved,
    code_product_low_signal_target,
    apply_unverified_old_text_replan_contract,
    validate_unified_diff_text,
    repeated_tool_call_count,
    escalate_terminal_block_state,
) -> list[str]:
    paths = decision_paths(args)
    if tool == "repo_apply_patch" and args.get("path"):
        paths = [str(args.get("path"))]
    if tool == "repo_propose_code_edit" and (args.get("target_file") or args.get("path")):
        paths = [repo_rel_token(args.get("target_file") or args.get("path"))]

    if not paths:
        violations.append(
            "repo_read_missing_path_or_paths_items"
            if tool == "repo_read"
            else f"{tool}_missing_path_or_paths"
        )

    for path in paths:
        path = repo_rel_token(path)

        if target_scope and tool == "repo_read" and not path_under_scope(path, target_scope):
            violations.append(f"repo_read_path_outside_requested_scope:{path}:expected_under={target_scope}")

        if tool == "repo_read" and apply_required and not apply_patch_applied:
            if not apply_read_targets:
                violations.append(f"repo_read_not_allowed_without_apply_targets:{path}")
            elif path not in apply_read_targets:
                violations.append(f"repo_read_outside_apply_write_targets:{path}")

        if tool == "repo_read" and known_paths and path not in known_paths and path not in admissible_reads:
            violations.append(f"repo_read_path_not_from_prior_file_evidence:{path}")
            escalate_terminal_block_state()

        if tool in {"repo_read", "repo_apply_patch", "repo_propose_code_edit"} and not path_exists_repo_relative(path):
            violations.append(f"non_existing_path:{path}")

        if tool == "repo_apply_patch":
            old_value = args.get("old_text")
            new_value = args.get("new_text")
            if copyable_example_text(old_value) or copyable_example_text(new_value):
                violations.append("repo_apply_patch_placeholder_text")
                contract = apply_unverified_old_text_replan_contract(
                    contract, target_file=path, violation="repo_apply_patch_placeholder_text", history=history
                )
            elif isinstance(old_value, str) and old_value and not old_text_verified_by_repo_read(history, path, old_value):
                violations.append("repo_apply_patch_old_text_not_from_verified_read")
                contract = apply_unverified_old_text_replan_contract(
                    contract, target_file=path, violation="repo_apply_patch_old_text_not_from_verified_read", history=history
                )

        if tool == "repo_propose_code_edit" and path not in set(read_ok):
            violations.append(f"code_product_target_not_read:{path}")

        if tool == "repo_propose_code_edit":
            claim_conflict = scope_claim_conflict_for_path(path, user_scope_claims)
            if claim_conflict and not target_scope_conflict_resolved(path, args, contract):
                if "target_scope_conflict_unresolved" not in violations:
                    violations.append("target_scope_conflict_unresolved")

        if (
            tool == "repo_propose_code_edit"
            and not target_scope
            and goal_requires_code_product_report(goal)
            and code_product_low_signal_target(path, contract)
        ):
            violations.append(f"code_product_low_signal_target:{path}")

    if tool == "repo_propose_code_edit":
        violations = _validate_propose_code_edit(
            args=args,
            paths=paths,
            contract=contract,
            violations=violations,
            history=history,
            read_ok=read_ok,
            repo_rel_token=repo_rel_token,
            copyable_example_text=copyable_example_text,
            old_text_verified_by_repo_read=old_text_verified_by_repo_read,
            apply_unverified_old_text_replan_contract=apply_unverified_old_text_replan_contract,
            validate_unified_diff_text=validate_unified_diff_text,
            repeated_tool_call_count=repeated_tool_call_count,
        )

    return violations


def _validate_propose_code_edit(
    *,
    args,
    paths,
    contract,
    violations,
    history,
    read_ok,
    repo_rel_token,
    copyable_example_text,
    old_text_verified_by_repo_read,
    apply_unverified_old_text_replan_contract,
    validate_unified_diff_text,
    repeated_tool_call_count,
) -> list[str]:
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
                if repeated_tool_call_count(history, "repo_propose_code_edit", args) >= 1:
                    violations.append("code_product_route_shift_required")
            elif copyable_example_text(old_value) or copyable_example_text(new_value):
                violations.append("repo_propose_code_edit_placeholder_text")
                if paths:
                    contract = apply_unverified_old_text_replan_contract(
                        contract, target_file=paths[0], violation="repo_propose_code_edit_placeholder_text", history=history
                    )
                if repeated_tool_call_count(history, "repo_propose_code_edit", args) >= 1:
                    violations.append("code_product_route_shift_required")
            elif paths and not old_text_verified_by_repo_read(history, paths[0], old_value):
                violations.append("repo_propose_code_edit_old_text_not_from_verified_read")
                contract = apply_unverified_old_text_replan_contract(
                    contract, target_file=paths[0], violation="repo_propose_code_edit_old_text_not_from_verified_read", history=history
                )
                if repeated_tool_call_count(history, "repo_propose_code_edit", args) >= 1:
                    violations.append("code_product_route_shift_required")
        else:
            diff_errors = validate_unified_diff_text(
                unified_diff=diff_text,
                target_file=paths[0] if paths else str(args.get("target_file") or args.get("path") or ""),
                require_unidiff=True,
            )
            blocking = [str(e) for e in diff_errors if str(e) != "unidiff_dependency_missing"]
            if blocking:
                violations.append("invalid_code_product_candidate")
                violations.extend(
                    f"repo_propose_code_edit_unified_diff_error:{e}" for e in blocking[:6]
                )
                if repeated_tool_call_count(history, "repo_propose_code_edit", args) >= 1:
                    violations.append("code_product_route_shift_required")

    if edit_kind == "structured_edit" and not isinstance(args.get("structured_operations"), list):
        violations.append("repo_propose_code_edit_missing_structured_operations")
        if repeated_tool_call_count(history, "repo_propose_code_edit", args) >= 1:
            violations.append("code_product_route_shift_required")

    if edit_kind == "no_op" and (
        args.get("unified_diff")
        or args.get("structured_operations")
        or args.get("old_text")
        or args.get("new_text")
    ):
        violations.append("repo_propose_code_edit_no_op_has_patch_payload")

    return violations


def _validate_code_product_build_state(
    *,
    args,
    contract,
    violations,
    code_product_contract,
    read_ok,
    target_file,
    repo_rel_token,
    code_product_build_state_parse,
    code_product_build_state_has_collecting_progress,
    code_product_build_state_duplicate_write,
    code_product_build_state_ready_payload,
    history,
) -> list[str]:
    if not code_product_contract.get("required"):
        violations.append("code_product_build_state_write_outside_code_product_contract")

    state_text = str(args.get("text") or args.get("content") or "")
    state = code_product_build_state_parse(state_text)
    if not state:
        violations.append("code_product_build_state_invalid_payload")
        return violations

    state_target = repo_rel_token(
        args.get("target_file") or args.get("path") or state.get("target_file") or ""
    )
    if not state_target or state_target == ".":
        violations.append("code_product_build_state_missing_target")
    elif state_target not in set(read_ok):
        violations.append(f"code_product_build_state_target_not_read:{state_target}")

    status = str(state.get("status") or "")
    if status not in {"collecting_source", "ready_for_propose", "blocked_incomplete"}:
        violations.append("code_product_build_state_invalid_status")
    if status == "collecting_source" and not code_product_build_state_has_collecting_progress(state):
        violations.append("code_product_build_state_collecting_source_without_progress")
    if code_product_build_state_duplicate_write(history, target_file=state_target, text=state_text):
        violations.append("code_product_build_state_duplicate_without_progress")
    if status == "ready_for_propose" and not code_product_build_state_ready_payload(state):
        violations.append("code_product_build_state_ready_without_complete_payload")
    if status == "blocked_incomplete" and not str(state.get("blocker") or "").strip():
        violations.append("code_product_build_state_blocked_without_blocker")

    return violations


def _track_invalid_signature(
    *,
    contract,
    violations,
    invalid_signature,
    invalid_repeat_count,
    invalid_decision_signature_key,
) -> tuple[dict[str, Any], list[str]]:
    code_contract = contract.get("code_product_contract") if isinstance(contract.get("code_product_contract"), dict) else {}
    code_contract["latest_invalid_decision_signature"] = invalid_signature
    code_contract["latest_invalid_decision_repeat_count"] = invalid_repeat_count + 1

    if invalid_repeat_count >= 1:
        raw_disallowed = contract.get("disallowed_next_decision_signatures")
        disallowed = [
            item for item in (raw_disallowed if isinstance(raw_disallowed, list) else [])
            if isinstance(item, dict)
        ]
        entry = {**invalid_signature, "repeat_count": invalid_repeat_count + 1, "rule": "do_not_repeat_invalid_code_product_decision"}
        if invalid_decision_signature_key(invalid_signature) not in {
            invalid_decision_signature_key(item) for item in disallowed
        }:
            disallowed.append(entry)
        contract["disallowed_next_decision_signatures"] = disallowed
        code_contract["disallowed_next_decision_signatures"] = disallowed

    if invalid_repeat_count >= 2 and "planner_repeated_invalid_code_product_decision" not in violations:
        violations.append("planner_repeated_invalid_code_product_decision")
        code_contract["terminal_blocker"] = "planner_repeated_invalid_code_product_decision"

    contract["code_product_contract"] = code_contract
    return contract, violations


# ---------------------------------------------------------------------------
# Constant
# ---------------------------------------------------------------------------

_SCOPE_CHECKED_TOOLS = frozenset(
    {
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
    }
)