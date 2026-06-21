"""Planner loop controller - extracted from run_agentic_planner_job.

This module extracts the main planning loop, tool execution, and decision
handling from the ~2900-line run_agentic_planner_job function into a
separate, testable class.

Design:
- Pure functions where possible (no state mutation)
- Event emission handled by caller via deps
- State mutation handled by caller via deps
- Only business logic lives in this class
"""

from __future__ import annotations

import itertools
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)


class PlannerLoopController:
    """Controls the main planner loop execution.

    This class encapsulates:
    - The main for step in itertools.count() loop
    - Tool execution and dispatch
    - Decision normalization and action handling
    - Inner utility functions that were nested in run_agentic_planner_job
    """

    def __init__(
        self,
        job_id: str,
        deps: Mapping[str, Any],
        config: Mapping[str, Any],
        state: dict[str, Any],
        history: list[dict[str, Any]],
        loop_state: Any,
        root: Path,
        max_steps: int,
    ) -> None:
        """Initialize with all required dependencies.

        Args:
            job_id: Job identifier.
            deps: Dependency injections.
            config: Configuration dictionary.
            state: Agent job state.
            history: Planner history rows.
            loop_state: PlannerLoopState instance.
            root: Agent job root path.
            max_steps: Maximum semantic steps.
        """
        self.job_id = job_id
        self.deps = deps
        self.config = config
        self.state = state
        self.history = history
        self.loop_state = loop_state
        self.root = root
        self.max_steps = max_steps

        # Extract frequently used deps
        self._normalize_terminal_planner_decision = deps["normalize_terminal_planner_decision"]
        self._agentic_tool_allowed = deps["agentic_tool_allowed"]
        self._tool_cache_hit = deps["tool_cache_hit"]
        self._tool_cache_key = deps["tool_cache_key"]
        self._cached_tool_result = deps["cached_tool_result"]
        self._repeated_tool_call_count = deps["repeated_tool_call_count"]
        self._compact_tool_result_for_planner = deps["compact_tool_result_for_planner"]
        self._write_json = deps["write_json"]
        self._append_agent_event = deps["append_agent_event"]
        self._write_agent_job_state = deps["write_agent_job_state"]
        self._persist_loop_turn_memory = lambda row: deps["write_loop_turn_memory"](
            job_id, state, row, root, history
        )
        self._support_subturn_tools = frozenset({
            "planner_scratchpad_read",
            "planner_scratchpad_write",
            "runtime_sqlite_memory_search",
            "runtime_sqlite_memory_write",
        })

        # State tracking
        self.support_subturns_used = 0
        self.support_semantic_turns_used = 0
        self.support_semantic_steps_marked: set[int] = set()

    def execute_step(
        self,
        step: int,
        semantic_step: int,
        decision: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Execute a single planner step (tool execution or terminal action).

        This is the main step execution logic extracted from the loop body.
        Returns None on success (continue loop), finalize dict on terminal.

        Args:
            step: Physical step number.
            semantic_step: Semantic step number.
            decision: Normalized planner decision.

        Returns:
            None if tool executed successfully, finalize dict if terminal.
        """
        action = str(decision.get("action") or "tool").strip().lower()

        # --- final ---
        if action in {"final", "done", "complete", "completed"}:
            return self._handle_final_decision(decision, step)

        # --- block ---
        if action in {"block", "blocked", "need_user", "needs_user"}:
            return self._handle_block_decision(decision)

        # --- tool ---
        return self._handle_tool_decision(decision, step, semantic_step)

    def _handle_final_decision(
        self,
        decision: dict[str, Any],
        step: int,
    ) -> dict[str, Any]:
        """Handle terminal final/done/complete decision."""
        final_answer = str(
            decision.get("final_answer") or decision.get("answer")
            or decision.get("summary") or "Job completed."
        )
        terminal_decision = dict(decision)
        terminal_decision["step"] = step
        return {
            "action": "finalize",
            "status": "completed",
            "final_answer": final_answer,
            "extra": {
                "history": self.history,
                "planner_decision": terminal_decision,
            },
        }

    def _handle_block_decision(
        self,
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle terminal block/blocked/need_user decision."""
        final_answer = str(decision.get("final_answer") or decision.get("reason") or "Job blocked.")
        return {
            "action": "finalize",
            "status": "blocked_needs_attention",
            "final_answer": final_answer,
            "extra": {
                "history": self.history,
                "planner_decision": decision,
                "blocked_by": decision.get("reason"),
            },
        }

    def _handle_tool_decision(
        self,
        decision: dict[str, Any],
        step: int,
        semantic_step: int,
    ) -> dict[str, Any] | None:
        """Handle tool execution decision."""
        from ...tool_dispatch import dispatch_tool  # noqa
        from ...tool_contract import normalize_tool_name, sanitize_tool_args  # noqa

        VALID_INTERNAL_TOOLS = self.config["VALID_INTERNAL_TOOLS"]
        original_args = dict(self.state.get("original_args") or {})
        public_tool_name = str(self.state.get("public_tool_name") or "vulkan_helper")

        tool = normalize_tool_name(str(decision.get("tool") or ""))
        args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
        internal_args = sanitize_tool_args(tool, dict(args), original_args, public_tool_name)

        # Check for repeated tool calls
        if self._repeated_tool_call_count(self.history, tool, internal_args) >= 2:
            return {"action": "repeat_guard", "tool": tool}

        # Check cache hit
        cache_key = self._tool_cache_key(tool, internal_args)
        hit = self._tool_cache_hit(self.history, tool, internal_args)
        if hit:
            effective_cache_key = cache_key or str(hit.get("cache_key") or "")
            return {
                "action": "cache_hit",
                "tool": tool,
                "cache_key": effective_cache_key,
                "result": self._cached_tool_result(hit, effective_cache_key),
            }

        # Approval gate
        approval_mode = str(self.state.get("approval_mode") or "safe_write_lab")
        allowed, block_reason = self._agentic_tool_allowed(tool, internal_args, approval_mode)
        if not allowed:
            return {"action": "tool_blocked", "reason": block_reason, "tool": tool}

        # Execute tool
        return {
            "action": "execute_tool",
            "tool": tool,
            "internal_args": internal_args,
            "step": step,
            "semantic_step": semantic_step,
            "approval_mode": approval_mode,
        }

    def build_support_subturn_context(
        self,
        step_number: int,
    ) -> dict[str, Any]:
        """Build context for support subturn detection.

        Returns dict with support_subturn info and semantic_step calculation.
        """
        tool = ""  # Caller provides this
        decision = {}  # Caller provides this

        def support_subturn_tool(t: str) -> bool:
            return normalize_tool_name(t) in self._support_subturn_tools

        def support_subturn_decision(d: dict[str, Any]) -> bool:
            if str(d.get("action") or "").strip().lower() != "tool":
                return False
            return support_subturn_tool(str(d.get("tool") or ""))

        physical_step = max(1, int(step_number))
        counted_support_turns = self.support_semantic_turns_used
        if physical_step in self.support_semantic_steps_marked:
            counted_support_turns = max(0, counted_support_turns - 1)
        semantic_step = max(1, physical_step - counted_support_turns)

        is_support_subturn = support_subturn_decision(decision)

        return {
            "is_support_subturn": is_support_subturn,
            "semantic_step": semantic_step,
            "support_subturns_used": self.support_subturns_used,
        }

    def mark_support_subturn(
        self,
        row: dict[str, Any],
        semantic_step: int,
    ) -> None:
        """Mark a row as support subturn and update state."""
        self.support_subturns_used += 1
        try:
            physical_step = int(row.get("step") or 0)
        except (TypeError, ValueError):
            physical_step = 0
        if physical_step > 0 and physical_step not in self.support_semantic_steps_marked:
            self.support_semantic_steps_marked.add(physical_step)
            self.support_semantic_turns_used += 1
        row["support_subturn"] = True
        row["semantic_step"] = semantic_step
        result = row.get("tool_result")
        if isinstance(result, dict):
            result["support_subturn"] = True
            result["semantic_step"] = semantic_step
            result["support_subturn_index"] = self.support_subturns_used
            result["support_semantic_turns_used"] = self.support_semantic_turns_used
        self.state["support_subturns_used"] = self.support_subturns_used
        self.state["support_semantic_turns_used"] = self.support_semantic_turns_used

    def build_step_budget_guidance(self, step_number: int) -> dict[str, Any]:
        """Build step budget guidance for planner prompt."""
        remaining_steps = max(0, self.max_steps - int(step_number) + 1)
        if remaining_steps <= 0:
            return {}
        if remaining_steps == 1:
            mode = "force_terminal_decision"
        elif remaining_steps == 2:
            mode = "prepare_terminal_decision"
        else:
            return {}
        return {
            "schema": "planner_step_budget_guidance.v1",
            "mode": mode,
            "current_step": int(step_number),
            "max_steps": int(self.max_steps),
            "remaining_steps": int(remaining_steps),
            "source": "AICARMINE_AGENT_MAX_STEPS",
            "controller_does_not_auto_final": True,
        }

    def build_runtime_debug_packet(
        self,
        step_number: int,
        phase: str,
        planner_decision: dict[str, Any],
        validation: dict[str, Any] | None = None,
        evidence_contract: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build runtime debug packet for event emission."""
        return self.deps["build_runtime_debug_packet"](
            job_id=self.job_id,
            step=step_number,
            phase=phase,
            goal=str(self.state.get("goal") or ""),
            decision=planner_decision,
            validator_result=validation,
            evidence_contract=evidence_contract or {},
            extra=extra,
        )

    def persist_turn_memory(self, row: dict[str, Any]) -> None:
        """Persist loop turn memory to state."""
        self.state["controller_loop_turn_memory_last_write"] = self.deps["write_loop_turn_memory"](
            self.job_id,
            self.state,
            row,
            self.root,
            self.history,
        )

    def append_history_row(self, row: dict[str, Any]) -> None:
        """Append row to history and persist."""
        self.loop_state.append_history_row(row)
        self.persist_turn_memory(row)
        self._write_agent_job_state(self.state)