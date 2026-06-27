"""Extracted phase manager classes for planner_decision.

This module contains phase manager classes that replace the monolithic
planner_decision function's inline helpers and nested logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class PayloadBuilderPhase:
    """Manages payload building phases for planner decisions."""

    def __init__(
        self,
        job_id: str,
        state: dict,
        step: int,
        deps: dict,
        config: dict,
    ) -> None:
        self.job_id = job_id
        self.state = state
        self.step = step
        self.deps = deps
        self.config = config
        self._build_planner_user_payload = deps["build_planner_user_payload"]
        self._filter_tool_manifest_for_names = deps["filter_tool_manifest_for_names"]
        self._native_tools_schema_for_planner = deps["native_tools_schema_for_planner"]

    def build_native_payload(
        self,
        tool_names: list[str],
        history: list,
        evidence_contract: dict,
        intrinsic_context: dict,
        last_tool_result: dict,
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict]]:
        """Build payload for a given set of native tool names."""
        schema = (
            self._native_tools_schema_for_planner(tool_names)
            if self.config.get("AGENTIC_PLANNER_NATIVE_TOOLS")
            else []
        )
        manifest = self._filter_tool_manifest_for_names(
            [], tool_names
        )
        payload, budget = self._build_planner_user_payload(
            job_id=self.job_id,
            state=self.state,
            step=self.step,
            history=history,
            tool_manifest=manifest,
            evidence_contract=evidence_contract,
            planner_memory={},
            intrinsic_context=intrinsic_context,
            last_tool_result=last_tool_result,
            native_tools_schema=schema,
        )
        return payload, budget, schema


class EvidenceContractPhase:
    """Manages evidence contract construction phases."""

    def __init__(
        self,
        deps: dict,
        config: dict,
    ) -> None:
        self.deps = deps
        self.config = config
        self._planner_evidence_contract = deps["planner_evidence_contract"]
        self._apply_step_budget_guidance_to_contract = deps.get(
            "apply_step_budget_guidance_to_contract", lambda c, s: c
        )

    def build_contract(
        self,
        goal: str,
        history: list,
        intrinsic_context: dict,
        step_budget_guidance: dict | None = None,
    ) -> dict[str, Any]:
        """Build evidence contract for current state."""
        contract = self._planner_evidence_contract(goal, history, intrinsic_context=intrinsic_context)
        if step_budget_guidance and isinstance(step_budget_guidance, dict):
            contract = self._apply_step_budget_guidance_to_contract(contract, step_budget_guidance)
        return contract


class ToolSurfacePhase:
    """Manages tool surface determination phases."""

    def __init__(
        self,
        deps: dict,
    ) -> None:
        self.deps = deps
        self._tool_surface_names_for_turn = deps["tool_surface_names_for_turn"]
        self._post_final_reject_turn_tool_names = deps.get(
            "post_final_reject_turn_tool_names", lambda c, t, **kw: t
        )

    def determine_turn_tool_names(
        self,
        goal: str,
        evidence_contract: dict,
        intrinsic_context: dict,
        prompt_context_continuation_required: dict = None,
        known_tool_names: set = None,
    ) -> list[str]:
        """Determine the tool names available for this turn."""
        base_names = self._tool_surface_names_for_turn(
            goal=goal,
            evidence_contract=evidence_contract,
            intrinsic_context=intrinsic_context,
        )
        refined_names = self._post_final_reject_turn_tool_names(
            evidence_contract,
            base_names,
            known_tool_names=known_tool_names or set(),
        )
        return refined_names


class RuntimeRootsPhase:
    """Manages runtime roots validation phases."""

    def __init__(self) -> None:
        pass

    def validate_runtime_roots(
        self,
        runtime_roots: dict,
        base_tool_names: list[str],
        native_tool_names: list[str],
    ) -> dict[str, Any]:
        """Validate runtime roots and determine if final is blocked."""
        result = {
            "runtime_roots_mismatch": False,
            "terminal_runtime_surface": False,
            "runtime_roots_mismatch_blocks_final": False,
        }

        def normalized_root(value: str) -> str:
            normalized = str(value or "").strip()
            if not normalized:
                return ""
            return str(Path(normalized).resolve()).lower().replace("\\", "/").rstrip("/")

        lab_root = normalized_root(str(runtime_roots.get("AICARMINE_LAB_REPO") or ""))
        open_terminal_cwd = normalized_root(str(runtime_roots.get("OPEN_TERMINAL_CWD") or ""))
        open_terminal_workdir = normalized_root(str(runtime_roots.get("AICARMINE_OPEN_TERMINAL_WORKDIR") or ""))

        runtime_roots_mismatch = False
        if open_terminal_cwd and lab_root:
            runtime_roots_mismatch = not (
                open_terminal_cwd == lab_root or open_terminal_cwd.startswith(f"{lab_root}/")
            )
        if not runtime_roots_mismatch and open_terminal_workdir and lab_root:
            runtime_roots_mismatch = not (
                open_terminal_workdir == lab_root or open_terminal_workdir.startswith(f"{lab_root}/")
            )

        def is_terminal_runtime_tool(name: str) -> bool:
            lowered = str(name or "").strip().lower()
            return (
                lowered.startswith("terminal_")
                or lowered.startswith("open_terminal_")
                or lowered in {"run_command", "terminal_run_command", "terminal_run_command_wait"}
            )

        terminal_runtime_surface = any(
            is_terminal_runtime_tool(name)
            for name in base_tool_names + native_tool_names
        )
        runtime_roots_mismatch_blocks_final = bool(runtime_roots_mismatch and terminal_runtime_surface)

        result.update({
            "runtime_roots_mismatch": runtime_roots_mismatch,
            "terminal_runtime_surface": terminal_runtime_surface,
            "runtime_roots_mismatch_blocks_final": runtime_roots_mismatch_blocks_final,
        })
        return result


class DecisionExecutionPhase:
    """Manages decision execution phases."""

    def __init__(
        self,
        deps: dict,
    ) -> None:
        self.deps = deps
        self._normalize_terminal_planner_decision = deps["normalize_terminal_planner_decision"]
        self._native_tool_calls_decision = deps["native_tool_calls_decision"]

    def execute_decision(
        self,
        raw_decision: dict[str, Any],
        history: list,
    ) -> dict[str, Any]:
        """Execute a normalized planner decision."""
        decision = self._normalize_terminal_planner_decision(raw_decision)
        return decision