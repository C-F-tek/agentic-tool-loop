"""Planner decision validator owner."""

from __future__ import annotations

import json
from typing import Any, Mapping


def validate_planner_decision_against_evidence(
    goal: str,
    decision: dict[str, Any],
    history: list[dict[str, Any]],
    require_native_tool_call: bool = False,
    *,
    deps: Mapping[str, Any],
    config: Mapping[str, Any],
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
    _final_answer_is_action_plan_without_code_product = deps["final_answer_is_action_plan_without_code_product"]
    _final_composition_tool_names_from_candidates = deps["final_composition_tool_names_from_candidates"]
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
    violations: list[str] = []

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
                "Use only the current turn tool surface; if the quality gate is satisfied, "
                "produce action=final instead of calling another tool."
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

    requested_limit = int(contract.get("requested_file_limit") or 0)
    target_scope = str(contract.get("resolved_goal_scope") or "")
    target_file = str(contract.get("resolved_goal_file") or "")
    target_kind = str(contract.get("target_kind") or "")
    review_goal = bool(contract.get("goal_requests_python_file_review"))
    known_paths = [str(x) for x in contract.get("known_paths_from_latest_repo_list_files") or []]
    admissible_reads = set(str(x) for x in (contract.get("validator_admissible_repo_read_paths") or []))
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
        if final_contract and final_contract.get("final_allowed") is False:
            violations.append("final_not_allowed_by_evidence_contract:" + str(final_contract.get("reason") or "insufficient evidence"))
        if post_write_validation_required and not post_write_validation_done:
            violations.append(
                "final_after_write_validation_failed"
                if post_write_validation_failed else
                "final_after_write_without_validation"
            )
        final_answer = str(decision.get("final_answer") or decision.get("answer") or decision.get("summary") or "")
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
        if _repo_analysis_goal(goal) and not final_answer.strip():
            violations.append("final_empty_answer")
        elif _repo_analysis_goal(goal):
            quality = _repo_analysis_final_answer_quality(final_answer, contract)
            quality_violations = (
                quality.get("violations")
                if isinstance(quality.get("violations"), list)
                else []
            )
            if quality_violations:
                violations.extend(str(v) for v in quality_violations)
                contract["repo_analysis_final_quality"] = quality
                contract["required_next_progress"] = quality.get("required_next_progress")
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
        result = {
            "ok": not violations,
            "violations": violations,
            "evidence_contract": contract,
            "quality_gate_internal_inconsistency": internal_inconsistencies,
        }
        if action_plan_candidate:
            result["action_plan_candidate"] = action_plan_candidate
            result["semantic_goal_classification"] = contract.get("semantic_goal_classification")
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
                # Existing files are valid only if they have been discovered in tree/list evidence.
                violations.append(f"repo_read_path_not_from_prior_file_evidence:{path}")
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
