"""
action_validators.py
====================
Validation logic for each planner action type (final / block / tool).

Each top-level function receives the complete validated context already
pre-extracted by the orchestrator and returns ``(violations, contract)``.
Callers should treat the returned *contract* as the authoritative updated
version (some helpers mutate it in place; returning it makes the data flow
explicit).
"""

from __future__ import annotations

import json
from typing import Any

from .rewrite_latch import coerce_latch_state, clear_terminal_block_state
from .contract_utils import (
    is_coverage_required,
    is_coverage_satisfied,
    missing_coverage_owner_paths,
)


# ---------------------------------------------------------------------------
# action=final
# ---------------------------------------------------------------------------

def validate_final_action(
    *,
    decision: dict[str, Any],
    contract: dict[str, Any],
    history: list[dict[str, Any]],
    # injected callables
    effective_repo_goal: bool,
    semantic_audit_goal: bool,
    apply_final_quality_route,
    repo_analysis_final_answer_quality,
    repo_analysis_final_answer_model_quality,
    contract_final_required_now,
    final_answer_is_action_plan_without_code_product,
    final_composition_tool_names_from_candidates,
    successful_code_edit_proposals,
    code_product_payload_violations,
    code_product_low_signal_target,
    goal_requires_code_product_report,
    path_under_scope,
    repo_readable_evidence_file,
    repo_rel_token,
    # pre-computed context
    target_kind: str,
    target_file: str,
    target_scope: str,
    review_goal: bool,
    requested_limit: int,
    read_ok: list[str],
    post_write_validation_required: bool,
    post_write_validation_done: bool,
    post_write_validation_failed: bool,
    latest_file_list_result,
    user_scope_claims: list[Any],
) -> tuple[list[str], dict[str, Any]]:
    """
    Validate ``action=final`` and return ``(violations, updated_contract)``.
    """
    violations: list[str] = []
    internal_inconsistencies: list[str] = []
    result_extras: dict[str, Any] = {}

    final_contract = _get_final_contract(contract)

    # --- Terminal-block guard ---
    violations, should_return = _check_terminal_block_disallows_final(
        violations, contract, final_contract
    )
    if should_return:
        return violations, contract

    # --- Finalization contract gate ---
    if final_contract and final_contract.get("final_allowed") is False:
        reason = final_contract.get("reason") or "insufficient evidence"
        violations.append(f"final_not_allowed_by_evidence_contract:{reason}")

    # --- Post-write validation ---
    if post_write_validation_required and not post_write_validation_done:
        violations.append(
            "final_after_write_validation_failed"
            if post_write_validation_failed
            else "final_after_write_without_validation"
        )

    final_answer = str(
        decision.get("final_answer")
        or decision.get("answer")
        or decision.get("summary")
        or ""
    )

    # --- Coverage ---
    if is_coverage_required(contract) and not is_coverage_satisfied(contract):
        violations.append("final_without_minimum_read_coverage")
        _apply_coverage_block(contract, final_contract)

    if _final_answer_declares_missing_coverage(final_answer):
        violations.append("final_declares_missing_read_coverage")

    # --- Code product ---
    action_plan_candidate = _validate_code_product(
        final_answer=final_answer,
        contract=contract,
        violations=violations,
        history=history,
        final_answer_is_action_plan_without_code_product=final_answer_is_action_plan_without_code_product,
        successful_code_edit_proposals=successful_code_edit_proposals,
        code_product_payload_violations=code_product_payload_violations,
        repo_rel_token=repo_rel_token,
    )
    if action_plan_candidate:
        result_extras["action_plan_candidate"] = action_plan_candidate
        result_extras["semantic_goal_classification"] = contract.get("semantic_goal_classification")

    # --- File / scope reads ---
    if target_kind == "file" and target_file and target_file not in read_ok:
        violations.append(f"final_without_requested_file_read:{target_file}")

    if target_scope:
        _validate_scope_reads(
            violations=violations,
            internal_inconsistencies=internal_inconsistencies,
            contract=contract,
            target_scope=target_scope,
            read_ok=read_ok,
            final_contract=final_contract,
            path_under_scope=path_under_scope,
            repo_readable_evidence_file=repo_readable_evidence_file,
            latest_file_list_result=latest_file_list_result,
        )

    # --- Repo/semantic quality gates ---
    if effective_repo_goal or semantic_audit_goal:
        _validate_repo_final_quality(
            final_answer=final_answer,
            contract=contract,
            violations=violations,
            history=history,
            apply_final_quality_route=apply_final_quality_route,
            repo_analysis_final_answer_quality=repo_analysis_final_answer_quality,
            repo_analysis_final_answer_model_quality=repo_analysis_final_answer_model_quality,
        )

    # --- Review-goal checks ---
    if review_goal and not read_ok:
        violations.append("final_without_successful_repo_read_for_python_review")

    if review_goal and target_scope:
        if any(not path_under_scope(p, target_scope) for p in read_ok):
            violations.append(
                f"final_uses_read_paths_outside_requested_scope:{target_scope}"
            )

    if review_goal and requested_limit:
        _validate_review_read_count(
            violations=violations,
            read_ok=read_ok,
            requested_limit=requested_limit,
            latest_file_list_result=latest_file_list_result,
        )

    # --- Clear latch on success ---
    if not violations:
        contract = clear_terminal_block_state(contract)

    result: dict[str, Any] = {
        "ok": not violations,
        "violations": violations,
        "evidence_contract": contract,
        "quality_gate_internal_inconsistency": internal_inconsistencies,
        "coverage_satisfied": is_coverage_satisfied(contract),
        "missing_owner_paths": missing_coverage_owner_paths(contract),
        **result_extras,
    }
    if isinstance(contract.get("required_next_tool_call"), dict):
        result["required_next_tool_call"] = contract["required_next_tool_call"]
    return violations, contract


# ---------------------------------------------------------------------------
# action=block
# ---------------------------------------------------------------------------

def validate_block_action(
    *,
    decision: dict[str, Any],
    contract: dict[str, Any],
    violations: list[str],
    # injected
    minimum_read_coverage_required,
    minimum_read_coverage_satisfied,
    minimum_read_coverage_missing_owner_paths,
    repo_rel_token,
) -> tuple[list[str], dict[str, Any]]:
    """
    Validate ``action=block`` and return ``(violations, updated_contract)``.

    Returns early ``(violations=[], contract)`` when block is legitimately
    forced by the controller.  Returns ``(violations, contract)`` with
    ``"block_not_allowed_by_evidence_contract"`` when block is premature.
    """
    reason = str(decision.get("reason") or "")
    reason_low = reason.lower()

    # --- Internal planner-format failures ---
    early = _check_planner_format_failures(reason, reason_low, violations, contract)
    if early is not None:
        return early

    # --- Degenerate / non-JSON output ---
    raw_planner_text = str(
        decision.get("raw_planner_text")
        or decision.get("raw_planner_text_preview")
        or decision.get("partial_content")
        or ""
    )
    if raw_planner_text and _is_degenerate_output(reason, reason_low):
        violations.append(f"planner_block_requires_controller_classification:{reason[:160]}")
        return violations, contract

    final_contract = _get_final_contract(contract)
    planner_forced, force_reason = _extract_forced_block(final_contract)
    contract["finalization_contract"] = final_contract

    planner_may_choose_block = bool(contract.get("planner_may_choose_block")) or bool(
        final_contract.get("planner_may_choose_block")
    )

    if planner_forced:
        contract["planner_may_choose_block"] = True
        if force_reason and not contract.get("required_next_progress"):
            contract["required_next_progress"] = (
                f"Controller-forced terminal block is active: {force_reason}. "
                "Consume and pass through this terminal signal."
            )
        return [], contract

    if not planner_may_choose_block:
        _apply_block_not_allowed(
            contract=contract,
            final_quality_reject_count=int(contract.get("planner_final_quality_reject_count") or 0),
            minimum_read_coverage_required=minimum_read_coverage_required,
            minimum_read_coverage_satisfied=minimum_read_coverage_satisfied,
            minimum_read_coverage_missing_owner_paths=minimum_read_coverage_missing_owner_paths,
        )
        violations.append("block_not_allowed_by_evidence_contract")
        return violations, contract

    return [], contract


# ---------------------------------------------------------------------------
# Per-tool argument validators
# ---------------------------------------------------------------------------

def validate_tool_arguments(
    tool: str,
    args: dict[str, Any],
    violations: list[str],
    *,
    any_argument_group_present,
    argument_value_present,
    repo_read_selector_present,
    planner_scratchpad_read_selector_present,
) -> None:
    """
    Append argument-level violations for the given *tool* to *violations*.
    All checks are argument-shape only; no contract or history needed here.
    """
    _TOOL_ARG_CHECKS = {
        "repo_search": (any_argument_group_present, [["query"], ["pattern"], ["symbol"]], "repo_search_missing_query_pattern_or_symbol"),
        "repo_semantic_search": (argument_value_present, "query", "repo_semantic_search_missing_query"),
        "repo_rg_search": (any_argument_group_present, [["query"], ["pattern"]], "repo_rg_search_missing_pattern"),
        "repo_jq_query": (any_argument_group_present, [["query"], ["filter"]], "repo_jq_query_missing_query"),
        "repo_ast_grep_search": (any_argument_group_present, [["pattern"], ["kind"]], "repo_ast_grep_search_missing_pattern_or_kind"),
        "repo_ast_grep_dry_run": (any_argument_group_present, [["pattern", "rewrite"]], "repo_ast_grep_dry_run_missing_pattern_or_rewrite"),
        "repo_tree_sitter_parse": (argument_value_present, "path", "repo_tree_sitter_parse_missing_path"),
        "repo_unidiff_validate": (any_argument_group_present, [["unified_diff"], ["diff"]], "repo_unidiff_validate_missing_diff"),
        "repo_git_apply_check": (any_argument_group_present, [["unified_diff"], ["diff"], ["patch"]], "repo_git_apply_check_missing_diff"),
        "repo_shellcheck": (any_argument_group_present, [["path"], ["paths"]], "repo_shellcheck_missing_path"),
        "repo_semgrep_scan": (any_argument_group_present, [["pattern"], ["config"]], "repo_semgrep_scan_missing_pattern_or_config"),
        "repo_hyperfine_benchmark": (argument_value_present, "commands", "repo_hyperfine_benchmark_missing_commands"),
        "repo_read": (repo_read_selector_present, None, "repo_read_missing_path_or_paths_items"),
        "planner_scratchpad_write": (any_argument_group_present, [["text"], ["content"]], "planner_scratchpad_write_missing_text"),
        "planner_scratchpad_read": (planner_scratchpad_read_selector_present, None, "planner_scratchpad_read_missing_selector"),
        "runtime_sqlite_memory_search": (any_argument_group_present, [["query"], ["tag"], ["kind"]], "runtime_sqlite_memory_search_missing_query_tag_or_kind"),
        "runtime_sqlite_memory_write": (any_argument_group_present, [["text"], ["content"]], "runtime_sqlite_memory_write_missing_text"),
        "terminal_search_files": (argument_value_present, "query", "terminal_search_files_missing_query"),
        "terminal_run_command_wait": (argument_value_present, "command", "terminal_run_command_wait_missing_command"),
        "repo_command": (argument_value_present, "command", "repo_command_missing_command"),
    }

    if tool not in _TOOL_ARG_CHECKS:
        return

    checker, check_arg, violation_key = _TOOL_ARG_CHECKS[tool]

    if checker is any_argument_group_present:
        if not any_argument_group_present(args, check_arg):
            violations.append(violation_key)
    elif checker is argument_value_present:
        if not argument_value_present(args, check_arg):
            violations.append(violation_key)
    elif checker is repo_read_selector_present:
        if not repo_read_selector_present(args):
            violations.append(violation_key)
    elif checker is planner_scratchpad_read_selector_present:
        if not planner_scratchpad_read_selector_present(args):
            violations.append(violation_key)


# ---------------------------------------------------------------------------
# Scratchpad-write special checks
# ---------------------------------------------------------------------------

def validate_scratchpad_write(
    args: dict[str, Any],
    violations: list[str],
    *,
    contract: dict[str, Any],
    final_composition_tool_names_from_candidates,
    successful_answer_chunk_signatures: set[str],
) -> None:
    """Extra validation rules specific to ``planner_scratchpad_write``."""
    kind = str(args.get("kind") or "").strip()
    text = str(args.get("text") or args.get("content") or "")

    if kind not in {"answer_chunk", "final_answer_chunk"}:
        return

    final_composition_tools = final_composition_tool_names_from_candidates(contract)
    if "planner_scratchpad_write" not in final_composition_tools:
        violations.append("planner_answer_chunk_without_final_composition_contract")

    if _answer_chunk_misuses_terminal_payload_shape(text):
        violations.append("planner_answer_chunk_tool_misused_for_terminal_payload")

    tag = str(args.get("tag") or "").strip()
    if tag and f"{kind}:{tag}" in successful_answer_chunk_signatures:
        violations.append("planner_answer_chunk_tag_already_written_without_progress")


# ---------------------------------------------------------------------------
# Internal helpers shared across validators
# ---------------------------------------------------------------------------

def _get_final_contract(contract: dict[str, Any]) -> dict[str, Any]:
    fc = contract.get("finalization_contract")
    return fc if isinstance(fc, dict) else {}


def _check_terminal_block_disallows_final(
    violations: list[str],
    contract: dict[str, Any],
    final_contract: dict[str, Any],
) -> tuple[list[str], bool]:
    """Return (violations, should_return_early)."""
    final_rewrite_latch = coerce_latch_state(contract.get("final_rewrite_latch"))
    forced_block_payload = final_contract.get("planner_forced_terminal_block")
    planner_forced, force_reason = _extract_forced_block(final_contract)
    contract["finalization_contract"] = final_contract

    planner_may_choose_block = bool(contract.get("planner_may_choose_block")) or bool(
        final_contract.get("planner_may_choose_block")
    )

    if (
        final_rewrite_latch == "terminal_block_required" and planner_may_choose_block
    ) or planner_forced:
        violations.append("terminal_block_required_final_disallowed")
        contract["terminal_block_final_retry_count"] = (
            int(contract.get("terminal_block_final_retry_count") or 0) + 1
        )
        contract.update(
            {
                "planner_cuda_rewrite_required": True,
                "final_rewrite_latch": "terminal_block_required",
                "planner_may_choose_final": False,
                "planner_may_choose_block": True,
                "required_next_progress": (
                    "Terminal block lane is active after repeated final-quality rejection. "
                    "Return action=block with the remaining blocker; do not emit another final."
                ),
            }
        )
        final_contract.update(
            {
                "final_allowed": False,
                "planner_may_choose_final": False,
                "planner_may_choose_block": True,
                "planner_forced_terminal_block": True,
                "planner_forced_terminal_block_reason": (
                    force_reason or "terminal_block_required_final_disallowed"
                ),
                "reason": "terminal_block_required_final_disallowed",
            }
        )
        contract["finalization_contract"] = final_contract
        return violations, True

    return violations, False


def _extract_forced_block(
    final_contract: dict[str, Any],
) -> tuple[bool, str]:
    """Return (is_forced, reason_str) from final_contract."""
    payload = final_contract.get("planner_forced_terminal_block")
    if isinstance(payload, dict):
        final_contract["planner_forced_terminal_block"] = bool(payload.get("enabled"))
        return bool(payload.get("enabled")), str(payload.get("reason") or "").strip()
    forced = bool(payload is True)
    reason = str(final_contract.get("planner_forced_terminal_block_reason") or "").strip()
    final_contract["planner_forced_terminal_block"] = forced
    return forced, reason


def _apply_coverage_block(
    contract: dict[str, Any], final_contract: dict[str, Any]
) -> None:
    missing = missing_coverage_owner_paths(contract)
    contract.update(
        {
            "required_next_progress": (
                "coverage_required: minimum_read_coverage.coverage_satisfied=false. "
                "Read/search the missing owner/core paths or return a typed block; do not final."
            ),
            "coverage_block": {
                "schema": "minimum_read_coverage.block.v1",
                "coverage_satisfied": False,
                "missing_owner_paths": missing,
            },
            "planner_may_choose_final": False,
        }
    )
    if isinstance(final_contract, dict):
        final_contract.update(
            {
                "final_allowed": False,
                "planner_may_choose_final": False,
                "coverage_satisfied": False,
                "missing_owner_paths": missing,
            }
        )
        contract["finalization_contract"] = final_contract


def _validate_scope_reads(
    *,
    violations: list[str],
    internal_inconsistencies: list[str],
    contract: dict[str, Any],
    target_scope: str,
    read_ok: list[str],
    final_contract: dict[str, Any],
    path_under_scope,
    repo_readable_evidence_file,
    latest_file_list_result,
) -> None:
    listed_rows = (
        contract.get("repo_list_files_evidence")
        if isinstance(contract.get("repo_list_files_evidence"), list)
        else []
    )
    scope_listed = bool(contract.get("latest_in_scope_repo_list_path")) or any(
        path_under_scope(str(row.get("path") or ""), target_scope)
        and str(row.get("path") or ".") not in ("", ".")
        for row in listed_rows
        if isinstance(row, dict)
    )
    scope_reads = [
        p for p in read_ok
        if path_under_scope(p, target_scope) and repo_readable_evidence_file(p)
    ]
    final_allowed = bool(final_contract.get("final_allowed")) if isinstance(final_contract, dict) else False

    if final_allowed and not scope_listed:
        internal_inconsistencies.append(
            f"quality_gate_internal_inconsistency:scope_listed_missing:{target_scope}"
        )
    if final_allowed and not scope_reads:
        internal_inconsistencies.append(
            f"quality_gate_internal_inconsistency:scope_reads_missing:{target_scope}"
        )
    if not scope_listed and not final_allowed:
        violations.append(f"final_without_in_scope_tree_or_list:{target_scope}")
    if not scope_reads and not final_allowed:
        violations.append(f"final_without_in_scope_concrete_read:{target_scope}")


def _validate_repo_final_quality(
    *,
    final_answer: str,
    contract: dict[str, Any],
    violations: list[str],
    history: list[dict[str, Any]],
    apply_final_quality_route,
    repo_analysis_final_answer_quality,
    repo_analysis_final_answer_model_quality,
) -> None:
    if not final_answer.strip():
        violations.append("final_empty_answer")
        return

    deterministic_quality = repo_analysis_final_answer_quality(final_answer, contract)
    contract["repo_analysis_final_deterministic_quality"] = deterministic_quality
    det_violations = (
        deterministic_quality.get("violations")
        if isinstance(deterministic_quality.get("violations"), list)
        else []
    )
    if det_violations:
        violations.extend(str(v) for v in det_violations)
        apply_final_quality_route(deterministic_quality)

    if callable(repo_analysis_final_answer_model_quality):
        quality = repo_analysis_final_answer_model_quality(
            final_answer, contract, history=history
        )
    else:
        quality = {
            "schema": "repo_analysis_final_model_quality.v1",
            "model_decision_available": False,
            "ok": False,
            "decision": "invalid",
            "violations": ["repo_analysis_final_model_quality_dependency_missing"],
            "required_next_progress": (
                "Final answer rejected because repo-analysis final quality has no model judge "
                "dependency.  Do not accept this final through deterministic heuristics."
            ),
        }

    quality_violations = (
        quality.get("violations") if isinstance(quality.get("violations"), list) else []
    )
    contract["repo_analysis_final_quality"] = quality
    if quality_violations:
        violations.extend(str(v) for v in quality_violations)
        apply_final_quality_route(quality if isinstance(quality, dict) else {})


def _validate_code_product(
    *,
    final_answer: str,
    contract: dict[str, Any],
    violations: list[str],
    history: list[dict[str, Any]],
    final_answer_is_action_plan_without_code_product,
    successful_code_edit_proposals,
    code_product_payload_violations,
    repo_rel_token,
) -> str:
    code_product_contract = (
        contract.get("code_product_contract")
        if isinstance(contract.get("code_product_contract"), dict)
        else {}
    )
    if not code_product_contract.get("required"):
        return ""

    action_plan_candidate = ""
    if final_answer_is_action_plan_without_code_product(final_answer):
        violations.append("final_action_plan_without_code_product")
        action_plan_candidate = final_answer

    verified_rows = (
        contract.get("verified_content_reads")
        if isinstance(contract.get("verified_content_reads"), list)
        else []
    )
    verified_paths = {
        repo_rel_token(row.get("path"))
        for row in verified_rows
        if isinstance(row, dict) and row.get("path")
    }
    proposals = successful_code_edit_proposals(history)
    if not proposals:
        violations.append("missing_code_product_candidate")
    else:
        violations.extend(code_product_payload_violations(proposals[-1], verified_paths))

    return action_plan_candidate


def _validate_review_read_count(
    *,
    violations: list[str],
    read_ok: list[str],
    requested_limit: int,
    latest_file_list_result,
) -> None:
    expected = requested_limit
    latest_list = latest_file_list_result(None)  # history not available here; caller must pass
    total_matches = latest_list.get("total_matches") if isinstance(latest_list, dict) else None
    if isinstance(total_matches, int) and total_matches > 0:
        expected = min(expected, total_matches)
    if len(read_ok) < expected:
        violations.append(f"final_before_required_read_count:{len(read_ok)}/{expected}")


def _check_planner_format_failures(
    reason: str,
    reason_low: str,
    violations: list[str],
    contract: dict[str, Any],
) -> tuple[list[str], dict[str, Any]] | None:
    """Return early result tuple if reason is an internal planner-format failure, else None."""
    if reason == "planner_final_required_empty_output":
        violations.append("planner_final_required_empty_output")
        contract["required_next_progress"] = (
            "Quality gate is satisfied and no tool surface was provided. "
            "Return a terminal final answer. Do not call tools."
        )
        return violations, contract

    if reason == "planner_native_tool_call_required":
        violations.append("planner_native_tool_call_required")
        contract["required_next_progress"] = (
            "Native tool mode is active and the planner emitted no message.tool_calls. "
            "Retry with one native tool_call from candidate_next_actions or return a real "
            "final/block answer when the evidence contract allows it."
        )
        return violations, contract

    if reason == "planner_native_mode_non_json_output":
        violations.append("planner_native_mode_non_json_output")
        contract["required_next_progress"] = (
            "Native tool mode is active and the planner emitted malformed protocol-shaped text. "
            "Retry with one native tool_call from candidate_next_actions, or return a terminal "
            "final/block answer when the evidence contract allows it."
        )
        return violations, contract

    return None


def _is_degenerate_output(reason: str, reason_low: str) -> bool:
    return (
        "invalid_planner_output_non_json" in reason_low
        or "non-json" in reason_low
        or "no_json" in reason_low
        or "degenerate" in reason_low
        or "timeout" in reason_low
        or reason.startswith("PLANNER_DEGENERATE_OUTPUT")
    )


def _apply_block_not_allowed(
    *,
    contract: dict[str, Any],
    final_quality_reject_count: int,
    minimum_read_coverage_required,
    minimum_read_coverage_satisfied,
    minimum_read_coverage_missing_owner_paths,
) -> None:
    coverage_required = minimum_read_coverage_required()
    coverage_satisfied = minimum_read_coverage_satisfied()
    coverage_missing = minimum_read_coverage_missing_owner_paths()
    required_tool = ""
    required_next_tool_call = contract.get("required_next_tool_call")
    if isinstance(required_next_tool_call, dict):
        required_tool = str(required_next_tool_call.get("tool") or "").strip()

    final_rewrite_latch = coerce_latch_state(contract.get("final_rewrite_latch"))

    if required_tool:
        msg = (
            "Block is not authorized by evidence contract while required_next_tool_call is pending. "
            f"Required tool: {required_tool}. "
            "Either execute the required tool path or return final only when final is explicitly allowed."
        )
    elif coverage_required and not coverage_satisfied:
        msg = (
            "Block is not authorized by evidence contract because minimum read coverage is not "
            f"satisfied; missing_owner_paths={coverage_missing[:12]}."
        )
    elif final_rewrite_latch:
        progress = str(contract.get("required_next_progress") or "")[:180] or "resolve remaining lane"
        msg = (
            "Block is not authorized by evidence contract while a final-rewrite/deadlock lane is "
            f"active; required_next_progress: {progress}. "
            "Resume rewrite using verified evidence and required evidence gaps."
        )
    else:
        msg = (
            f"Block is not authorized after {final_quality_reject_count} final-quality "
            f"reject{'s' if final_quality_reject_count != 1 else ''}; "
            "provide rewrite evidence before terminal."
        )

    contract["required_next_progress"] = msg


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


def _answer_chunk_misuses_terminal_payload_shape(text: str) -> bool:
    try:
        parsed = json.loads(str(text or ""))
    except Exception:
        return False
    if not isinstance(parsed, dict):
        return False
    return any(str(key) in parsed for key in ("final_answer", "answer", "summary"))