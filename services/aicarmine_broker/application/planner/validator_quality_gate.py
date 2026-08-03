"""Quality gate stage extracted from validator.py.

Handles final quality gate evaluation, rewrite latch state transitions,
required-next tool call generation, and candidate-next-actions population.
"""

from __future__ import annotations

from typing import Any, Mapping

from aicarmine_broker.application.planner.path_utils import coalesce_repo_read_paths
from aicarmine_broker.application.planner.required_call_validator import (
    coerce_final_rewrite_latch,
    coalesce_required_next_tool_tool,
    required_next_route_has_deterministic_proof,
)
from aicarmine_broker.application.planner.validator_pipeline import PipelineState
from aicarmine_broker.application.tool_surface.required_tool_call import (
    append_stale_required_call_marker,
    required_next_tool_call_satisfaction,
)


class StageQualityGate:
    """Evaluate final quality gates and manage rewrite lane state."""

    def _coalesce_required_next_missing_paths(self, values: Any) -> list[str]:
        out: list[str] = []
        if not isinstance(values, (list, tuple, set)):
            return out
        for value in values:
            token = str(value).strip()
            if token and token not in out:
                out.append(token)
        return out[:12]

    def _required_gap_paths_from_quality(
        self,
        quality: Mapping[str, Any],
        contract: dict[str, Any],
        existing_missing: list[str],
        successful_read_paths: set[str],
        stale_paths: set[str],
    ) -> list[str]:
        raw_missing = (
            quality.get("required_next_missing_evidences")
            if isinstance(quality.get("required_next_missing_evidences"), list)
            else existing_missing
        )
        if not isinstance(raw_missing, list):
            return []
        required_next_missing_evidences = [
            str(item).strip() for item in raw_missing if str(item).strip()
        ]
        return [
            path
            for path in required_next_missing_evidences
            if path not in successful_read_paths
            and path not in stale_paths
            and path not in existing_missing
        ]

    def run(self, state: PipelineState) -> PipelineState:
        """Run quality gate stage. Returns state with updated contract/result."""
        deps = state.deps
        contract = state.contract
        history = state.history
        violations = state.violations
        action = state.action

        # Quality gate only applies to final/done/complete actions
        if action not in {"final", "done", "complete", "completed"}:
            return state

        # Extract deps
        _agentic_v2_successful_read_paths = deps["agentic_v2_successful_read_paths"]
        _successful_window_signatures = deps["successful_window_signatures"]
        _repo_read_window_signature = deps["repo_read_window_signature"]
        _planner_scratchpad_window_signature = deps["planner_scratchpad_window_signature"]
        _decision_paths = deps["decision_paths"]
        _apply_duplicate_window_replan_contract = deps["apply_duplicate_window_replan_contract"]
        _apply_duplicate_repo_read_path_recovery_contract = deps["apply_duplicate_repo_read_path_recovery_contract"]
        _repo_analysis_final_answer_quality = deps["repo_analysis_final_answer_quality"]
        _repo_analysis_final_answer_model_quality = deps.get("repo_analysis_final_answer_model_quality")
        _final_answer_is_action_plan_without_code_product = deps["final_answer_is_action_plan_without_code_product"]
        _final_composition_tool_names_from_candidates = deps["final_composition_tool_names_from_candidates"]
        _code_product_payload_violations = deps["code_product_payload_violations"]
        _successful_code_edit_proposals = deps["successful_code_edit_proposals"]
        append_stale_required_call_marker = deps["append_stale_required_call_marker"]

        # Step 1: Track reject count
        step_index = len(history)
        if int(contract.get("planner_final_quality_last_rewrite_decision") or -1) != step_index:
            reject_count = int(contract.get("planner_final_quality_reject_count") or 0) + 1
            contract["planner_final_quality_reject_count"] = reject_count
            contract["planner_final_quality_last_rewrite_decision"] = step_index
        else:
            reject_count = int(contract.get("planner_final_quality_reject_count") or 0)
        contract["planner_cuda_rewrite_required"] = True

        # Step 2: Process required_next_progress
        quality = {}  # Full quality gate result will be built incrementally
        required_next_progress = str(quality.get("required_next_progress") or "").strip()
        if required_next_progress:
            contract["required_next_progress"] = required_next_progress

        # Step 3: Process required_next_output_sections
        required_next_output_sections = quality.get("required_next_output_sections") if isinstance(quality.get("required_next_output_sections"), list) else []
        if required_next_output_sections:
            contract["required_next_output_sections"] = [
                str(item).strip() for item in required_next_output_sections if str(item).strip()
            ]

        # Step 4: Compute required gap paths
        raw_existing_required_missing = contract.get("required_next_missing_evidences")
        existing_required_missing = [
            path for path in self._coalesce_required_next_missing_paths(
                raw_existing_required_missing if isinstance(raw_existing_required_missing, (list, tuple, set)) else []
            )
            if path
        ]
        successful = set()
        for path in contract.get("successful_repo_read_paths") if isinstance(contract.get("successful_repo_read_paths"), list) else []:
            token = str(path).strip()
            if token:
                successful.add(token)
        stale = set()
        for row in contract.get("stale_required_next_tool_calls") if isinstance(contract.get("stale_required_next_tool_calls"), list) else []:
            if not isinstance(row, dict):
                continue
            if str(row.get("tool") or "") != "repo_read":
                continue
            args = row.get("arguments") if isinstance(row.get("arguments"), dict) else {}
            for path in args.get("paths", []) if isinstance(args.get("paths"), list) else [args.get("path")]:
                token = str(path).strip()
                if token:
                    stale.add(token)
        required_next_missing_evidences = self._required_gap_paths_from_quality(
            quality, contract, existing_required_missing, successful, stale
        )
        raw_required_next_missing_evidences = required_next_missing_evidences if required_next_missing_evidences else existing_required_missing

        # Step 5: Verify required missing paths
        verified_required_missing, invalid_required_missing = [], []
        for path in raw_required_next_missing_evidences:
            if path in {"coverage required", "read or search pending", "missing core candidate paths", "missing unverified file mentions"} or path.startswith("need_") or any(ch.isspace() for ch in path):
                if path not in invalid_required_missing:
                    invalid_required_missing.append(path)
                continue
            if path in successful or path in stale:
                if path not in invalid_required_missing:
                    invalid_required_missing.append(path)
                continue
            if path not in invalid_required_missing:
                invalid_required_missing.append(path)
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

        # Step 6: Build required_next_tool_call
        required_next_tool_call = quality.get("required_next_tool_call") if isinstance(quality.get("required_next_tool_call"), dict) else {}
        raw_contract_missing = contract.get("required_next_missing_evidences")
        contract_missing = raw_contract_missing if isinstance(raw_contract_missing, (list, tuple, set)) else []
        if not required_next_tool_call and contract_missing:
            required_next_tool_call = {
                "tool": "repo_read",
                "arguments": {"paths": self._coalesce_required_next_missing_paths(contract_missing)[:12]},
                "reason": "Rewrite final from verified evidence requires at least one remaining evidence gap. Read one of the requested missing paths before final.",
                "allow_only_if_missing_evidence": True,
                "source": "repo_analysis_final_model_quality",
            }

        # Step 7: Validate required_next_tool_call
        if required_next_tool_call.get("tool") == "repo_read":
            args = required_next_tool_call.get("arguments") if isinstance(required_next_tool_call.get("arguments"), dict) else {}
            raw_paths = []
            if args.get("path"):
                raw_paths.append(args.get("path"))
            raw_paths.extend(args.get("paths") if isinstance(args.get("paths"), list) else [])
            parsed_paths = coalesce_repo_read_paths(raw_paths)
            allowlist = set()
            for key in ("validator_admissible_repo_read_paths", "read_admissible_paths", "successful_repo_read_paths"):
                values = contract.get(key)
                if isinstance(values, (list, dict)):
                    for item in (values.values() if isinstance(values, dict) else values):
                        if isinstance(item, dict):
                            token = str(item.get("path") or item.get("repo_path") or "")
                            if token:
                                allowlist.add(token)
                        else:
                            allowlist.add(str(item))
            valid_paths = [p for p in parsed_paths if p in allowlist or not allowlist]
            if valid_paths:
                if len(valid_paths) == 1:
                    args["path"] = valid_paths[0]
                else:
                    args["paths"] = valid_paths[:12]
                required_next_tool_call["arguments"] = args
            else:
                required_next_tool_call = {}

        # Step 8: Coalesce and validate deterministic proof
        if required_next_tool_call:
            required_next_tool_call = coalesce_required_next_tool_tool(required_next_tool_call)
            if not required_next_route_has_deterministic_proof(required_next_tool_call, contract):
                required_next_tool_call = {}

        # Step 9: Build candidate_next_actions or set final_rewrite_latch
        final_rewrite_latch = "terminal_block_required" if reject_count >= 2 else "rewrite_required"
        if required_next_tool_call:
            final_rewrite_latch = "rewrite_required"
            required_next_tool_call["source"] = "repo_analysis_final_model_quality"
            required_next_tool_call["allow_only_if_missing_evidence"] = True
            satisfaction = required_next_tool_call_satisfaction(
                required_next_tool_call, history,
                successful_repo_read_paths=_agentic_v2_successful_read_paths,
                successful_window_signatures=_successful_window_signatures,
                repo_read_window_signature=_repo_read_window_signature,
                planner_scratchpad_window_signature=_planner_scratchpad_window_signature,
                decision_paths=_decision_paths,
            )
            if satisfaction.get("satisfied") is True:
                append_stale_required_call_marker(contract, satisfaction)
                required_next_tool_call = {}
            else:
                required_next_tool_call["validated"] = True
                required_next_tool_call["validation_source"] = "deterministic_validator"
                contract["required_next_tool_call"] = required_next_tool_call
                contract["required_next_tool_call_validated"] = True
                contract["required_next_tool_call_validation_source"] = "deterministic_validator"
                action_id = f"repo_analysis_final_quality:{required_next_tool_call.get('tool', '')}"
                action = {
                    "action_id": action_id,
                    "tool": required_next_tool_call.get("tool"),
                    "arguments": required_next_tool_call.get("arguments"),
                    "reason": required_next_tool_call.get("reason"),
                    "source": "repo_analysis_final_model_quality",
                    "independent_read_only": True,
                }
                existing = contract.get("candidate_next_actions") if isinstance(contract.get("candidate_next_actions"), list) else []
                contract["candidate_next_actions"] = [action] + [item for item in existing if isinstance(item, dict) and item != action][:12]
        else:
            contract.pop("required_next_tool_call", None)
            contract.pop("required_next_tool_call_validated", None)
            contract.pop("required_next_tool_call_validation_source", None)
            fallback_progress = "Final-quality rejected with no concrete evidence gap and no runnable required_next_tool_call. Rewrite the final answer from verified evidence only; do not call non-evidence tools."
            if not contract.get("required_next_progress"):
                contract["required_next_progress"] = fallback_progress

        # Step 10: Set final_rewrite_latch and finalization_contract
        contract["final_rewrite_latch"] = final_rewrite_latch
        contract["planner_may_choose_block"] = final_rewrite_latch == "terminal_block_required"
        contract["planner_may_choose_final"] = False
        final_contract = contract.get("finalization_contract") if isinstance(contract.get("finalization_contract"), dict) else {}
        final_contract["final_allowed"] = False
        final_contract["planner_may_choose_final"] = False
        if final_rewrite_latch == "terminal_block_required":
            final_contract["planner_may_choose_block"] = True
            final_contract["planner_forced_terminal_block"] = True
            final_contract["planner_forced_terminal_block_reason"] = "repo_analysis_final_quality_no_runnable_gap_terminal_block"
            final_contract["reason"] = "repo_analysis_final_quality_no_runnable_gap_terminal_block"
        else:
            final_contract["planner_may_choose_block"] = False
            final_contract["reason"] = "repo_analysis_final_model_quality_rejected_no_runnable_gap"
        contract["finalization_contract"] = final_contract

        return state