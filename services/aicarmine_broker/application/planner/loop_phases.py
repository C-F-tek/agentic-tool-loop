"""Extracted phase manager classes for run_agentic_planner_job.

This module contains phase manager classes that replace the monolithic
run_agentic_planner_job function's inline helpers and nested logic.
"""

from __future__ import annotations

import traceback
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
        """Evaluate native tool call required guard.
        
        Returns guard_result if rejected, None if valid.
        Mirrors GuardEvaluator.evaluate_native_tool_call_guard logic.
        """
        violations = {str(v) for v in (validation.get("violations") if isinstance(validation.get("violations"), list) else [])}
        if "planner_native_tool_call_required" not in violations:
            return None

        prior_native_empty_guards = self.deps.get("_controller_guard_count", lambda h, t: 0)(
            history,
            "planner_native_tool_call_required",
        )
        retry_limit = int(self.config.get("AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES", 0))

        if prior_native_empty_guards >= retry_limit:
            return {
                "guard_result": None,
                "should_continue": False,
                "should_finalize": True,
                "final_status": "blocked_needs_attention",
                "final_reason": (
                    "planner_native_tool_call_required_repeated: planner native tool mode "
                    "was active, tools were provided to Ollama, but the planner repeatedly "
                    "returned no message.tool_calls. Controller did not fall back to JSON-text "
                    "tool execution."
                ),
                "final_extra": {
                    "history": history,
                    "planner_decision": decision,
                    "blocked_by": "planner_native_tool_call_required_repeated",
                    "validation": validation,
                },
            }

        guard_result = self.deps.get("_controller_guard_result_for_validation", lambda *a, **k: {})(
            validation,
            decision,
            job_id=job_id,
            step=step,
            goal=goal,
        )
        guard_result["guard_type"] = "planner_native_tool_call_required"
        guard_result["summary"] = "planner_native_tool_call_required"
        guard_result["retry_count"] = prior_native_empty_guards
        guard_result["retry_limit"] = retry_limit

        return {
            "guard_result": guard_result,
            "should_continue": True,
            "should_finalize": False,
        }


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


# ==================================================================
# BatchDecisionPhase (NEW — extracted from loop.py ~1231-1536)
# ==================================================================

class BatchDecisionPhase:
    """Manages native tool batch decision validation phases.

    Extracted from the inline batch decision handling in run_agentic_planner_job.
    Handles all batch guard checks, micro-batch contract validation,
    call signature deduplication, and vulkan repair logic.
    """

    def __init__(
        self,
        job_id: str,
        step: int,
        state: dict,
        history: list,
        deps: dict,
        config: dict,
    ) -> None:
        self.job_id = job_id
        self.step = step
        self.state = state
        self.history = history
        self.deps = deps
        self.config = config
        self._tool_cache_key = deps["tool_cache_key"]
        self._normalize_tool_name = deps["normalize_tool_name"]
        self._sanitize_tool_args = deps["sanitize_tool_args"]
        self._build_runtime_debug_packet = deps["build_runtime_debug_packet"]
        self._validate_planner_decision_against_evidence = deps["validate_planner_decision_against_evidence"]
        self._should_attempt_vulkan_repair = deps["should_attempt_vulkan_repair"]
        self._vulkan_repair_invalid_planner_decision = deps["vulkan_repair_invalid_planner_decision"]
        self._normalize_terminal_planner_decision = deps["normalize_terminal_planner_decision"]
        self._native_required_repaired_tool_decision_disallowed = deps["native_required_repaired_tool_decision_disallowed"]
        self._controller_guard_result_for_validation = deps["controller_guard_result_for_validation"]
        self._validation_without_full_evidence_contract = deps["validation_without_full_evidence_contract"]
        self._append_agent_event = deps["append_agent_event"]

    def evaluate_batch_decision(
        self,
        decision: dict,
        calls: list,
        batch_evidence_contract: dict,
        micro_batch_contract: dict,
        loop_controller: Any,
        dispatch_tool: Callable,
        sanitize_tool_args: Callable,
        write_json: Callable,
        original_args: dict,
        public_tool_name: str,
        planner_evidence_contract: Callable,
    ) -> tuple[dict, list[dict], bool]:
        """Evaluate a tool_batch decision and return (batch_guard, batch_decisions, should_break)."""
        batch_decisions: list[dict[str, Any]] = []
        batch_guard: dict[str, Any] = {}
        used_micro_batch_action_ids: set[str] = set()
        used_micro_batch_call_signatures: set[str] = set()

        # Guard 1: Empty calls
        if not calls:
            batch_guard = self._build_batch_guard(
                guard_type="native_tool_batch_invalid",
                summary="native_tool_batch_empty",
                violations=["native_tool_batch_empty"],
                validation={
                    "ok": False,
                    "violations": ["native_tool_batch_empty"],
                    "evidence_contract": batch_evidence_contract,
                },
            )
            return batch_guard, batch_decisions, True

        # Guard 2: Too large
        native_max_parallel = int(self.config.get("AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY") or 1)
        if len(calls) > native_max_parallel:
            batch_guard = self._build_batch_guard(
                guard_type="native_tool_batch_too_large",
                summary="native_tool_batch_exceeds_readonly_limit",
                violations=["native_tool_batch_too_large"],
                extra={
                    "native_tool_call_count": len(calls),
                    "native_tool_call_limit": native_max_parallel,
                },
                validation={
                    "ok": False,
                    "violations": ["native_tool_batch_too_large"],
                    "evidence_contract": batch_evidence_contract,
                },
            )
            return batch_guard, batch_decisions, True

        # Guard 3: Contract not allowed
        if micro_batch_contract.get("allowed") is not True:
            batch_guard = self._build_batch_guard(
                guard_type="native_tool_batch_contract",
                summary="native_tool_batch_not_allowed_by_evidence_contract",
                violations=["native_tool_batch_not_allowed_by_evidence_contract"],
                extra={"micro_batch_contract": micro_batch_contract},
                validation={
                    "ok": False,
                    "violations": ["native_tool_batch_not_allowed_by_evidence_contract"],
                    "evidence_contract": batch_evidence_contract,
                },
            )
            return batch_guard, batch_decisions, True

        # Process each call in the batch
        for call in calls:
            if not isinstance(call, dict):
                batch_guard = self._build_batch_guard(
                    guard_type="native_tool_batch_invalid",
                    summary="native_tool_batch_call_invalid",
                    violations=["native_tool_batch_call_invalid"],
                    validation={
                        "ok": False,
                        "violations": ["native_tool_batch_call_invalid"],
                        "evidence_contract": batch_evidence_contract,
                    },
                )
                return batch_guard, batch_decisions, True

            # Build call_decision
            call_decision = {
                "action": "tool",
                "tool": self._normalize_tool_name(str(call.get("tool") or "")),
                "arguments": call.get("arguments") if isinstance(call.get("arguments"), dict) else {},
                "reason": "native_tool_call_batch",
                "native_tool_call": True,
                "raw_native_tool_call": call.get("raw_tool_call") if isinstance(call.get("raw_tool_call"), dict) else call,
            }
            if isinstance(decision.get("allowed_tool_names"), list):
                call_decision["allowed_tool_names"] = list(decision["allowed_tool_names"])
            if isinstance(decision.get("allowed_native_tool_names"), list):
                call_decision["allowed_native_tool_names"] = list(decision["allowed_native_tool_names"])

            internal_args = sanitize_tool_args(
                call_decision["tool"],
                dict(call_decision["arguments"]),
                original_args,
                public_tool_name,
            )

            # Guard 4: Duplicate call signature
            call_signature = self._canonical_batch_call_key(
                call_decision["tool"],
                internal_args,
            )
            if call_signature in used_micro_batch_call_signatures:
                batch_guard = self._build_batch_guard(
                    guard_type="native_tool_batch_duplicate_call",
                    summary="native_tool_batch_duplicate_call",
                    violations=["native_tool_batch_duplicate_call"],
                    rejected_decision=call_decision,
                    validation={
                        "ok": False,
                        "violations": ["native_tool_batch_duplicate_call"],
                        "evidence_contract": batch_evidence_contract,
                    },
                )
                return batch_guard, batch_decisions, True
            used_micro_batch_call_signatures.add(call_signature)

            # Guard 5: Not in micro-batch contract
            matched_action = self._match_micro_batch_action(
                micro_batch_contract,
                tool=call_decision["tool"],
                internal_args=internal_args,
            )
            if not matched_action:
                batch_guard = self._build_batch_guard(
                    guard_type="native_tool_batch_contract",
                    summary="native_tool_batch_call_not_in_micro_batch_contract",
                    violations=["native_tool_batch_call_not_in_micro_batch_contract"],
                    rejected_decision=call_decision,
                    extra={"micro_batch_contract": micro_batch_contract},
                    validation={
                        "ok": False,
                        "violations": ["native_tool_batch_call_not_in_micro_batch_contract"],
                        "evidence_contract": batch_evidence_contract,
                    },
                )
                return batch_guard, batch_decisions, True

            # Handle planner_scratchpad_read special case
            if call_decision["tool"] == "planner_scratchpad_read":
                matched_args = (
                    matched_action.get("arguments")
                    if isinstance(matched_action.get("arguments"), dict)
                    else {}
                )
                call_decision["prompt_context_continuation_required"] = {
                    "tool": "planner_scratchpad_read",
                    "arguments": matched_args,
                    "reason": matched_action.get("reason"),
                }

            # Guard 6: Duplicate or missing action_id
            action_id = str(matched_action.get("action_id") or "").strip()
            if not action_id or action_id in used_micro_batch_action_ids:
                batch_guard = self._build_batch_guard(
                    guard_type="native_tool_batch_contract",
                    summary="native_tool_batch_duplicate_or_missing_action_id",
                    violations=["native_tool_batch_duplicate_or_missing_action_id"],
                    rejected_decision=call_decision,
                    extra={"micro_batch_action_id": action_id},
                    validation={
                        "ok": False,
                        "violations": ["native_tool_batch_duplicate_or_missing_action_id"],
                        "evidence_contract": batch_evidence_contract,
                    },
                )
                return batch_guard, batch_decisions, True
            used_micro_batch_action_ids.add(action_id)
            call_decision["micro_batch_action_id"] = action_id
            call_decision["micro_batch_contract_schema"] = micro_batch_contract.get("schema")

            # Guard 7: Non-readonly tool
            if not self._tool_cache_key(call_decision["tool"], internal_args):
                batch_guard = self._build_batch_guard(
                    guard_type="native_tool_batch_non_readonly",
                    summary="native_tool_batch_requires_readonly_tools_only",
                    violations=["native_tool_batch_non_readonly"],
                    rejected_decision=call_decision,
                    validation={
                        "ok": False,
                        "violations": ["native_tool_batch_non_readonly"],
                        "evidence_contract": batch_evidence_contract,
                    },
                )
                return batch_guard, batch_decisions, True

            # Validate call decision against evidence
            validation_i = self._validate_planner_decision_against_evidence(
                str(self.state.get("goal") or ""), call_decision, self.history, self.deps, self.config
            )
            if not validation_i.get("ok"):
                should_repair_call = self._should_attempt_vulkan_repair(call_decision, validation_i, self.history)
                repair_result = {
                    "ok": False,
                    "error": "vulkan_repair_not_applicable_for_this_invalid_decision",
                }
                if should_repair_call:
                    repair_result = self._vulkan_repair_invalid_planner_decision(
                        goal=str(self.state.get("goal") or ""),
                        step=self.step,
                        decision=call_decision,
                        validation=validation_i,
                        history=self.history,
                        state=self.state,
                    )
                if repair_result.get("ok") and isinstance(repair_result.get("repaired_decision"), dict):
                    repaired_decision = self._normalize_terminal_planner_decision(
                        repair_result["repaired_decision"]
                    )
                    if self._native_required_repaired_tool_decision_disallowed(repaired_decision):
                        validation_for_debug = self._validation_without_full_evidence_contract({
                            "ok": False,
                            "violations": ["vulkan_repair_tool_decision_disallowed_in_native_mode"],
                            "evidence_contract": validation_i.get("evidence_contract"),
                        })
                        batch_guard = {
                            "tool": "controller_guard",
                            "ok": True,
                            "guard_type": "native_tool_batch_validation",
                            "summary": "vulkan_repair_tool_decision_disallowed_in_native_mode",
                            "violations": ["vulkan_repair_tool_decision_disallowed_in_native_mode"],
                            "rejected_decision": call_decision,
                            "evidence_contract_summary": validation_for_debug.get("evidence_contract_summary"),
                            "evidence_contract_chars": validation_for_debug.get("evidence_contract_chars"),
                            "evidence_contract_sha256": validation_for_debug.get("evidence_contract_sha256"),
                            "runtime_debug_packet": self._build_runtime_debug_packet(
                                step_number=self.step,
                                phase="CONTROLLER_GUARD",
                                planner_decision=call_decision,
                                validation=validation_for_debug,
                                extra={"repaired_decision_disallowed": True},
                            ),
                            "vulkan_repair": repair_result,
                        }
                        return batch_guard, batch_decisions, True
                    self._append_agent_event(
                        self.job_id,
                        "vulkan_gpu0_decision_repair",
                        "Vulkan/GPU0 repaired invalid native batch tool call.",
                        {"repair_ok": True, "repaired_decision": repaired_decision},
                        step=self.step,
                    )
                    decision = repaired_decision
                    break
                batch_guard = self._controller_guard_result_for_validation(
                    validation_i,
                    call_decision,
                    job_id=self.job_id,
                    step=self.step,
                    goal=str(self.state.get("goal") or ""),
                )
                batch_guard["guard_type"] = "native_tool_batch_validation"
                batch_guard["summary"] = "native_tool_batch_validation_failed"
                if should_repair_call:
                    batch_guard["vulkan_repair"] = repair_result
                return batch_guard, batch_decisions, True

            batch_decisions.append(call_decision)

        return batch_guard, batch_decisions, False

    def _build_batch_guard(
        self,
        guard_type: str,
        summary: str,
        violations: list,
        rejected_decision: dict | None = None,
        extra: dict | None = None,
        validation: dict | None = None,
    ) -> dict:
        """Build a controller_guard batch_guard dict with consistent structure."""
        result = {
            "tool": "controller_guard",
            "ok": True,
            "guard_type": guard_type,
            "summary": summary,
            "violations": violations,
        }
        if rejected_decision:
            result["rejected_decision"] = rejected_decision
        if extra:
            result.update(extra)
        if validation:
            result["runtime_debug_packet"] = self._build_runtime_debug_packet(
                step_number=self.step,
                phase="CONTROLLER_GUARD",
                planner_decision=rejected_decision or {},
                validation=validation,
            )
        return result

    def _canonical_batch_call_key(self, tool_name: str, internal_args: dict) -> str:
        """Generate canonical call signature for deduplication."""
        from ..tool_surface.required_tool_call import canonical_batch_call_key
        return canonical_batch_call_key(tool_name, internal_args)

    def _match_micro_batch_action(self, micro_batch_contract: dict, tool: str, internal_args: dict) -> dict | None:
        """Match a call against micro-batch contract actions."""
        for action in (micro_batch_contract.get("actions") or []):
            if not isinstance(action, dict):
                continue
            if action.get("tool") == tool:
                action_args = action.get("arguments", {})
                if isinstance(action_args, dict) and all(
                    internal_args.get(k) == v for k, v in action_args.items()
                ):
                    return action
        return None


__all__ = [
    "PreseedPhaseManager",
    "LoopPhaseManager",
    "DecisionPhaseManager",
    "FinalizationPhaseManager",
    "BatchDecisionPhase",
]