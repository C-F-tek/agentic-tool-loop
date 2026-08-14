"""Pure non-executive catalog of 28 control lanes.

This module provides a frozen dataclass-based catalog describing all 28
control lanes without side effects. It does NOT:
- call models;
- import planner.py or loop.py;
- read environment variables;
- write state or files;
- modify control flow;
- register callbacks/executors;
- perform validations at import time.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

# Ensure no imports from runtime modules
# No: planner, loop, turn, validator, config, environment


@dataclass(frozen=True, slots=True)
class ControlLaneSpec:
    """Frozen specification of a single control lane."""

    lane_id: str
    kind: str
    phase: str
    runtime_scope: str
    authority: str
    provider: str
    validator_required: bool
    affects_control_flow: bool
    may_execute_tools: bool
    default_mode: str
    description: str


# Define all 28 control lanes exactly as specified
CONTROL_LANE_SPECS: tuple[ControlLaneSpec, ...] = (
    ControlLaneSpec(
        lane_id="planner.primary",
        kind="ai",
        phase="plan",
        runtime_scope="loop",
        authority="proposal_only",
        provider="gpu1_planner",
        validator_required=True,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="active",
        description="Primary planning lane that proposes actions for execution.",
    ),
    ControlLaneSpec(
        lane_id="planner.cuda_rewrite",
        kind="ai",
        phase="rewrite",
        runtime_scope="loop",
        authority="proposal_only",
        provider="gpu1_planner",
        validator_required=True,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="active",
        description="CUDA rewrite lane for GPU-accelerated planning rewrites.",
    ),
    ControlLaneSpec(
        lane_id="planner.replan",
        kind="ai",
        phase="replan",
        runtime_scope="loop",
        authority="advisory_only",
        provider="gpu1_planner",
        validator_required=True,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="active",
        description="Replanning lane when current plan fails or becomes obsolete.",
    ),
    ControlLaneSpec(
        lane_id="judge.final_quality",
        kind="ai",
        phase="judge",
        runtime_scope="loop",
        authority="judge_only",
        provider="gpu1_planner",
        validator_required=True,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="active",
        description="Final quality judgment lane for terminal decisions.",
    ),
    ControlLaneSpec(
        lane_id="repair.vulkan_gpu0",
        kind="ai",
        phase="repair",
        runtime_scope="loop",
        authority="repair_only",
        provider="gpu0_task_model",
        validator_required=True,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="active",
        description="Vulkan GPU0 repair lane for fixing invalid states.",
    ),
    ControlLaneSpec(
        lane_id="preplanner.semantic_query",
        kind="ai",
        phase="preplan",
        runtime_scope="loop",
        authority="advisory_only",
        provider="gpu1_planner",
        validator_required=False,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="active",
        description="Semantic query lane for retrieval-augmented preplanning.",
    ),
    ControlLaneSpec(
        lane_id="planner.native_tool_batch",
        kind="hybrid",
        phase="plan",
        runtime_scope="loop",
        authority="proposal_only",
        provider="gpu1_planner",
        validator_required=True,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="active",
        description="Native tool batch planning lane for parallel tool orchestration.",
    ),
    ControlLaneSpec(
        lane_id="planner.guided_terminal_final_quality",
        kind="hybrid",
        phase="terminal",
        runtime_scope="loop",
        authority="proposal_only",
        provider="gpu1_planner",
        validator_required=True,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="active",
        description="Guided terminal synthesis with final quality gates.",
    ),
    ControlLaneSpec(
        lane_id="routing.evidence_gap",
        kind="hybrid",
        phase="route",
        runtime_scope="loop",
        authority="advisory_only",
        provider="mixed",
        validator_required=True,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="active",
        description="Evidence gap detection and routing lane for missing data.",
    ),
    ControlLaneSpec(
        lane_id="planner.incomprehensible_retry",
        kind="hybrid",
        phase="retry",
        runtime_scope="loop",
        authority="proposal_only",
        provider="gpu1_planner",
        validator_required=True,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="active",
        description="Retry lane for incomprehensible model outputs or failures.",
    ),
    ControlLaneSpec(
        lane_id="planner.native_protocol_recovery",
        kind="hybrid",
        phase="retry",
        runtime_scope="loop",
        authority="proposal_only",
        provider="gpu1_planner",
        validator_required=True,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="active",
        description="Native protocol recovery lane for MCP communication failures.",
    ),
    ControlLaneSpec(
        lane_id="orientation.initial",
        kind="ai_candidate",
        phase="orientation",
        runtime_scope="loop",
        authority="bounded_selection",
        provider="gpu1_planner",
        validator_required=False,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="legacy",
        description="Initial orientation lane for bounded area selection.",
    ),
    ControlLaneSpec(
        lane_id="orientation.area_expansion",
        kind="ai_candidate",
        phase="orientation",
        runtime_scope="loop",
        authority="bounded_selection",
        provider="gpu1_planner",
        validator_required=False,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="legacy",
        description="Area expansion lane for growing search boundaries.",
    ),
    ControlLaneSpec(
        lane_id="candidate_actions.ranking",
        kind="ai_candidate",
        phase="rank",
        runtime_scope="loop",
        authority="bounded_ranking",
        provider="gpu1_planner",
        validator_required=False,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="legacy",
        description="Candidate actions ranking lane for action prioritization.",
    ),
    ControlLaneSpec(
        lane_id="planner.max_step_terminal_synthesis",
        kind="ai_candidate",
        phase="terminal",
        runtime_scope="loop",
        authority="proposal_only",
        provider="gpu1_planner",
        validator_required=True,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="legacy",
        description="Max step terminal synthesis for bounded completion attempts.",
    ),
    ControlLaneSpec(
        lane_id="coverage.interpretation",
        kind="hybrid",
        phase="coverage",
        runtime_scope="loop",
        authority="deterministic_enforcement",
        provider="mixed",
        validator_required=True,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="fixed",
        description="Coverage interpretation lane for deterministic enforcement.",
    ),
    ControlLaneSpec(
        lane_id="validator.evidence",
        kind="deterministic",
        phase="validate",
        runtime_scope="loop",
        authority="deterministic_enforcement",
        provider="controller",
        validator_required=False,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="fixed",
        description="Evidence validation lane for deterministic proof checking.",
    ),
    ControlLaneSpec(
        lane_id="quality.deterministic_floor",
        kind="deterministic",
        phase="judge",
        runtime_scope="loop",
        authority="deterministic_enforcement",
        provider="controller",
        validator_required=False,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="fixed",
        description="Deterministic floor quality gate for minimum standards.",
    ),
    ControlLaneSpec(
        lane_id="audit.specialist_route",
        kind="deterministic",
        phase="audit",
        runtime_scope="loop",
        authority="deterministic_enforcement",
        provider="controller",
        validator_required=False,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="fixed",
        description="Specialist routing audit lane for path verification.",
    ),
    ControlLaneSpec(
        lane_id="guard.repeat",
        kind="deterministic",
        phase="guard",
        runtime_scope="loop",
        authority="deterministic_enforcement",
        provider="controller",
        validator_required=False,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="fixed",
        description="Repeat guard lane for preventing infinite loops.",
    ),
    ControlLaneSpec(
        lane_id="cache.tool_result",
        kind="deterministic",
        phase="cache",
        runtime_scope="loop",
        authority="deterministic_enforcement",
        provider="controller",
        validator_required=False,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="fixed",
        description="Tool result caching lane for performance optimization.",
    ),
    ControlLaneSpec(
        lane_id="guard.approval",
        kind="deterministic",
        phase="guard",
        runtime_scope="loop",
        authority="deterministic_enforcement",
        provider="controller",
        validator_required=False,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="fixed",
        description="Approval guard lane for explicit permission gating.",
    ),
    ControlLaneSpec(
        lane_id="dispatch.tool",
        kind="deterministic",
        phase="dispatch",
        runtime_scope="loop",
        authority="deterministic_enforcement",
        provider="controller",
        validator_required=False,
        affects_control_flow=True,
        may_execute_tools=True,
        default_mode="fixed",
        description="Tool dispatch lane for executing validated tool calls.",
    ),
    ControlLaneSpec(
        lane_id="guard.repeated_rejection_breaker",
        kind="deterministic",
        phase="guard",
        runtime_scope="loop",
        authority="deterministic_enforcement",
        provider="controller",
        validator_required=False,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="fixed",
        description="Repeated rejection breaker lane for escape from deadlocks.",
    ),
    ControlLaneSpec(
        lane_id="lifecycle.terminal_status",
        kind="deterministic",
        phase="lifecycle",
        runtime_scope="loop",
        authority="deterministic_enforcement",
        provider="controller",
        validator_required=False,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="fixed",
        description="Terminal status lifecycle lane for job completion signaling.",
    ),
    ControlLaneSpec(
        lane_id="judge.terminal",
        kind="ai",
        phase="terminal",
        runtime_scope="finalizer",
        authority="diagnostic_only",
        provider="gpu1_planner",
        validator_required=False,
        affects_control_flow=False,
        may_execute_tools=False,
        default_mode="active",
        description="Terminal judgment lane for final diagnostic output.",
    ),
    ControlLaneSpec(
        lane_id="diagnostic.npu_phi",
        kind="sidecar",
        phase="diagnostic",
        runtime_scope="loop",
        authority="diagnostic_only",
        provider="npu_phi",
        validator_required=False,
        affects_control_flow=False,
        may_execute_tools=False,
        default_mode="active",
        description="NPU Phi diagnostic sidecar lane for hardware monitoring.",
    ),
    ControlLaneSpec(
        lane_id="boundary.internal_tool_selector",
        kind="boundary",
        phase="select",
        runtime_scope="boundary",
        authority="bounded_selection",
        provider="gpu0_task_model",
        validator_required=False,
        affects_control_flow=True,
        may_execute_tools=False,
        default_mode="active",
        description="Internal tool selector boundary lane for scope enforcement.",
    ),
)

# Build read-only mapping
CONTROL_LANE_BY_ID: Mapping[str, ControlLaneSpec] = MappingProxyType(
    {spec.lane_id: spec for spec in CONTROL_LANE_SPECS}
)


def get_control_lane_spec(lane_id: str) -> ControlLaneSpec | None:
    """Get a control lane spec by ID.

    Args:
        lane_id: The lane identifier to look up.

    Returns:
        The ControlLaneSpec if found, None otherwise.
    """
    return CONTROL_LANE_BY_ID.get(lane_id)


def validate_control_lane_catalog() -> list[str]:
    """Validate the control lane catalog.

    Verifies:
    - Exactly 28 lanes present
    - All lane_ids non-empty
    - All lane_ids unique
    - default_mode in active|legacy|fixed
    - authority non-empty
    - provider non-empty
    - may_execute_tools=true only for dispatch.tool
    - Diagnostic lanes do not have affects_control_flow=true

    Returns:
        List of error messages (empty if valid).
    """
    errors: list[str] = []

    # Check count
    if len(CONTROL_LANE_SPECS) != 28:
        errors.append(f"Expected 28 lanes, found {len(CONTROL_LANE_SPECS)}")

    # Check uniqueness and non-empty IDs
    seen_ids: set[str] = set()
    for spec in CONTROL_LANE_SPECS:
        if not spec.lane_id:
            errors.append(f"Empty lane_id for spec {spec}")
        if spec.lane_id in seen_ids:
            errors.append(f"Duplicate lane_id: {spec.lane_id}")
        seen_ids.add(spec.lane_id)

    # Validate field constraints
    for spec in CONTROL_LANE_SPECS:
        if spec.default_mode not in ("active", "legacy", "fixed"):
            errors.append(
                f"Invalid default_mode '{spec.default_mode}' for {spec.lane_id}"
            )
        if not spec.authority:
            errors.append(f"Empty authority for {spec.lane_id}")
        if not spec.provider:
            errors.append(f"Empty provider for {spec.lane_id}")
        if spec.may_execute_tools and spec.lane_id != "dispatch.tool":
            errors.append(
                f"may_execute_tools=true only allowed for dispatch.tool, got {spec.lane_id}"
            )
        if spec.authority == "diagnostic_only" and spec.affects_control_flow:
            errors.append(
                f"Lane {spec.lane_id} with authority='diagnostic_only' must have affects_control_flow=False"
            )

    return errors


def control_lane_event_metadata(
    lane_id: str,
   
    step: int | None = None,
    attempt: int = 1,
    max_attempts: int | None = None,
    trigger: str = "",
) -> dict[str, object]:
    """Generate event metadata for a control lane invocation.

    Args:
        lane_id: The lane identifier.
        step: Optional step number.
        attempt: Attempt number within the step.
        max_attempts: Maximum attempts allowed.
        trigger: Triggering event description.

    Returns:
        Dictionary with event metadata.
    """
    spec = get_control_lane_spec(lane_id)
    if spec is None:
        return {
            "lane_id": lane_id,
            "error": f"Unknown lane_id: {lane_id}",
            "step": step,
            "attempt": attempt,
            "trigger": trigger,
        }

    return {
        "lane_id": lane_id,
        "lane_kind": spec.kind,
        "phase": spec.phase,
        "runtime_scope": spec.runtime_scope,
        "authority": spec.authority,
        "provider": spec.provider,
        "validator_required": spec.validator_required,
        "affects_control_flow": spec.affects_control_flow,
        "may_execute_tools": spec.may_execute_tools,
        "default_mode": spec.default_mode,
        "description": spec.description,
        "step": step,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "trigger": trigger,
    }


if __name__ == "__main__":
    # Verification when run directly
    print(f"len(CONTROL_LANE_SPECS) = {len(CONTROL_LANE_SPECS)}")
    print(f"len(CONTROL_LANE_BY_ID) = {len(CONTROL_LANE_BY_ID)}")
    print(f"validate_control_lane_catalog() = {validate_control_lane_catalog()}")

    # Demonstrate read-only mapping
    try:
        CONTROL_LANE_BY_ID["nonexistent"] = "should fail"
    except TypeError as e:
        print(f"MappingProxyType correctly prevents mutation: {e}")