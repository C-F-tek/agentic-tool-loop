"""Extracted phase manager classes for planner_decision.

This module contains phase manager classes that replace the monolithic
planner_decision function's inline helpers and nested logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


# ==================================================================
# Utility Functions (extracted from turn.py)
# ==================================================================

def _dict_from_mapping(value: Any) -> dict[str, Any]:
    """Convert a mapping value to a plain dict with string keys."""
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


# ==================================================================
# PayloadBuilderPhase
# ==================================================================

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


# ==================================================================
# EvidenceContractPhase (extended with coverage checking)
# ==================================================================

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

    def check_coverage(self, contract: dict[str, Any]) -> bool:
        """Check if minimum read coverage is satisfied.
        
        Extracted from _contract_coverage_satisfied in turn.py.
        """
        coverage = _dict_from_mapping(contract.get("minimum_read_coverage"))
        if coverage:
            return coverage.get("coverage_satisfied") is True
        return contract.get("coverage_satisfied") is True


# ==================================================================
# ToolSurfacePhase
# ==================================================================

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


# ==================================================================
# RuntimeRootsPhase
# ==================================================================

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


# ==================================================================
# DecisionExecutionPhase
# ==================================================================

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


# ==================================================================
# RoleOverridePhase (NEW — extracted from turn.py)
# ==================================================================

class RoleOverridePhase:
    """Manages planner role override extraction and system suffix building.
    
    Extracted from _planner_role_override_from_state and 
    _planner_role_system_suffix in turn.py.
    """

    def __init__(self) -> None:
        pass

    def extract_role_override(self, state: dict[str, Any]) -> dict[str, Any]:
        """Extract planner role override from state.
        
        Extracted from _planner_role_override_from_state in turn.py.
        """
        value = state.get("planner_role_override")
        if not isinstance(value, dict):
            return {}
        role = str(value.get("role") or "").strip().lower()
        if role != "planner_cuda_rewrite":
            return {}
        out = {
            key: value.get(key)
            for key in (
                "schema",
                "role",
                "rewrite_target",
                "source_step",
                "instruction",
                "rejected_decision",
                "validator_violations",
                "evidence_contract_sha256",
            )
            if value.get(key) not in (None, "", [], {})
        }
        out["role"] = role
        out["one_shot"] = True
        out["provider"] = "gpu1_planner"
        return out

    def build_system_suffix(self, role_override: dict[str, Any]) -> str:
        """Build system instruction suffix for cuda_rewrite role.
        
        Extracted from _planner_role_system_suffix in turn.py.
        """
        if str(role_override.get("role") or "") != "planner_cuda_rewrite":
            return ""
        rewrite_target = str(role_override.get("rewrite_target") or "decision")
        instruction = str(role_override.get("instruction") or "").strip()
        return (
            "ACTIVE SPECIALIST ROLE: planner_cuda_rewrite on the same GPU1 planner model. "
            f"Rewrite target={rewrite_target}. This is a one-shot continuation of a "
            "validator-rejected planner decision, not a fresh planning episode. Use the "
            "verified evidence and validator feedback already supplied. Do not restart broad "
            "discovery, do not call Vulkan/GPU0, and do not claim success unless the candidate "
            "satisfies the current evidence contract. Return exactly one normal planner decision; "
            "the validator remains authoritative."
            + (f" Specialist instruction: {instruction}" if instruction else "")
        )


# ==================================================================
# StepBudgetPhase (NEW — extracted from turn.py)
# ==================================================================

class StepBudgetPhase:
    """Manages step budget guidance application to evidence contracts.
    
    Extracted from _apply_step_budget_guidance_to_contract and
    _planner_step_budget_guidance_from_state in turn.py.
    """

    def __init__(self, deps: dict) -> None:
        self.deps = deps
        self._enforce_required_scratchpad_read_continuation_contract = deps.get(
            "enforce_required_scratchpad_read_continuation_contract",
            lambda c, call: c,
        )

    def get_step_budget_guidance(self, state: dict[str, Any]) -> dict[str, Any]:
        """Extract step budget guidance from state.
        
        Extracted from _planner_step_budget_guidance_from_state in turn.py.
        """
        guidance = state.get("planner_step_budget_guidance")
        if not isinstance(guidance, dict):
            return {}
        mode = str(guidance.get("mode") or "").strip()
        if mode not in {"prepare_terminal_decision", "force_terminal_decision"}:
            return {}
        return _dict_from_mapping(guidance)

    def apply_guidance_to_contract(
        self,
        contract: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply step budget guidance to evidence contract.
        
        Extracted from _apply_step_budget_guidance_to_contract in turn.py.
        This is the ~200 line function that handles all step budget modes.
        """
        guidance = self.get_step_budget_guidance(state)
        if not guidance:
            return contract

        out = _dict_from_mapping(contract)
        final_contract = _dict_from_mapping(out.get("finalization_contract"))
        coverage_satisfied = self.check_coverage(out)
        final_allowed = final_contract.get("final_allowed") is True and coverage_satisfied
        mode = str(guidance.get("mode") or "")
        guidance_payload = {
            "schema": "planner_step_budget_guidance.v1",
            "mode": mode,
            "current_step": guidance.get("current_step"),
            "max_steps": guidance.get("max_steps"),
            "remaining_steps": guidance.get("remaining_steps"),
            "final_allowed_by_evidence_contract": final_allowed,
            "coverage_satisfied": coverage_satisfied,
            "missing_owner_paths": out.get("missing_owner_paths"),
            "controller_does_not_auto_final": True,
        }
        out["planner_step_budget_guidance"] = guidance_payload

        if mode == "prepare_terminal_decision":
            operational = _dict_from_mapping(out.get("operational_notes"))
            operational["step_budget_hint"] = {
                "mode": mode,
                "remaining_steps": guidance_payload["remaining_steps"],
                "instruction": (
                    "The configured step budget is almost exhausted. Prefer a validator-accepted "
                    "final when the evidence contract allows it; otherwise use at most one targeted "
                    "tool call needed to make the final robust."
                ),
            }
            out["operational_notes"] = operational
            return out

        required = _dict_from_mapping(out.get("required_next_tool_call"))
        required_tool = str(required.get("tool") or "").strip()
        if required_tool == "planner_scratchpad_read":
            guidance_payload["terminal_decision_deferred_by_required_continuation"] = True
            out["planner_step_budget_guidance"] = guidance_payload
            out = self._enforce_required_scratchpad_read_continuation_contract(
                out,
                {
                    "tool": "planner_scratchpad_read",
                    "arguments": _dict_from_mapping(required.get("arguments")),
                    "reason": required.get("reason") or out.get("required_next_progress"),
                },
            )
            operational = _dict_from_mapping(out.get("operational_notes"))
            operational["step_budget_hint"] = {
                "mode": mode,
                "remaining_steps": guidance_payload["remaining_steps"],
                "instruction": (
                    "Step budget is exhausted, but an exact planner_scratchpad_read "
                    "continuation is still required. Consume that continuation before "
                    "any terminal final/block decision."
                ),
            }
            out["operational_notes"] = operational
            return out
        if required_tool in {
            "repo_read",
            "repo_semantic_search",
            "repo_rg_search",
            "repo_search",
            "repo_list_files",
        }:
            guidance_payload["terminal_decision_deferred_by_required_tool_call"] = True
            out["planner_step_budget_guidance"] = guidance_payload
            out["planner_may_choose_final"] = False
            final_contract["final_allowed"] = False
            final_contract["planner_may_choose_final"] = False
            final_contract["reason"] = "step_budget_deferred_by_required_tool_call"
            out["finalization_contract"] = final_contract
            operational = _dict_from_mapping(out.get("operational_notes"))
            operational["step_budget_hint"] = {
                "mode": mode,
                "remaining_steps": guidance_payload["remaining_steps"],
                "instruction": (
                    "Step budget is tight, but a model-selected required_next_tool_call is pending. "
                    "Execute that exact read-only tool before any terminal final/block decision."
                ),
            }
            out["operational_notes"] = operational
            return out

        final_contract["terminal_decision_required_by_step_budget"] = True
        final_contract["tool_calls_disallowed_by_step_budget"] = True
        final_contract["planner_may_choose_final"] = final_allowed
        final_contract["planner_may_choose_block"] = True
        final_contract["coverage_satisfied"] = coverage_satisfied
        if not coverage_satisfied:
            final_contract["final_allowed"] = False
            final_contract["missing_owner_paths"] = out.get("missing_owner_paths")
        out["finalization_contract"] = final_contract
        out["planner_may_choose_block"] = True
        out["planner_may_choose_final"] = final_allowed
        out["candidate_next_actions"] = []
        out.pop("required_next_tool_call", None)
        out.pop("forbidden_repeated_tool_calls", None)

        if final_allowed:
            return out

        out["planner_may_choose_block"] = True
        out["planner_may_choose_final"] = False
        out["candidate_next_actions"] = []
        out.pop("required_next_tool_call", None)
        out.pop("forbidden_repeated_tool_calls", None)
        return out

    def check_coverage(self, contract: dict[str, Any]) -> bool:
        """Check if minimum read coverage is satisfied."""
        coverage = _dict_from_mapping(contract.get("minimum_read_coverage"))
        if coverage:
            return coverage.get("coverage_satisfied") is True
        return contract.get("coverage_satisfied") is True


# ==================================================================
# Export all phase classes and utilities
# ==================================================================

__all__ = [
    # Utilities
    "_dict_from_mapping",
    # Phase classes
    "PayloadBuilderPhase",
    "EvidenceContractPhase",
    "ToolSurfacePhase",
    "RuntimeRootsPhase",
    "DecisionExecutionPhase",
    "RoleOverridePhase",
    "StepBudgetPhase",
]