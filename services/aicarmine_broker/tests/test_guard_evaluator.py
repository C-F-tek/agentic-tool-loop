"""Smoke tests — verify all phase manager classes load without import errors."""
import pytest


def test_guard_evaluator_import():
    """Verify GuardEvaluator class can be imported."""
    from ..application.planner.guard_evaluator import GuardEvaluator
    assert GuardEvaluator is not None


def test_loop_controller_import():
    """Verify PlannerLoopController class can be imported."""
    from ..application.planner.loop_controller import PlannerLoopController
    assert PlannerLoopController is not None


def test_evidence_contract_manager_import():
    """Verify ContractMutationPhase class can be imported."""
    from ..application.planner.evidence_contract_manager import ContractMutationPhase
    assert ContractMutationPhase is not None


def test_loop_phases_import():
    """Verify all phase managers in loop_phases.py can be imported."""
    from ..application.planner.loop_phases import (
        PreseedPhaseManager,
        LoopPhaseManager,
        DecisionPhaseManager,
        FinalizationPhaseManager,
        BatchDecisionPhase,
    )
    assert PreseedPhaseManager is not None
    assert LoopPhaseManager is not None
    assert DecisionPhaseManager is not None
    assert FinalizationPhaseManager is not None
    assert BatchDecisionPhase is not None


def test_guard_evaluator_instantiation(mock_deps, mock_config):
    """Verify GuardEvaluator can be instantiated with mock deps."""
    from ..application.planner.guard_evaluator import GuardEvaluator
    deps = mock_deps
    config = mock_config
    # Add missing required dep key
    deps["controller_guard_result_for_validation"] = lambda *a, **k: {}
    guard_evaluator = GuardEvaluator(deps, config)
    assert guard_evaluator is not None
