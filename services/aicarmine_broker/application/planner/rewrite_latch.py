"""Rewrite latch state machine extracted from validator.py.

Manages the ``final_rewrite_latch`` state transitions that control
whether the planner may retry, must fill a gap, or is blocked from
continuing.
"""

from __future__ import annotations

from typing import Any, Dict, Final

# Valid latch states in ascending severity.
_STATES: Final = (
    "inactive",
    "rewrite_required",
    "required_gap_only",
    "terminal_block_required",
)


class RewriteLatchMachine:
    """Deterministic state machine for final-rewrite lane control.

    States (in severity order):
        inactive                        — no rewrite pressure
        rewrite_required                — first rejection, allow retry
        required_gap_only              — second rejection, must fill gap
        terminal_block_required        — blocked, no further retries
    """

    __slots__ = ("_latch", "_reject_count", "_has_gap_route")

    def __init__(
        self,
        latch: str = "inactive",
        *,
        reject_count: int = 0,
        has_gap_route: bool = False,
    ) -> None:
        self._latch = str(latch or "inactive").strip().lower()
        self._reject_count = int(reject_count)
        self._has_gap_route = bool(has_gap_route)

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def next_state(self) -> str:
        """Return the next latch state after one escalation step."""
        if self._latch == "terminal_block_required":
            return self._latch

        if self._reject_count >= 2:
            return "terminal_block_required"

        if self._latch == "required_gap_only":
            return "required_gap_only" if self._has_gap_route else "terminal_block_required"

        # First rejection starts rewrite branch.
        return "rewrite_required"

    def escalate(self) -> "RewriteLatchMachine":
        """Advance one step and return self for chaining."""
        self._reject_count += 1
        self._latch = self.next_state()
        return self

    def clear(self) -> "RewriteLatchMachine":
        """Reset to inactive (called when a valid final answer is produced)."""
        self._latch = "inactive"
        self._reject_count = 0
        self._has_gap_route = False
        return self

    def coerce(self, value: Any) -> str:
        """Normalize a value to a valid latch state."""
        raw = str(value or "inactive").strip().lower()
        return raw if raw in _STATES else "inactive"

    # ------------------------------------------------------------------
    # Contract mutation helpers
    # ------------------------------------------------------------------

    def apply_to_contract(self, contract: Dict[str, Any]) -> Dict[str, Any]:
        """Mutate *contract* with current latch state and return it."""
        contract["final_rewrite_latch"] = self._latch
        contract["planner_may_choose_block"] = (
            self._latch == "terminal_block_required"
        )
        contract["planner_may_choose_final"] = (
            self._latch != "terminal_block_required"
        )
        return contract

    def apply_final_contract(
        self,
        contract: Dict[str, Any],
        *,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Mutate the nested finalization_contract with latch state."""
        final_contract = (
            contract.get("finalization_contract")
            if isinstance(contract.get("finalization_contract"), dict)
            else {}
        )
        final_contract["final_allowed"] = (
            self._latch != "terminal_block_required"
        )
        final_contract["planner_may_choose_final"] = final_contract["final_allowed"]
        final_contract["planner_may_choose_block"] = (
            self._latch == "terminal_block_required"
        )
        if self._latch == "terminal_block_required":
            final_contract["planner_forced_terminal_block"] = True
            final_contract["planner_forced_terminal_block_reason"] = (
                reason or "terminal_block_required"
            )
        if reason:
            final_contract["reason"] = reason
        contract["finalization_contract"] = final_contract
        return contract

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    @property
    def latch(self) -> str:
        return self._latch

    @property
    def reject_count(self) -> int:
        return self._reject_count

    @property
    def is_terminal(self) -> bool:
        return self._latch == "terminal_block_required"

    @property
    def is_active(self) -> bool:
        return self._latch != "inactive"

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"RewriteLatchMachine(latch={self._latch!r}, "
            f"reject_count={self._reject_count}, "
            f"has_gap_route={self._has_gap_route})"
        )


def next_final_rewrite_latch(
    current: str,
    *,
    reject_count: int,
    has_gap_route: bool,
) -> str:
    """Standalone helper (backward compat with old validator module)."""
    machine = RewriteLatchMachine(
        current,
        reject_count=reject_count,
        has_gap_route=has_gap_route,
    )
    return machine.next_state()


def escalate_final_rewrite_retry_count(
    contract: Dict[str, Any],
    *,
    has_gap_route: bool,
) -> Dict[str, Any]:
    """Standalone helper (backward compat)."""
    contract = contract if isinstance(contract, dict) else {}
    current_latch = str(contract.get("final_rewrite_latch") or "").strip().lower()
    if not current_latch:
        return contract
    if current_latch not in {"rewrite_required", "required_gap_only", "terminal_block_required"}:
        return contract
    if contract.get("planner_cuda_rewrite_required") is not True:
        return contract
    if current_latch == "terminal_block_required":
        contract["planner_may_choose_block"] = True
        return contract

    reject_count = int(contract.get("planner_final_quality_reject_count") or 0) + 1
    contract["planner_final_quality_reject_count"] = reject_count

    machine = RewriteLatchMachine(
        current_latch,
        reject_count=reject_count,
        has_gap_route=has_gap_route,
    )
    next_latch = machine.next_state()
    contract["final_rewrite_latch"] = next_latch
    contract["planner_may_choose_block"] = next_latch == "terminal_block_required"

    final_contract = (
        contract.get("finalization_contract")
        if isinstance(contract.get("finalization_contract"), dict)
        else {}
    )
    if next_latch == "terminal_block_required":
        final_contract["planner_may_choose_block"] = True
        final_contract["final_allowed"] = False
        final_contract["planner_may_choose_final"] = False
        final_contract["reason"] = "planner_cuda_rewrite_required_repeated_retry_block_required"
    elif next_latch == "required_gap_only":
        final_contract["reason"] = "planner_cuda_rewrite_required_retry_gap_only"
    else:
        final_contract["reason"] = "planner_cuda_rewrite_required_retry_continue"
    contract["finalization_contract"] = final_contract
    return contract


def clear_final_terminal_block_state(contract: Dict[str, Any]) -> Dict[str, Any]:
    """Standalone helper (backward compat)."""
    contract = contract if isinstance(contract, dict) else {}
    final_contract = (
        contract.get("finalization_contract")
        if isinstance(contract.get("finalization_contract"), dict)
        else {}
    )

    contract["final_rewrite_latch"] = "inactive"
    contract["planner_may_choose_block"] = False
    contract["planner_may_choose_final"] = True
    for key in (
        "planner_cuda_rewrite_required",
        "planner_forced_terminal_block",
        "planner_forced_terminal_block_reason",
        "planner_final_quality_terminal_block",
        "planner_final_quality_terminal_block_count",
        "planner_final_quality_terminal_block_latched",
        "planner_final_quality_latched_patch_axes",
        "planner_final_quality_latched_operator_instructions",
        "planner_final_answer_blocked_reason",
        "planner_final_quality_public_notice",
        "required_next_tool_call",
        "required_next_tool_call_validated",
        "required_next_tool_call_validation_source",
        "required_next_tool_call_invalid_tool",
        "required_next_tool_call_invalid_reason",
        "required_next_tool_call_satisfied",
        "required_next_tool_call_satisfied_reason",
        "required_next_missing_evidences",
        "required_next_output_sections",
        "invalid_required_next_missing_evidences",
        "invalid_required_next_missing_evidence_reason",
        "invalid_required_next_tool_call_paths",
        "invalid_required_next_tool_call_reason",
        "invalid_required_next_tool_call_query",
        "required_next_progress_model_stale",
        "required_next_progress_model",
        "stale_required_next_tool_calls",
        "required_next_progress",
        "required_next_tool_call_validation_error",
        "replan_specialist_route_diagnostics",
        "replan_specialist_route_audit",
        "replan_specialist_retry_audit",
        "replan_specialist_retry_replan",
    ):
        contract.pop(key, None)

    existing_actions = (
        contract.get("candidate_next_actions")
        if isinstance(contract.get("candidate_next_actions"), list)
        else []
    )
    filtered_actions = [
        item for item in existing_actions
        if not (
            isinstance(item, dict)
            and (
                str(item.get("source") or "") == "repo_analysis_final_model_quality"
                or str(item.get("action_id") or "").startswith("repo_analysis_final_quality:")
            )
        )
    ]
    if filtered_actions:
        contract["candidate_next_actions"] = filtered_actions
    else:
        contract.pop("candidate_next_actions", None)

    final_contract["final_allowed"] = True
    final_contract["planner_may_choose_final"] = True
    final_contract["planner_may_choose_block"] = False
    for key in (
        "planner_forced_terminal_block",
        "planner_forced_terminal_block_reason",
        "planner_final_quality_terminal_block",
        "planner_final_quality_terminal_block_count",
        "planner_final_quality_terminal_block_latched",
        "planner_final_quality_latched_patch_axes",
        "planner_final_quality_latched_operator_instructions",
        "planner_final_answer_blocked_reason",
        "planner_final_quality_public_notice",
        "required_next_tool_call",
        "required_next_missing_evidences",
        "required_next_output_sections",
        "replan_specialist_route_diagnostics",
        "replan_specialist_route_audit",
        "replan_specialist_retry_audit",
        "replan_specialist_retry_replan",
    ):
        final_contract.pop(key, None)
    if final_contract.get("reason") in {
        "repo_analysis_final_quality_no_runnable_gap_terminal_block",
        "repo_analysis_final_model_quality_rejected_no_runnable_gap",
        "planner_cuda_rewrite_required_repeated_retry_block_required",
        "planner_cuda_rewrite_required_retry_gap_only",
        "planner_cuda_rewrite_required_retry_continue",
        "required_next_tool_call_unknown_tool",
        "required_next_tool_call_not_in_current_surface",
    }:
        final_contract.pop("reason", None)
    contract["finalization_contract"] = final_contract
    return contract