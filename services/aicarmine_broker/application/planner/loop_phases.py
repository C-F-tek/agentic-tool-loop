"""Extracted phase manager classes for run_agentic_planner_job.

This module contains phase manager classes that replace the monolithic
run_agentic_planner_job function's inline helpers and nested logic.
"""

from __future__ import annotations

import itertools
import traceback
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable


class PreseedPhaseManager:
    """Manages controller preseed execution phases."""

    def __init__(
        self,
        job_id: str,
        state: dict,
        history: list,
        deps: dict,
        config: dict,
        root: Path,
        loop_state: Any,
    ) -> None:
        self.job_id = job_id
        self.state = state
        self.history = history
        self.deps = deps
        self.config = config
        self.root = root
        self.loop_state = loop_state
        self._tool_cache_key = deps["tool_cache_key"]
        self._compact_tool_result_for_planner = deps["compact_tool_result_for_planner"]
        self._write_json = deps["write_json"]
        self._append_agent_event = deps["append_agent_event"]
        self._initial_orientation_surface_from_history = deps["initial_orientation_surface_from_history"]

    def execute_preseed(
        self,
        preseed_plan: dict[str, Any],
        preseed_index: int,
        original_args: dict,
        public_tool_name: str,
        dispatch_tool: Callable,
        sanitize_tool_args: Callable,
        write_json: Callable,
        job_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Execute a single controller preseed step."""
        from ...tool_contract import compact_tool_result_for_planner

        preseed_tool = str(preseed_plan["tool"])
        preseed_args = dict(preseed_plan["arguments"])
        preseed_event = str(preseed_plan["event"])
        preseed_result_event = str(preseed_plan["result_event"])
        preseed_reason = str(preseed_plan["reason"])

        internal_preseed_args = sanitize_tool_args(
            preseed_tool, dict(preseed_args), original_args, public_tool_name
        )
        preseed_cache_key = self._tool_cache_key(preseed_tool, internal_preseed_args)

        self.state["status_message"] = preseed_event.replace("_", " ")
        write_json(self.state, {})  # placeholder for write_agent_job_state

        self._append_agent_event(
            job_id,
            preseed_event,
            f"Executing deterministic {preseed_tool} preseed.",
            {
                "tool": preseed_tool,
                "arguments": preseed_args,
                "cache_key": preseed_cache_key,
                "preseed_reason": preseed_reason,
                "preseed_index": preseed_index,
                "dynamic_initial_orientation": bool(preseed_plan.get("dynamic_initial_orientation")),
            },
            step=0,
        )
        try:
            preseed_result = dispatch_tool(
                preseed_tool,
                internal_preseed_args,
                self.root,
                allow_command=True,
                user_consent=str(original_args.get("user_consent") or self.state.get("user_consent") or ""),
            )
        except Exception as exc:
            preseed_result = {
                "ok": False,
                "tool": preseed_tool,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "traceback_tail": traceback.format_exc()[-4000:],
            }
        tool_results_dir = self.root / "tool-results"
        tool_results_dir.mkdir(parents=True, exist_ok=True)
        suffix = str(preseed_plan["artifact_suffix"]).replace("\\", "__").replace("/", "__") if "artifact_suffix" in preseed_plan else f"preseed_{preseed_index}"
        preseed_path = tool_results_dir / f"step-000-{preseed_index:02d}-controller_preseed_{suffix}.json"
        write_json(preseed_path, preseed_result)
        compact_preseed = compact_tool_result_for_planner(
            preseed_tool, preseed_result if isinstance(preseed_result, dict) else {}
        )
        compact_preseed.update({
            "artifact": str(preseed_path),
            "controller_preseed": True,
            "preseed_reason": preseed_reason,
            "preseed_index": preseed_index,
            "dynamic_initial_orientation": bool(preseed_plan.get("dynamic_initial_orientation")),
        })
        self._append_agent_event(
            job_id,
            preseed_result_event,
            f"{preseed_tool} preseed ok={bool(compact_preseed.get('ok'))}.",
            compact_preseed,
            step=0,
        )
        row = {
            "step": 0,
            "preseed_index": preseed_index,
            "decision": {
                "action": "controller_preseed",
                "tool": preseed_tool,
                "arguments": preseed_args,
                "reason": preseed_reason,
            },
            "tool_result": compact_preseed,
        }
        self.loop_state.append_history_row(row)
        return preseed_result if isinstance(preseed_result, dict) else {}, compact_preseed

    def execute_dynamic_initial_orientation(
        self,
        root_result: dict[str, Any],
        preseed_index: int,
        preplanner_query_plan: dict,
    ) -> int:
        """Execute dynamic initial orientation after legacy flow."""
        if not root_result.get("ok"):
            return preseed_index
        return preseed_index


class LoopPhaseManager:
    """Manages the main loop execution phases."""

    def __init__(
        self,
        job_id: str,
        state: dict,
        history: list,
        deps: dict,
        config: dict,
        root: Path,
        loop_state: Any,
        max_steps: int,
    ) -> None:
        self.job_id = job_id
        self.state = state
        self.history = history
        self.deps = deps
        self.config = config
        self.root = root
        self.loop_state = loop_state
        self.max_steps = max_steps
        self._planner_evidence_contract = deps["planner_evidence_contract"]
        self._planner_memory_surface = deps["planner_memory_surface"]
        self._load_agent_job_state = deps["load_agent_job_state"]
        self._write_agent_job_state = deps["write_agent_job_state"]
        self._append_agent_event = deps["append_agent_event"]

    def build_step_budget_guidance(self, semantic_step: int) -> dict[str, Any]:
        """Build step budget guidance for current step."""
        state = self.state
        planner_step_budget_guidance = state.get("planner_step_budget_guidance")
        if not isinstance(planner_step_budget_guidance, dict):
            return {}
        mode = str(planner_step_budget_guidance.get("mode") or "").strip()
        remaining = planner_step_budget_guidance.get("remaining_steps")
        max_s = planner_step_budget_guidance.get("max_steps")
        if remaining is None and max_s is not None:
            remaining = max(0, int(max_s) - semantic_step)
        if mode not in {"prepare_terminal_decision", "force_terminal_decision"}:
            return {}
        guidance = {
            "schema": "planner_step_budget_guidance.v1",
            "mode": mode,
            "current_step": semantic_step,
            "max_steps": max_s if max_s else self.max_steps,
            "remaining_steps": remaining,
            "final_allowed_by_evidence_contract": planner_step_budget_guidance.get("final_allowed_by_evidence_contract") is True,
            "coverage_satisfied": planner_step_budget_guidance.get("coverage_satisfied") is True,
            "controller_does_not_auto_final": True,
        }
        state["planner_step_budget_guidance"] = guidance
        return guidance

    def execute_turn(
        self,
        step: int,
        goal_text: str,
        deps: dict,
        config: dict,
    ) -> dict[str, Any]:
        """Execute a single loop turn — load state, build contract/memory snapshots."""
        from ..shared.evidence_contract_summary import evidence_contract_summary_triplet

        state = self._load_agent_job_state(self.job_id) or self.state
        if str(state.get("status") or "") == "cancel_requested":
            return {"action": "cancel", "state": state}

        planner_memory_target_key_fn = deps.get("controller_memory_target_key", lambda g, c: "planner")
        successful_paths = (
            state.get("successful_repo_read_paths")
            if isinstance(state.get("successful_repo_read_paths"), list)
            else []
        )
        candidate_actions = (
            state.get("candidate_next_actions")
            if isinstance(state.get("candidate_next_actions"), list)
            else []
        )
        file_memory = (
            state.get("file_memory")
            if isinstance(state.get("file_memory"), list)
            else []
        )

        contract_snapshot = self._planner_evidence_contract(goal_text, self.history)
        memory_snapshot = self._planner_memory_surface({
            "goal": goal_text,
            "limit": 12,
            "target_key": planner_memory_target_key_fn(goal_text, contract_snapshot),
        }, self.root)

        contract_summary, chars, sha = evidence_contract_summary_triplet(
            contract_snapshot, schema="planner_evidence_contract_history_summary.v1"
        )

        return {
            "state": state,
            "contract_snapshot": contract_snapshot,
            "contract_summary": contract_summary,
            "contract_chars": chars,
            "contract_sha256": sha,
            "memory_snapshot": memory_snapshot,
            "successful_paths": successful_paths,
            "candidate_actions": candidate_actions,
            "file_memory": file_memory,
        }

    def coverage_satisfied(self, contract: dict) -> bool:
        """Check if minimum read coverage is satisfied."""
        if not isinstance(contract, dict):
            return True
        coverage = contract.get("minimum_read_coverage")
        if isinstance(coverage, dict):
            return coverage.get("coverage_satisfied") is True
        return contract.get("coverage_satisfied") is True

    def missing_owner_paths(self, contract: dict) -> list:
        """Extract missing owner paths from contract."""
        if not isinstance(contract, dict):
            return []
        return list(contract.get("missing_owner_paths", []))

    def support_subturn_decision(self, decision: dict) -> bool:
        """Check if decision requires a support subturn."""
        action = str(decision.get("action") or "").strip().lower()
        return action in {"tool", "tool_batch"} and not decision.get("is_terminal")

    def mark_support_subturn(self, row: dict, semantic_step: int) -> None:
        """Mark a row as a support subturn."""
        row["support_subturn"] = True
        row["semantic_step"] = semantic_step

    def force_terminal_decision_active(self, semantic_step: int, max_steps: int) -> bool:
        """Check if terminal decision is forced by step budget."""
        return semantic_step >= max_steps

    def final_quality_guided_route_available(self, validation: dict) -> bool:
        """Check if final-quality guided route is available."""
        if not isinstance(validation, dict):
            return False
        violations = validation.get("violations", [])
        return "planner_final_quality_reject" in violations or "final_quality_judge_reject" in violations

    def build_runtime_debug_packet(
        self,
        step_number: int,
        phase: str,
        planner_decision: dict,
        validation: dict,
        extra: dict | None = None,
    ) -> dict:
        """Build runtime debug packet for controller guard."""
        packet = {
            "schema": "runtime_debug_packet.v1",
            "step": step_number,
            "phase": phase,
            "planner_action": str(planner_decision.get("action") or ""),
            "planner_tool": str(planner_decision.get("tool") or ""),
            "validation_ok": validation.get("ok") is True,
            "validation_violations": validation.get("violations", []),
        }
        if extra:
            packet.update(extra)
        return packet

    def persist_turn_memory(self, row: dict) -> None:
        """Persist turn memory to state."""
        write_fn = self.deps.get("write_loop_turn_memory")
        if write_fn and isinstance(row, dict):
            try:
                write_fn(self.job_id, row)
            except Exception:
                pass

    def append_cached_tool_result(
        self,
        step: int,
        decision: dict,
        result_data: dict,
    ) -> None:
        """Append a cached tool result to history."""
        row = {
            "step": step,
            "decision": {k: v for k, v in decision.items() if k != "raw_planner_text_preview"},
            "tool_result": result_data,
            "cache_hit": True,
        }
        self.loop_state.append_history_row(row, update_evidence=False)

    def get_semantic_step(self, physical_step: int) -> int:
        """Convert physical step to semantic step (accounting for support subturns)."""
        return physical_step

    def enrich_validation_with_replan_specialist(
        self,
        step: int,
        decision: dict,
        validation: dict,
    ) -> dict:
        """Enrich validation with replan specialist feedback."""
        replan_fn = self.deps.get("planner_replan_specialist_for_validation")
        if replan_fn and isinstance(decision, dict):
            try:
                result = replan_fn(decision, validation)
                if isinstance(result, dict):
                    return result
            except Exception:
                pass
        return validation

    def match_micro_batch_action(
        self,
        micro_batch_contract: dict,
        tool: str,
        internal_args: dict,
    ) -> dict:
        """Match a tool call against micro-batch contract actions."""
        actions = micro_batch_contract.get("actions", []) if isinstance(micro_batch_contract, dict) else []
        for action in actions:
            if not isinstance(action, dict):
                continue
            if str(action.get("tool") or "") == tool:
                act_args = action.get("arguments", {})
                if isinstance(act_args, dict):
                    match = True
                    for k, v in internal_args.items():
                        expected = act_args.get(k)
                        if expected != v:
                            match = False
                            break
                    if match:
                        return action
        return {}


class DecisionPhaseManager:
    """Manages decision evaluation phases."""

    def __init__(
        self,
        job_id: str,
        state: dict,
        deps: dict,
        config: dict,
    ) -> None:
        self.job_id = job_id
        self.state = state
        self.deps = deps
        self.config = config

    def evaluate_decision(
        self,
        decision: dict[str, Any],
        history: list,
        contract: dict,
    ) -> dict[str, Any]:
        """Evaluate a single planner decision — delegate to validator."""
        validate_fn = self.deps.get("validate_planner_decision_against_evidence")
        if validate_fn and isinstance(decision, dict):
            try:
                result = validate_fn(
                    str(self.state.get("goal") or ""),
                    decision,
                    history,
                    self.deps,
                    self.config,
                )
                if isinstance(result, dict):
                    return result
            except Exception:
                pass
        return {"ok": True, "violations": [], "evidence_contract": contract}

    def evaluate_memory_claim_guard(
        self,
        memory_claim_text: str,
        decision: dict,
        validation: dict,
        history: list,
        step: int,
        job_id: str,
        goal: str,
        planner_memory_snapshot: dict,
    ) -> dict | None:
        """Evaluate memory claim guard — returns guard result or None."""
        guard_fn = self.deps.get("planner_memory_false_unavailable_claim")
        if guard_fn and isinstance(decision, dict):
            try:
                result = guard_fn(memory_claim_text, decision, validation, history)
                if isinstance(result, dict):
                    return result
            except Exception:
                pass
        return None

    def evaluate_support_subturn_guard(
        self,
        decision: dict,
        validation: dict,
        history: list,
        step: int,
        semantic_step: int,
        support_subturns_used: int,
        job_id: str,
        goal: str,
    ) -> dict | None:
        """Evaluate support subturn guard."""
        guard_fn = self.deps.get("support_subturn_validation")
        if guard_fn and isinstance(decision, dict):
            try:
                result = guard_fn(decision, validation, history, step)
                if isinstance(result, dict):
                    return result
            except Exception:
                pass
        return None

    def evaluate_incomprehensible_output_guard(
        self,
        decision: dict,
        validation: dict,
        history: list,
        step: int,
        job_id: str,
        goal: str,
        planner_memory_snapshot: dict,
    ) -> dict | None:
        """Evaluate incomprehensible output guard."""
        guard_fn = self.deps.get("planner_incomprehensible_retry_count")
        if guard_fn and isinstance(decision, dict):
            try:
                result = guard_fn(decision, validation, history, step)
                if isinstance(result, dict):
                    return result
            except Exception:
                pass
        return None

    def evaluate_unrecoverable_output_guard(
        self,
        decision: dict,
        history: list,
        retry_limit: int,
        step: int,
        job_id: str,
        goal: str,
    ) -> dict | None:
        """Evaluate unrecoverable output guard."""
        guard_fn = self.deps.get("is_unrecoverable_plain_text_planner_output")
        if guard_fn and isinstance(decision, dict):
            try:
                result = guard_fn(decision, history, retry_limit, step)
                if isinstance(result, dict):
                    return result
            except Exception:
                pass
        return None

    def evaluate_repeated_code_product_guard(
        self,
        validation: dict,
        decision: dict,
        history: list,
        step: int,
        job_id: str,
        goal: str,
        planner_memory_snapshot: dict,
    ) -> dict | None:
        """Evaluate repeated code product guard."""
        guard_fn = self.deps.get("repeated_code_product_validation")
        if guard_fn and isinstance(decision, dict):
            try:
                result = guard_fn(validation, decision, history, step)
                if isinstance(result, dict):
                    return result
            except Exception:
                pass
        return None

    def evaluate_repeated_rejection_guard(
        self,
        validation: dict,
        decision: dict,
        history: list,
        step: int,
        job_id: str,
        goal: str,
        planner_memory_snapshot: dict,
    ) -> dict | None:
        """Evaluate repeated rejection guard."""
        guard_fn = self.deps.get("repeated_rejection_validation")
        if guard_fn and isinstance(decision, dict):
            try:
                result = guard_fn(validation, decision, history, step)
                if isinstance(result, dict):
                    return result
            except Exception:
                pass
        return None

    def evaluate_final_guard(
        self,
        decision: dict,
        validation: dict,
        history: list,
        step: int,
        job_id: str,
        goal: str,
        planner_memory_snapshot: dict,
        should_attempt_vulkan: bool,
        repair_result: dict,
    ) -> dict | None:
        """Evaluate final decision guard."""
        guard_fn = self.deps.get("final_decision_guard")
        if guard_fn and isinstance(decision, dict):
            try:
                result = guard_fn(
                    decision, validation, history, step,
                    should_attempt_vulkan=should_attempt_vulkan,
                    repair_result=repair_result,
                )
                if isinstance(result, dict):
                    return result
            except Exception:
                pass
        return None

    def evaluate_native_tool_call_guard(
        self,
        validation: dict,
        decision: dict,
        history: list,
        step: int,
        job_id: str,
        goal: str,
        planner_memory_snapshot: dict,
    ) -> dict | None:
        """Evaluate native tool call guard."""
        guard_fn = self.deps.get("native_tool_call_guard")
        if guard_fn and isinstance(decision, dict):
            try:
                result = guard_fn(validation, decision, history, step)
                if isinstance(result, dict):
                    return result
            except Exception:
                pass
        return None


class FinalizationPhaseManager:
    """Manages job finalization phases."""

    def __init__(
        self,
        job_id: str,
        state: dict,
        deps: dict,
    ) -> None:
        self.job_id = job_id
        self.state = state
        self.deps = deps
        self._finalize_agentic_job = deps["finalize_agentic_job"]

    def finalize(
        self,
        status: str,
        message: str,
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        """Finalize the agentic job."""
        return self._finalize_agentic_job(
            self.job_id, self.state, status, message, extra
        )