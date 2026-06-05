"""Planner evidence contract builder owner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aicarmine_broker.application.evidence.coverage_scorer import score_evidence_coverage
from aicarmine_broker.application.planner.required_progress import required_next_progress_from_text
from aicarmine_broker.application.tool_surface.candidate_action_gate import gate_candidate_actions
from aicarmine_broker.application.tool_surface.action_proof_ledger import attach_action_proof


@dataclass(frozen=True)
class EvidenceBuilder:
    """Owner for planner evidence contract construction."""

    _deps: Mapping[str, Any]
    _config: Mapping[str, Any]

    def build(
        self,
        goal: str,
        history: list[dict[str, Any]],
        intrinsic_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        deps = self._deps
        config = self._config
        CODE_PRODUCT_BUILD_STATE_KIND = config["CODE_PRODUCT_BUILD_STATE_KIND"]
        LAB_REPO = config["LAB_REPO"]
        REPO_CONCRETE_READ_TARGET = config["REPO_CONCRETE_READ_TARGET"]
        SCOPED_CONCRETE_READ_TARGET = config["SCOPED_CONCRETE_READ_TARGET"]
        _agentic_v2_decision_paths = deps["agentic_v2_decision_paths"]
        _agentic_v2_enrich_evidence_contract = deps["agentic_v2_enrich_evidence_contract"]
        _agentic_v2_goal_scope = deps["agentic_v2_goal_scope"]
        _apply_turn_surface_policy = deps["apply_turn_surface_policy"]
        _build_operational_notebook = deps["build_operational_notebook"]
        _candidate_actions_from_evidence = deps["candidate_actions_from_evidence"]
        _canonical_invalid_code_product_decision_signature = deps["canonical_invalid_code_product_decision_signature"]
        _code_product_action_has_complete_payload = deps["code_product_action_has_complete_payload"]
        _code_product_build_state_propose_action = deps["code_product_build_state_propose_action"]
        _code_product_build_state_read_action = deps["code_product_build_state_read_action"]
        _code_product_build_state_write_action = deps["code_product_build_state_write_action"]
        _code_product_candidate_action = deps["code_product_candidate_action"]
        _code_product_payload_rejection_count = deps["code_product_payload_rejection_count"]
        _code_product_payload_violations = deps["code_product_payload_violations"]
        _code_product_source_window_candidate = deps["code_product_source_window_candidate"]
        _compact_validation_rejections_tail = deps["compact_validation_rejections_tail"]
        _core_discovery_candidates_from_intrinsic = deps["core_discovery_candidates_from_intrinsic"]
        _disallowed_invalid_code_product_signatures = deps["disallowed_invalid_code_product_signatures"]
        _failed_code_edit_proposal_validation_row = deps["failed_code_edit_proposal_validation_row"]
        _file_memory_from_history = deps["file_memory_from_history"]
        _goal_exact_text_block = deps["goal_exact_text_block"]
        _goal_target_file = deps["goal_target_file"]
        _goal_target_kind = deps["goal_target_kind"]
        _initial_orientation_surface_from_history = deps["initial_orientation_surface_from_history"]
        _input_error_goal = deps["input_error_goal"]
        _latest_code_product_build_state = deps["latest_code_product_build_state"]
        _low_signal_top_dir = deps["low_signal_top_dir"]
        _meaningful_read_candidates_from_evidence = deps["meaningful_read_candidates_from_evidence"]
        _path_exists_repo_relative = deps["path_exists_repo_relative"]
        _path_under_scope = deps["path_under_scope"]
        _paths_from_list_rows = deps["paths_from_list_rows"]
        _paths_from_result = deps["paths_from_result"]
        _rank_core_candidates = deps["rank_core_candidates"]
        _repo_analysis_goal = deps["repo_analysis_goal"]
        _repo_code_file = deps["repo_code_file"]
        _repo_doc_or_config = deps["repo_doc_or_config"]
        _repo_list_evidence = deps["repo_list_evidence"]
        _repo_readable_evidence_file = deps["repo_readable_evidence_file"]
        _repo_rel_token = deps["repo_rel_token"]
        _repo_required_read_count = deps["repo_required_read_count"]
        _scope_read_candidates_from_evidence = deps["scope_read_candidates_from_evidence"]
        _scoped_required_read_count = deps["scoped_required_read_count"]
        _user_scope_claims = deps["user_scope_claims"]
        _verified_repo_read_content_rows = deps["verified_repo_read_content_rows"]
        goal_requested_repo_scope = deps["goal_requested_repo_scope"]
        goal_requests_apply = deps["goal_requests_apply"]
        goal_requests_code_product = deps["goal_requests_code_product"]
        goal_requests_python_file_review = deps["goal_requests_python_file_review"]
        history_has_tool = deps["history_has_tool"]
        latest_file_list_result = deps["latest_file_list_result"]
        requested_file_limit_from_goal = deps["requested_file_limit_from_goal"]
        semantic_goal_classification = deps["semantic_goal_classification"]
        successful_code_edit_proposals = deps["successful_code_edit_proposals"]
        successful_repo_read_paths = deps["successful_repo_read_paths"]
        failed_repo_read_paths = deps["failed_repo_read_paths"]
        failed_repo_list_files_paths = deps["failed_repo_list_files_paths"]

        semantic_classification = semantic_goal_classification(goal)
        latest_list = latest_file_list_result(history)
        known_paths = _paths_from_result(latest_list) if latest_list else []
        requested_limit = requested_file_limit_from_goal(goal, 0)
        target_file = _goal_target_file(goal)
        target_scope = "" if target_file else (_agentic_v2_goal_scope(goal, {}) or goal_requested_repo_scope(goal))
        target_kind = _goal_target_kind(goal)
        read_ok = successful_repo_read_paths(history)
        verified_read_rows = _verified_repo_read_content_rows(history)
        verified_read_paths = [str(row.get("path")) for row in verified_read_rows if row.get("path")]
        verified_read_path_set = set(verified_read_paths)
        missing_full_content_reads = [
            p for p in read_ok
            if p not in verified_read_path_set and _repo_readable_evidence_file(p)
        ]
        read_failed = failed_repo_read_paths(history)
        list_failed = failed_repo_list_files_paths(history)
        list_rows = _repo_list_evidence(history)
        file_memory = _file_memory_from_history(history)
        doc_reads = [p for p in verified_read_paths if _repo_doc_or_config(p)]
        code_reads = [p for p in verified_read_paths if _repo_code_file(p)]
        root_surface_done = any(
            row.get("path") in ("", ".") for row in list_rows
        ) or any(
            isinstance(item, dict)
            and (item.get("tool_result") or {}).get("tool") == "repo_tree"
            and (item.get("tool_result") or {}).get("ok")
            for item in history if isinstance(item, dict)
        )
        meaningful_lists = [
            row.get("path") for row in list_rows
            if row.get("path") not in (None, "", ".") and not _low_signal_top_dir(str(row.get("path")))
        ]
        meaningful_content_reads = [
            p for p in verified_read_paths
            if any(_path_under_scope(p, str(area)) for area in meaningful_lists)
            and _repo_readable_evidence_file(p)
        ]
        repo_available_read_candidates = _meaningful_read_candidates_from_evidence(list_rows)
        repo_required_read_count = _repo_required_read_count(repo_available_read_candidates)
        repo_goal = _repo_analysis_goal(goal)
        repo_goal_class = str(semantic_classification.get("class") or "")
        analysis_only_repo_goal = (
            repo_goal
            and repo_goal_class == "analysis_only"
            and not bool(semantic_classification.get("must_produce_code_product"))
            and not goal_requests_apply(goal)
        )
        orientative_repo_final_goal = (
            repo_goal
            and repo_goal_class in {"analysis_only", "action_plan_only"}
            and not bool(semantic_classification.get("must_produce_code_product"))
            and not goal_requests_apply(goal)
        )
        repo_final_required_read_count = (
            min(repo_required_read_count, 10)
            if orientative_repo_final_goal
            else repo_required_read_count
        )
        scoped_inspection = bool(target_scope)
        file_read_done = bool(target_file and target_file in verified_read_path_set)
        scope_listed = bool(target_scope and any(_path_under_scope(str(row.get("path") or ""), target_scope) and str(row.get("path") or ".") not in ("", ".") for row in list_rows))
        scope_content_reads = [
            p for p in verified_read_paths
            if target_scope
            and _path_under_scope(p, target_scope)
            and _repo_readable_evidence_file(p)
        ]
        scope_available_read_candidates = _scope_read_candidates_from_evidence(list_rows, target_scope) if target_scope else []
        scope_required_read_count = _scoped_required_read_count(scope_available_read_candidates) if target_scope else 0
        user_scope_claims = _user_scope_claims(goal, target_scope)
        core_discovery_candidates, core_discovery_status = _core_discovery_candidates_from_intrinsic(
            intrinsic_context=intrinsic_context,
            list_rows=list_rows,
            read_ok=read_ok,
            target_scope=target_scope,
            user_scope_claims=user_scope_claims,
        )
        all_listed_paths = _paths_from_list_rows(list_rows)
        validator_admissible_read_paths: list[str] = []
        for path in (
            known_paths
            + all_listed_paths
            + repo_available_read_candidates
            + scope_available_read_candidates
            + [
                str(item.get("path") or "")
                for item in core_discovery_candidates
                if isinstance(item, dict)
            ]
            + read_ok
        ):
            p = _repo_rel_token(path)
            if p and p not in validator_admissible_read_paths:
                validator_admissible_read_paths.append(p)
        final_allowed = False
        final_reason = "No generic final fallback. Final requires explicit evidence for the actual goal."
        if _input_error_goal(goal):
            final_allowed = False
            final_reason = "Bridge/input error: missing natural-language user request. Do not invent a repository-analysis goal."
        elif target_kind == "file":
            final_allowed = file_read_done
            final_reason = (
                f"File evidence exists for {target_file}: direct repo_read succeeded."
                if final_allowed else
                f"Need direct repo_read evidence for requested file {target_file}."
            )
        elif scoped_inspection:
            final_allowed = bool(scope_listed and len(scope_content_reads) >= scope_required_read_count)
            final_reason = (
                f"Scoped evidence exists for {target_scope}: in-scope tree/list and "
                f"{len(scope_content_reads)}/{scope_required_read_count} verified concrete readable file reads."
                if final_allowed else
                f"Need scoped evidence for {target_scope}: repo_tree/list under scope and "
                f"{len(scope_content_reads)}/{scope_required_read_count} verified concrete readable file reads "
                f"(up to {SCOPED_CONCRETE_READ_TARGET}, bounded by discovered candidates)."
            )
        elif repo_goal:
            strict_repo_evidence_sufficient = bool(
                root_surface_done
                and len(doc_reads) >= 3
                and len(meaningful_lists) >= 1
                and len(meaningful_content_reads) >= repo_required_read_count
            )
            analysis_repo_evidence_sufficient = bool(
                orientative_repo_final_goal
                and root_surface_done
                and len(doc_reads) >= 3
                and len(meaningful_lists) >= 1
                and len(meaningful_content_reads) >= 1
                and len(verified_read_rows) >= repo_final_required_read_count
            )
            final_allowed = bool(strict_repo_evidence_sufficient or analysis_repo_evidence_sufficient)
            final_reason = (
                (
                    "Analysis/action-plan repository evidence exists: root surface, multiple docs/config reads, "
                    f"one meaningful non-infra/code area, {len(meaningful_content_reads)} verified reads "
                    f"inside meaningful areas, and {len(verified_read_rows)}/{repo_final_required_read_count} "
                    "total verified content reads. The 20-read target remains orientative, not a hard final gate."
                )
                if analysis_repo_evidence_sufficient and not strict_repo_evidence_sufficient else
                (
                    "Codex-quality repository evidence exists: root surface, multiple docs/config reads, "
                    f"one meaningful non-infra/code area, and {len(meaningful_content_reads)}/"
                    f"{repo_required_read_count} verified concrete readable reads inside meaningful areas."
                )
                if final_allowed else
                (
                    "Need root surface + at least 3 markdown/config reads + one meaningful non-infra/code area "
                    f"+ {len(meaningful_content_reads)}/{repo_final_required_read_count} verified concrete readable reads "
                    "for analysis/action-plan finalization "
                    f"(target {REPO_CONCRETE_READ_TARGET} remains orientative and bounded by discovered candidates)."
                )
            )
        else:
            # Non-repository goals may still finish only after a planner final with
            # evidence. Do not use this branch to auto-legitimize a one-step repo_tree.
            final_allowed = bool(read_ok or meaningful_lists)
            final_reason = (
                "Non-repository goal has some executed evidence." if final_allowed
                else "Need at least one relevant tool result; no generic final fallback."
            )
        if goal_requests_apply(goal) and not history_has_tool(history, "repo_apply_patch"):
            final_allowed = False
            final_reason = "Apply/edit/write goal requires repo_apply_patch after verified repo_read old_text evidence."

        core_candidates = _rank_core_candidates(file_memory, list_rows)
        candidates = _candidate_actions_from_evidence(
            goal,
            file_memory,
            list_rows,
            read_ok,
            final_allowed,
            list_failed,
            core_discovery_candidates,
        )
        candidate_repo_read_paths: list[str] = []
        for action in candidates:
            if not isinstance(action, dict) or action.get("tool") != "repo_read":
                continue
            args = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
            raw_paths: list[Any] = []
            if args.get("path") not in (None, "", [], {}):
                raw_paths.append(args.get("path"))
            if isinstance(args.get("paths"), list):
                raw_paths.extend(args.get("paths") or [])
            for raw_path in raw_paths:
                if isinstance(raw_path, dict):
                    continue
                p = _repo_rel_token(raw_path)
                if (
                    p
                    and p != "."
                    and p not in candidate_repo_read_paths
                    and p not in read_ok
                    and _path_exists_repo_relative(p)
                    and _repo_readable_evidence_file(p)
                ):
                    candidate_repo_read_paths.append(p)
        for p in candidate_repo_read_paths:
            if p not in validator_admissible_read_paths:
                validator_admissible_read_paths.append(p)
        code_product_required = bool(semantic_classification.get("must_produce_code_product")) and not goal_requests_apply(goal)
        code_product_proposals = successful_code_edit_proposals(history)
        latest_code_product = code_product_proposals[-1] if code_product_proposals else {}
        latest_code_product_violations = (
            _code_product_payload_violations(latest_code_product, verified_read_path_set)
            if latest_code_product else ["missing_code_product_candidate"]
        )
        code_product_blocks_final = code_product_required and bool(latest_code_product_violations)
        code_product_candidate_target = ""
        code_product_candidate_line_count = 0
        if code_product_blocks_final:
            candidate_paths = [target_file]
            ranked_code_reads = sorted(
                [
                    row for row in verified_read_rows
                    if _repo_code_file(str(row.get("path") or ""))
                    and (
                        target_file
                        or (
                            not str(row.get("path") or "").endswith("__init__.py")
                            and not str(row.get("path") or "").endswith("__main__.py")
                            and int(row.get("line_count") or 0) >= 20
                        )
                    )
                ],
                key=lambda row: (
                    str(row.get("path") or "").endswith("__init__.py"),
                    str(row.get("path") or "").endswith("__main__.py"),
                    -int(row.get("line_count") or 0),
                    str(row.get("path") or ""),
                ),
            )
            candidate_paths.extend(str(row.get("path") or "") for row in ranked_code_reads)
            if target_file:
                candidate_paths.extend([*code_reads, *scope_content_reads, *verified_read_paths])
            for candidate_path in candidate_paths:
                p = _repo_rel_token(candidate_path)
                if p and p != "." and p in verified_read_path_set:
                    code_product_candidate_target = p
                    for row in verified_read_rows:
                        if _repo_rel_token(row.get("path") or "") == p:
                            try:
                                code_product_candidate_line_count = int(row.get("line_count") or 0)
                            except Exception:
                                code_product_candidate_line_count = 0
                            break
                    break
        code_product_build_state = _latest_code_product_build_state(
            history,
            code_product_candidate_target or target_file,
        )
        if (
            code_product_blocks_final
            and not code_product_candidate_target
            and _repo_rel_token(code_product_build_state.get("target_file") or "") in verified_read_path_set
        ):
            code_product_candidate_target = _repo_rel_token(code_product_build_state.get("target_file") or "")
        if code_product_blocks_final:
            final_allowed = False
            final_reason = (
                "Code-product goal requires repo_propose_code_edit ok=true before final. "
                "Latest code-product violations: "
                + ", ".join(str(v) for v in latest_code_product_violations)
            )
            if code_product_candidate_target:
                code_candidate = _code_product_candidate_action(
                    target_file=code_product_candidate_target,
                    latest_violations=latest_code_product_violations,
                    goal=goal,
                )
                if code_candidate and not any(
                    item.get("tool") == "repo_propose_code_edit"
                    and (item.get("arguments") or {}).get("target_file") == code_product_candidate_target
                    for item in candidates
                    if isinstance(item, dict)
                ):
                    candidates.insert(0, code_candidate)

        validation_rejections: list[dict[str, Any]] = []
        for item in history if isinstance(history, list) else []:
            result = item.get("tool_result") if isinstance(item, dict) and isinstance(item.get("tool_result"), dict) else {}
            if result.get("tool") == "controller_guard" or result.get("violations"):
                validation_rejections.append({
                    "step": item.get("step"),
                    "guard_type": result.get("guard_type"),
                    "summary": result.get("summary"),
                    "classification": result.get("classification"),
                    "semantic_goal_classification": result.get("semantic_goal_classification"),
                    "next_instruction": result.get("next_instruction"),
                    "action_plan_candidate": result.get("action_plan_candidate"),
                    "raw_planner_text_preview": result.get("raw_planner_text_preview"),
                    "violations": result.get("violations") or [],
                    "rejected_decision": result.get("rejected_decision") or {},
                    "invalid_decision_signature": (
                        result.get("invalid_decision_signature")
                        if isinstance(result.get("invalid_decision_signature"), dict)
                        else _canonical_invalid_code_product_decision_signature(
                            result.get("rejected_decision") if isinstance(result.get("rejected_decision"), dict) else {},
                            result.get("violations") if isinstance(result.get("violations"), list) else [],
                        )
                    ),
                })
            else:
                failed_code_edit_row = _failed_code_edit_proposal_validation_row(item)
                if failed_code_edit_row:
                    failed_code_edit_row["invalid_decision_signature"] = (
                        failed_code_edit_row.get("invalid_decision_signature")
                        if isinstance(failed_code_edit_row.get("invalid_decision_signature"), dict)
                        else _canonical_invalid_code_product_decision_signature(
                            failed_code_edit_row.get("rejected_decision")
                            if isinstance(failed_code_edit_row.get("rejected_decision"), dict) else {},
                            failed_code_edit_row.get("violations")
                            if isinstance(failed_code_edit_row.get("violations"), list) else [],
                        )
                    )
                    validation_rejections.append(failed_code_edit_row)
        action_plan_candidate = ""
        for row in reversed(validation_rejections):
            candidate = str(row.get("action_plan_candidate") or "").strip()
            if candidate:
                action_plan_candidate = candidate
                break
        disallowed_invalid_decision_signatures = _disallowed_invalid_code_product_signatures(
            validation_rejections
        )

        contract = {
            "contract_type": "planner_decides_controller_validates",
            "planner_must_decide_next_action": True,
            "controller_may_reject_but_must_not_replace_planner_reasoning": True,
            "controller_must_not_auto_read_or_auto_final": True,
            "semantic_goal_classification": semantic_classification,
            "goal_requests_python_file_review": goal_requests_python_file_review(goal),
            "goal_requests_code_product": goal_requests_code_product(goal),
            "goal_requires_code_product_report": code_product_required,
            "goal_requests_apply": goal_requests_apply(goal),
            "action_plan_candidate": action_plan_candidate or None,
            "requested_file_limit": requested_limit or None,
            "target_kind": target_kind,
            "resolved_goal_file": target_file or None,
            "resolved_goal_scope": target_scope or None,
            "known_paths_from_latest_repo_list_files": known_paths[:120],
            "known_paths_total_in_latest_digest": len(known_paths),
            "successful_repo_read_paths": read_ok[:160],
            "successful_repo_read_count": len(read_ok),
            "verified_content_read_count": len(verified_read_rows),
            "verified_content_reads": verified_read_rows[:160],
            "missing_full_content_reads": missing_full_content_reads[:160],
            "user_scope_claims": user_scope_claims[:12],
            "core_discovery_status": core_discovery_status,
            "core_discovery_candidates": core_discovery_candidates[:16],
            "scoped_concrete_read_target": SCOPED_CONCRETE_READ_TARGET if target_scope else None,
            "scoped_concrete_read_required": scope_required_read_count or None,
            "scoped_available_read_candidates": scope_available_read_candidates[:120],
            "scoped_concrete_read_count": len(scope_content_reads),
            "repo_concrete_read_target": REPO_CONCRETE_READ_TARGET if repo_goal else None,
            "repo_concrete_read_target_is_orientative": bool(orientative_repo_final_goal) if repo_goal else None,
            "repo_concrete_read_required": repo_final_required_read_count if repo_goal else None,
            "repo_concrete_read_strict_required": repo_required_read_count if repo_goal else None,
            "repo_available_read_candidates": repo_available_read_candidates[:160] if repo_goal else [],
            "repo_concrete_read_count": len(meaningful_content_reads) if repo_goal else None,
            "repo_goal_final_target_is_orientative": bool(orientative_repo_final_goal) if repo_goal else None,
            "failed_repo_read_paths": read_failed[:120],
            "failed_repo_list_files_paths": list_failed[:120],
            "repo_list_files_evidence": list_rows[-10:],
            "file_memory": file_memory[:32],
            "ranked_core_candidate_dirs": core_candidates,
            "candidate_next_actions": candidates,
            "disallowed_next_decision_signatures": disallowed_invalid_decision_signatures,
            "planner_may_choose_final": final_allowed,
            "read_admissible_paths": validator_admissible_read_paths[:400],
            "validator_admissible_repo_read_paths": validator_admissible_read_paths[:400],
            "code_product_contract": {
                "required": code_product_required,
                "required_tool": "repo_propose_code_edit" if code_product_required else None,
                "successful_proposal_count": len(code_product_proposals),
                "latest_target_file": latest_code_product.get("target_file") if latest_code_product else None,
                "candidate_target_file": code_product_candidate_target or None,
                "candidate_target_line_count": code_product_candidate_line_count or None,
                "candidate_payload_must_be_generated_from_required_working_set": bool(
                    code_product_candidate_target
                    and not (_goal_exact_text_block(goal, "old_text") and _goal_exact_text_block(goal, "new_text"))
                    and code_product_blocks_final
                ),
                "action_plan_candidate_available": bool(action_plan_candidate),
                "latest_edit_kind": latest_code_product.get("edit_kind") if latest_code_product else None,
                "latest_payload_complete": bool(latest_code_product and not latest_code_product_violations),
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
                "disallowed_next_decision_signatures": disallowed_invalid_decision_signatures,
            },
            "validation_rejections_tail": _compact_validation_rejections_tail(validation_rejections, limit=5),
            "project_powershell_access": {
                "tool": "terminal_run_command_wait",
                "cwd": str(LAB_REPO),
                "privilege_boundary": "current 3572 Python process user; not UAC elevation",
                "dangerous_commands_require_user_consent": True,
                "use_for": "rg/select-string, dir/tree, git status/diff, python -m compileall, targeted diagnostics under the project folder",
            },
            "finalization_contract": {
                "final_allowed": final_allowed,
                "reason": final_reason,
                "planner_may_choose_final": final_allowed,
                "controller_must_not_auto_final": True,
                "final_is_not_required": True,
                "verified_content_read_count": len(verified_read_rows),
                "verified_content_reads": verified_read_rows[:160],
                "missing_full_content_reads": missing_full_content_reads[:160],
                "code_product_required": code_product_required,
                "code_product_required_tool": "repo_propose_code_edit" if code_product_required else None,
                "code_product_latest_violations": latest_code_product_violations if code_product_required else [],
                "minimum_evidence_for_this_goal_kind": (
                    "For code diff/refactoring proposals: read the target with repo_read, then call repo_propose_code_edit with a complete unified_diff, structured_operations, or explicit no_op rationale."
                    if code_product_required else
                    "For explicit file inspection: direct repo_read of the requested file."
                    if target_kind == "file" else
                    f"For explicit directory inspection: list/tree the requested directory and read up to "
                    f"{SCOPED_CONCRETE_READ_TARGET} verified concrete readable files discovered under it; "
                    "if fewer are discovered, read all discovered candidates."
                    if target_kind == "directory" else
                    "For generic repository structure/content analysis: root surface, at least 3 markdown/config reads, "
                    "one evidence-derived meaningful non-infra/code area, and enough verified content reads for the "
                    f"current goal. For analysis/action-plan goals the {REPO_CONCRETE_READ_TARGET}-read target is orientative; "
                    f"{repo_final_required_read_count} verified reads can satisfy finalization when concrete evidence is present."
                ),
            },
            "agentic_codex_quality": {
                "enabled": True,
                "repo_goal": repo_goal,
                "deep_repo_goal": repo_goal,
                "target_kind": target_kind,
                "target_file": target_file or None,
                "target_scope": target_scope or None,
                "root_surface_done": root_surface_done,
                "doc_read_count": len(doc_reads),
                "doc_reads": doc_reads[:80],
                "code_read_count": len(code_reads),
                "code_reads": code_reads[:80],
                "meaningful_non_root_list_count": len(meaningful_lists),
                "meaningful_non_root_lists": meaningful_lists[:20],
                "meaningful_content_read_count": len(meaningful_content_reads),
                "meaningful_content_reads": meaningful_content_reads[:40],
                "verified_content_read_count": len(verified_read_rows),
                "verified_content_reads": verified_read_rows[:80],
                "missing_full_content_reads": missing_full_content_reads[:80],
                "ranked_core_candidate_dirs": core_candidates,
                "core_discovery_candidates": core_discovery_candidates[:12],
                "top_core_seen": bool(core_candidates),
                "quality_gate": (
                    "direct file read"
                    if target_kind == "file" else
                    f"in-scope list/tree + {scope_required_read_count} in-scope verified concrete readable reads"
                    if target_kind == "directory" else
                    f"root_surface + >=3 docs/config reads + one evidence-derived non-infra/code area "
                    f"+ {repo_final_required_read_count} verified concrete readable reads"
                ),
                "hardcoded_core_path": False,
            },
            "initial_orientation_surface": _initial_orientation_surface_from_history(history),
        }
        contract = _agentic_v2_enrich_evidence_contract(contract, goal, history)
        contract["operational_notes"] = _build_operational_notebook(goal, contract)
        if code_product_blocks_final:
            payload_rejection_count = _code_product_payload_rejection_count(
                validation_rejections,
                code_product_candidate_target,
            )
            successful_read_path_set = {
                _repo_rel_token(path)
                for path in [*read_ok, *verified_read_paths, *list(verified_read_path_set)]
                if _repo_rel_token(path)
            }
            code_contract = contract.get("code_product_contract") if isinstance(contract.get("code_product_contract"), dict) else {}
            code_contract["payload_rejection_count"] = payload_rejection_count
            code_contract["route_shift_after_payload_rejection"] = bool(payload_rejection_count and code_product_candidate_target)
            contract["code_product_contract"] = code_contract
            final_contract = contract.get("finalization_contract") if isinstance(contract.get("finalization_contract"), dict) else {}
            final_contract["final_allowed"] = False
            final_contract["planner_may_choose_final"] = False
            final_contract["reason"] = final_reason
            contract["finalization_contract"] = final_contract
            contract["planner_may_choose_final"] = False
            build_state_ready_action = _code_product_build_state_propose_action(
                code_product_build_state,
                latest_code_product_violations,
            )
            complete_existing_code_action = next(
                (
                    item for item in (contract.get("candidate_next_actions") or [])
                    if isinstance(item, dict)
                    and item.get("tool") == "repo_propose_code_edit"
                    and _code_product_action_has_complete_payload(item)
                ),
                {},
            )
            if not build_state_ready_action and complete_existing_code_action:
                build_state_ready_action = complete_existing_code_action
            build_state_status = str(code_product_build_state.get("status") or "")
            build_state_target = _repo_rel_token(code_product_build_state.get("target_file") or "")
            build_state_needs_read = bool(
                code_product_build_state
                and not build_state_ready_action
                and (
                    code_product_build_state.get("complete_payload_ready")
                    or code_product_build_state.get("has_more_after") is True
                    or code_product_build_state.get("payload_loaded") is not True
                )
            )
            build_state_progress_handled = False
            if build_state_ready_action:
                build_state_progress_handled = True
                ready_progress = (
                    "Internal code_product_build_state is ready_for_propose. "
                    "Call repo_propose_code_edit with the complete payload from candidate_next_actions."
                    if code_product_build_state else
                    "A complete repo_propose_code_edit candidate is available. "
                    "Call repo_propose_code_edit with that complete payload."
                )
                existing_candidates = [
                    item for item in (contract.get("candidate_next_actions") or [])
                    if not (
                        isinstance(item, dict)
                        and item.get("tool") == "repo_propose_code_edit"
                        and not _code_product_action_has_complete_payload(item)
                    )
                ]
                contract["candidate_next_actions"] = [build_state_ready_action] + existing_candidates[:15]
                contract["required_next_progress"] = ready_progress
            elif build_state_status == "blocked_incomplete":
                build_state_progress_handled = True
                code_contract = contract.get("code_product_contract") if isinstance(contract.get("code_product_contract"), dict) else {}
                code_contract["build_state_block_allows_typed_block"] = True
                code_contract["build_state_blocker"] = (
                    code_product_build_state.get("blocker")
                    or (code_product_build_state.get("state") or {}).get("blocker")
                )
                contract["code_product_contract"] = code_contract
                contract["candidate_next_actions"] = []
                contract["required_next_progress"] = (
                    "Internal code_product_build_state is blocked_incomplete. "
                    "Return action=block with final_answer starting with code_product_build_state_blocked_incomplete "
                    "and cite the blocker; do not loop on repo_read or incomplete repo_propose_code_edit."
                )
            elif build_state_needs_read:
                build_state_progress_handled = True
                read_state_action = _code_product_build_state_read_action(
                    code_product_build_state,
                    build_state_target or code_product_candidate_target,
                )
                existing_candidates = [
                    item for item in (contract.get("candidate_next_actions") or [])
                    if not (
                        isinstance(item, dict)
                        and item.get("tool") == "repo_propose_code_edit"
                        and not _code_product_action_has_complete_payload(item)
                    )
                ]
                contract["candidate_next_actions"] = [read_state_action] + existing_candidates[:15]
                contract["required_next_progress"] = (
                    "Read the internal code_product_build_state SQLite window before deciding whether "
                    "repo_propose_code_edit has a complete payload."
                )
            elif payload_rejection_count and code_product_candidate_target:
                build_state_progress_handled = True
                route_candidate = _code_product_source_window_candidate(
                    code_product_candidate_target,
                    line_count=code_product_candidate_line_count,
                    history=history,
                )
                existing_candidates = [
                    item for item in (contract.get("candidate_next_actions") or [])
                    if not (
                        isinstance(item, dict)
                        and item.get("tool") == "repo_propose_code_edit"
                        and not _code_product_action_has_complete_payload(item)
                    )
                    and not (
                        isinstance(item, dict)
                        and item.get("tool") == "planner_scratchpad_write"
                        and (item.get("arguments") or {}).get("kind") == CODE_PRODUCT_BUILD_STATE_KIND
                        and not str((item.get("arguments") or {}).get("text") or (item.get("arguments") or {}).get("content") or "").strip()
                    )
                ]
                if route_candidate:
                    contract["candidate_next_actions"] = [route_candidate] + existing_candidates[:15]
                    contract["required_next_progress"] = (
                        "Route shift required after invalid repo_propose_code_edit payload. Change decision now: "
                        "read a different concrete source window from the target via candidate_next_actions[0], then call "
                        "repo_propose_code_edit only with complete unified_diff or complete old_text/new_text. "
                        "Do not repeat the rejected incomplete repo_propose_code_edit and do not write an empty "
                        "code_product_build_state."
                    )
                else:
                    contract["candidate_next_actions"] = existing_candidates[:15]
                    contract["required_next_progress"] = (
                        "Route shift required after invalid repo_propose_code_edit payload, but no new source "
                        "window is available for this target. Change decision now: use verified_content_reads / "
                        "required_working_set to call repo_propose_code_edit with a complete unified_diff or "
                        "complete old_text/new_text, write code_product_build_state with real progress only, "
                        "or return a typed block if the diff cannot be built. Do not repeat repo_read."
                    )
            elif build_state_status == "collecting_source" and code_product_build_state.get("payload_loaded") is True:
                build_state_progress_handled = True
                existing_candidates = [
                    item for item in (contract.get("candidate_next_actions") or [])
                    if not (
                        isinstance(item, dict)
                        and item.get("tool") == "repo_propose_code_edit"
                        and not _code_product_action_has_complete_payload(item)
                    )
                    and not (
                        isinstance(item, dict)
                        and item.get("tool") == "repo_read"
                        and (build_state_target or code_product_candidate_target) in {
                            _repo_rel_token(path)
                            for path in _agentic_v2_decision_paths(
                                str(item.get("tool") or ""),
                                item.get("arguments") if isinstance(item.get("arguments"), dict) else {},
                            )
                        }
                    )
                ]
                progress_write_action = _code_product_build_state_write_action(
                    build_state_target or code_product_candidate_target,
                    history,
                )
                contract["candidate_next_actions"] = (
                    ([progress_write_action] if progress_write_action else []) + existing_candidates[:15]
                )
                contract["required_next_progress"] = (
                    "Internal code_product_build_state is collecting_source but not ready and has no remaining "
                    "state window to read. Advance with one real step only: call repo_propose_code_edit with a "
                    "complete unified_diff or complete old_text/new_text, write code_product_build_state with "
                    "new real progress, or return a typed block if the diff cannot be built. Empty "
                    "collecting_source writes are rejected."
                )
            elif code_product_candidate_target and code_product_candidate_target in successful_read_path_set:
                build_state_progress_handled = True
                write_state_action = _code_product_build_state_write_action(code_product_candidate_target, history)
                existing_candidates = [
                    item for item in (contract.get("candidate_next_actions") or [])
                    if not (
                        isinstance(item, dict)
                        and item.get("tool") == "repo_propose_code_edit"
                        and not _code_product_action_has_complete_payload(item)
                    )
                    and not (
                        isinstance(item, dict)
                        and item.get("tool") == "repo_read"
                        and code_product_candidate_target in {
                            _repo_rel_token(path)
                            for path in _agentic_v2_decision_paths(
                                str(item.get("tool") or ""),
                                item.get("arguments") if isinstance(item.get("arguments"), dict) else {},
                            )
                        }
                    )
                ]
                contract["candidate_next_actions"] = (
                    ([write_state_action] if write_state_action else []) + existing_candidates[:15]
                )
                contract["required_next_progress"] = (
                    "Target is already read and no ready code product exists. Persist an internal "
                    "code_product_build_state with real progress only; do not repeat repo_read "
                    "for that target and do not call repo_propose_code_edit until payload is complete. "
                    "Empty collecting_source writes are rejected."
                )
            if not build_state_progress_handled and payload_rejection_count and code_product_candidate_target:
                route_candidate = _code_product_source_window_candidate(
                    code_product_candidate_target,
                    line_count=code_product_candidate_line_count,
                    history=history,
                )
                route_target_has_truncated_read = any(
                    _repo_rel_token(row.get("path") or "") == code_product_candidate_target
                    and row.get("truncated") is True
                    for row in verified_read_rows
                    if isinstance(row, dict)
                )
                existing_candidates = [
                    item for item in (contract.get("candidate_next_actions") or [])
                    if not (
                        isinstance(item, dict)
                        and item.get("tool") == "repo_propose_code_edit"
                        and not _code_product_action_has_complete_payload(item)
                    )
                    and not (
                        isinstance(item, dict)
                        and item.get("tool") == "repo_read"
                        and code_product_candidate_target in {
                            _repo_rel_token(path)
                            for path in _agentic_v2_decision_paths(
                                str(item.get("tool") or ""),
                                item.get("arguments") if isinstance(item.get("arguments"), dict) else {},
                            )
                        }
                    )
                ]
                if code_product_candidate_target in successful_read_path_set and not route_target_has_truncated_read:
                    code_contract["route_shift_target_already_read"] = True
                    code_contract["route_shift_blocker"] = (
                        "code_product_route_shift_target_already_read_but_no_valid_candidate"
                    )
                    code_contract["forbidden_repeated_repo_read_target"] = code_product_candidate_target
                    contract["code_product_contract"] = code_contract
                    contract["candidate_next_actions"] = existing_candidates[:15]
                    contract["forbidden_next_actions"] = [
                        {
                            "action": "tool",
                            "tool": "repo_read",
                            "arguments": route_candidate.get("arguments"),
                            "reason": (
                                "The code-product route-shift target is already in "
                                "successful_repo_read_paths; repeating this read loops."
                            ),
                        }
                    ]
                    contract["required_next_progress"] = (
                        "Route shift required after invalid repo_propose_code_edit payload, but "
                        f"{code_product_candidate_target} is already read. Do not call repo_read for "
                        "that target again. Use required_working_set.repo_reads / verified_content_reads "
                        "for that target and call repo_propose_code_edit only with a complete inline "
                        "unified_diff or complete structured_operations. If a complete code product "
                        "cannot be produced from the available source evidence, return action=block with "
                        "final_answer starting with "
                        "code_product_route_shift_target_already_read_but_no_valid_candidate."
                    )
                elif route_candidate:
                    contract["candidate_next_actions"] = [route_candidate] + existing_candidates[:15]
                    contract["required_next_progress"] = (
                        "Route shift required after invalid repo_propose_code_edit payload. "
                        f"Do not repeat the same repo_propose_code_edit arguments for {code_product_candidate_target}. "
                        "Next action must inspect a concrete source window of that target with repo_read, then produce "
                        "repo_propose_code_edit only when the unified_diff or structured_operations payload is complete inline."
                    )
                else:
                    contract["candidate_next_actions"] = existing_candidates[:15]
                    contract["required_next_progress"] = (
                        "Route shift required after invalid repo_propose_code_edit payload, but no unread source "
                        "window remains for the target. Do not call repo_read for that target again. Use the "
                        "existing source evidence to produce a complete inline repo_propose_code_edit payload, "
                        "write code_product_build_state with real progress, or return a typed block."
                    )
            elif not build_state_progress_handled and code_product_candidate_target:
                contract["required_next_progress"] = (
                    "Use required_working_set.repo_reads for the previously read target "
                    f"{code_product_candidate_target}; then call repo_propose_code_edit only with a complete "
                    "unified_diff or complete structured_operations inline. "
                    "Do not final with prose-only output."
                )
            elif not build_state_progress_handled:
                contract["required_next_progress"] = (
                    "read the target with repo_read, then call repo_propose_code_edit with a complete inline code product. "
                    "Do not final with prose-only output."
                )
        elif final_allowed:
            contract["required_next_progress"] = (
                "Quality gate is satisfied. Planner must produce action=final using operational_notes.read_notes, "
                "workflow/problems/core evidence, cited concrete paths, and explicit limits. Do not call repo_tree/list/read again "
                "unless a brand-new evidence gap is named."
            )
        elif candidates:
            contract["required_next_progress"] = (
                "candidate_next_actions contains admissible examples, not a controller script. "
                "Planner must choose the next evidence-bound tool or final; do not repeat rejected decisions. "
                "Controller validates only; no hidden fallback final."
            )
        else:
            contract["required_next_progress"] = (
                "Use prior evidence. If enough, final with concrete cited paths; otherwise choose a new evidence-bound tool."
            )
        proofed_candidates: list[dict[str, Any]] = []
        for action in contract.get("candidate_next_actions") or []:
            if not isinstance(action, dict):
                continue
            args = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
            action_paths = [
                _repo_rel_token(path)
                for path in _agentic_v2_decision_paths(str(action.get("tool") or ""), args)
                if _repo_rel_token(path)
            ]
            path_exists = None
            path_readable = None
            under_scope = None
            validator_admissible = None
            if action_paths:
                path_exists = all(_path_exists_repo_relative(path) for path in action_paths)
                path_readable = all(_repo_readable_evidence_file(path) for path in action_paths)
                under_scope = (
                    all(_path_under_scope(path, target_scope) for path in action_paths)
                    if target_scope
                    else True
                )
                validator_admissible = (
                    all(path in validator_admissible_read_paths for path in action_paths)
                    if action.get("tool") == "repo_read"
                    else None
                )
            proofed_candidates.append(
                attach_action_proof(
                    action,
                    source="evidence_contract_candidate_next_actions",
                    path_exists=path_exists,
                    path_readable=path_readable,
                    under_scope=under_scope,
                    validator_admissible=validator_admissible,
                )
            )
        candidate_gate = gate_candidate_actions(proofed_candidates)
        contract["candidate_next_actions"] = candidate_gate["candidate_next_actions"]
        contract["rejected_candidate_actions"] = candidate_gate["rejected_candidate_actions"]
        contract["evidence_coverage"] = score_evidence_coverage(contract)
        progress_text = str(contract.get("required_next_progress") or "").strip()
        if progress_text:
            contract["required_next_progress_model"] = required_next_progress_from_text(
                progress_text,
                metadata={
                    "final_allowed": bool(contract.get("planner_may_choose_final")),
                    "candidate_next_actions_count": len(contract.get("candidate_next_actions") or []),
                    "forbidden_next_actions_count": len(contract.get("forbidden_next_actions") or []),
                    "goal_requests_code_product": bool(contract.get("goal_requests_code_product")),
                },
            ).to_contract()
        contract = _apply_turn_surface_policy(contract)
        return contract


def planner_evidence_contract(
    goal: str,
    history: list[dict[str, Any]],
    intrinsic_context: dict[str, Any] | None = None,
    *,
    deps: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Compatibility entrypoint for ``EvidenceBuilder``."""
    return EvidenceBuilder(_deps=deps, _config=config).build(
        goal,
        history,
        intrinsic_context,
    )
