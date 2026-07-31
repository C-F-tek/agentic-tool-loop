"""Planner decision validator owner.

Refactored to delegate to ValidatorPipeline.run() for all validation stages.
The monolithic validate_planner_decision_against_evidence function has been
replaced by the pipeline orchestrator in validator_pipeline.py.

Backward-compat: validate_planner_decision_against_evidence remains as a thin
wrapper that delegates to ValidatorPipeline.run().
"""

from __future__ import annotations

from typing import Any, Mapping

from aicarmine_broker.application.planner.validator_pipeline import ValidatorPipeline


def validate_planner_decision_against_evidence(
    goal: str,
    decision: dict[str, Any],
    history: list[dict[str, Any]],
    require_native_tool_call: bool = False,
    *,
    deps: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Delegate to the 9-stage validation pipeline.

    Parameters
    ----------
    goal : str
        The planner goal being validated.
    decision : dict
        The terminal planner decision to validate.
    history : list[dict]
        Turn history for evidence lookups.
    require_native_tool_call : bool
        Reserved for future native-mode enforcement.
    deps : Mapping[str, Any]
        Dependency map passed through to pipeline stages.
    config : Mapping[str, Any]
        Configuration passed through to pipeline stages.

    Returns
    -------
    dict
        Validation result with keys ``ok``, ``violations``, and ``evidence_contract``.
    """
    pipeline = ValidatorPipeline()
    return pipeline.run(
        goal=goal,
        decision=decision,
        history=history,
        deps=deps,
        config=config,
    )