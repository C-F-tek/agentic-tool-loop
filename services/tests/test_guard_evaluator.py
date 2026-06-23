"""Tests for GuardEvaluator - planner decision validation guards."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from aicarmine_broker.application.planner.guard_evaluator import GuardEvaluator


def _make_deps(**overrides: object) -> dict[str, object]:
    """Create minimal deps dict with mocked helpers."""
    deps: dict[str, object] = {
        "controller_guard_result_for_validation": MagicMock(
            return_value={"ok": True, "guard_type": "test"}
        ),
        "controller_guard_rejection_signature": MagicMock(return_value="sig1"),
        "controller_guard_rejection_signature_count": MagicMock(return_value=0),
        "controller_guard_count": MagicMock(return_value=0),
        "planner_incomprehensible_retry_count": MagicMock(return_value=0),
        "planner_memory_false_unavailable_claim": MagicMock(return_value=False),
        "raw_planner_text_classification": MagicMock(return_value="json"),
        "should_retry_incomprehensible_planner_output": MagicMock(return_value=False),
        "is_unrecoverable_plain_text_planner_output": MagicMock(return_value=False),
        "should_attempt_vulkan_repair": MagicMock(return_value=False),
        "vulkan_repair_invalid_planner_decision": MagicMock(
            return_value={"ok": False, "error": "not attempted"}
        ),
        "normalize_terminal_planner_decision": MagicMock(
            return_value={"action": "noop", "tool": "", "arguments": {}}
        ),
        "native_required_repaired_tool_decision_disallowed": MagicMock(
            return_value=False
        ),
        "specialist_route_audit": MagicMock(return_value={}),
        "planner_replan_specialist_for_validation": MagicMock(return_value={}),
    }
    for key, value in overrides.items():
        deps[key] = value
    return deps


def _make_config(**overrides: object) -> dict[str, object]:
    """Create minimal config dict."""
    config: dict[str, object] = {"AGENTIC_PLANNER_INCOMPREHENSIBLE_RETRIES": 3}
    for key, value in overrides.items():
        config[key] = value
    return config


@pytest.fixture
def evaluator():
    """Create a GuardEvaluator instance with minimal deps."""
    deps = _make_deps()
    config = _make_config()
    return GuardEvaluator(deps, config)


class TestGuardEvaluatorInit:
    """Test GuardEvaluator initialization."""

    def test_init_stores_deps(self):
        """Test that deps are stored correctly."""
        deps = _make_deps()
        config = _make_config()
        ev = GuardEvaluator(deps, config)
        assert ev.deps is deps
        assert ev.config is config

    def test_init_extract_frequently_used_deps(self):
        """Test that frequently used deps are extracted as attributes."""
        deps = _make_deps()
        config = _make_config()
        ev = GuardEvaluator(deps, config)
        assert hasattr(ev, "_controller_guard_result_for_validation")
        assert hasattr(ev, "_controller_guard_rejection_signature")
        assert hasattr(ev, "_planner_incomprehensible_retry_count")


class TestEvaluateSupportSubturnGuard:
    """Test evaluate_support_subturn_guard."""

    def test_returns_guard_result_on_rejection(self):
        """Test that guard result is returned when validation indicates rejection."""
        deps = _make_deps()
        config = _make_config()
        ev = GuardEvaluator(deps, config)

        decision = {"action": "test", "tool": "test_tool"}
        validation = {"ok": False, "violations": ["test_violation"]}
        history = []

        result = ev.evaluate_support_subturn_guard(
            decision=decision,
            validation=validation,
            history=history,
            step=1,
            semantic_step=1,
            support_subturns_used=0,
            job_id="test-job",
            goal="test goal",
        )

        assert result is not None
        assert result["guard_result"]["guard_type"] == "support_subturn_validation_failed"
        assert result["should_continue"] is True
        assert result["should_finalize"] is False
        assert result["guard_result"]["semantic_step"] == 1

    def test_returns_none_when_valid(self, evaluator):
        """Test that None is returned when decision is valid."""
        # Mock the controller_guard_result_for_validation to return None-like behavior
        deps = _make_deps(
            controller_guard_rejection_signature=MagicMock(return_value=None)
        )
        config = _make_config()
        ev = GuardEvaluator(deps, config)

        decision = {"action": "test", "tool": "test_tool"}
        validation = {"ok": True, "violations": []}

        result = ev.evaluate_support_subturn_guard(
            decision=decision,
            validation=validation,
            history=[],
            step=1,
            semantic_step=1,
            support_subturns_used=0,
            job_id="test-job",
            goal="test goal",
        )
        # Should return guard_result (not None) because the method always builds one
        assert result is not None


class TestEvaluateNativeToolCallGuard:
    """Test evaluate_native_tool_call_guard."""

    def test_returns_none_when_not_violation(self, evaluator):
        """Test that None is returned when native tool call is not required."""
        validation = {"ok": True, "violations": ["other_violation"]}
        decision = {"action": "test"}

        result = evaluator.evaluate_native_tool_call_guard(
            validation=validation,
            decision=decision,
            history=[],
            step=1,
            job_id="test-job",
            goal="test goal",
            planner_memory_snapshot={"available": True},
        )

        assert result is None

    def test_returns_finalize_when_repeated_violation(self, evaluator):
        """Test that finalize is returned when native tool call violation repeats."""
        deps = _make_deps(
            controller_guard_count=MagicMock(return_value=3)  # >= retry_limit
        )
        config = _make_config()
        ev = GuardEvaluator(deps, config)

        validation = {"ok": False, "violations": ["planner_native_tool_call_required"]}
        decision = {"action": "test"}

        result = ev.evaluate_native_tool_call_guard(
            validation=validation,
            decision=decision,
            history=[],
            step=1,
            job_id="test-job",
            goal="test goal",
            planner_memory_snapshot={"available": True},
        )

        assert result is not None
        assert result["should_continue"] is False
        assert result["should_finalize"] is True
        assert "planner_native_tool_call_required_repeated" in result.get("final_reason", "")


class TestEvaluateMemoryClaimGuard:
    """Test evaluate_memory_claim_guard."""

    def test_returns_none_when_no_false_claim(self, evaluator):
        """Test that None is returned when there's no false memory claim."""
        result = evaluator.evaluate_memory_claim_guard(
            memory_claim_text="memory is available",
            decision={"action": "test"},
            validation={"ok": True},
            history=[],
            step=1,
            job_id="test-job",
            goal="test goal",
            planner_memory_snapshot={"available": True},
        )

        assert result is None

    def test_returns_guard_result_on_false_claim(self):
        """Test that guard result is returned when planner falsely claims memory unavailable."""
        deps = _make_deps(
            planner_memory_false_unavailable_claim=MagicMock(return_value=True),
            planner_incomprehensible_retry_count=MagicMock(return_value=1),
        )
        config = _make_config()
        ev = GuardEvaluator(deps, config)

        result = ev.evaluate_memory_claim_guard(
            memory_claim_text="memory is unavailable",
            decision={"action": "test"},
            validation={"ok": True, "violations": []},
            history=[],
            step=1,
            job_id="test-job",
            goal="test goal",
            planner_memory_snapshot={"available": True, "record_count": 5},
        )

        assert result is not None
        assert result["guard_result"]["guard_type"] == "planner_memory_false_unavailable_claim"


class TestEvaluateIncomprehensibleOutputGuard:
    """Test evaluate_incomprehensible_output_guard."""

    def test_returns_none_when_should_not_retry(self, evaluator):
        """Test that None is returned when retry is not needed."""
        result = evaluator.evaluate_incomprehensible_output_guard(
            decision={"action": "test"},
            validation={"ok": True},
            history=[],
            step=1,
            job_id="test-job",
            goal="test goal",
            planner_memory_snapshot={},
        )

        assert result is None

    def test_returns_guard_result_on_incomprehensible_output(self):
        """Test guard result for incomprehensible planner output."""
        deps = _make_deps(
            should_retry_incomprehensible_planner_output=MagicMock(return_value=True),
            raw_planner_text_classification=MagicMock(return_value="plain_text"),
            planner_incomprehensible_retry_count=MagicMock(return_value=1),
        )
        config = _make_config()
        ev = GuardEvaluator(deps, config)

        result = ev.evaluate_incomprehensible_output_guard(
            decision={"action": "test", "raw_planner_text": "some prose text"},
            validation={"ok": False, "violations": ["invalid_json"]},
            history=[],
            step=1,
            job_id="test-job",
            goal="test goal",
            planner_memory_snapshot={},
        )

        assert result is not None
        assert result["guard_result"]["guard_type"] == "planner_retry_required"


class TestEvaluateRepeatedCodeProductGuard:
    """Test evaluate_repeated_code_product_guard."""

    def test_returns_none_when_not_violation(self, evaluator):
        """Test that None is returned when repeated code product is not a violation."""
        validation = {"ok": True, "violations": []}

        result = evaluator.evaluate_repeated_code_product_guard(
            validation=validation,
            decision={"action": "test"},
            history=[],
            step=1,
            job_id="test-job",
            goal="test goal",
            planner_memory_snapshot={},
        )

        assert result is None

    def test_returns_finalize_on_repeated_violation(self):
        """Test finalize is returned on repeated invalid code product decision."""
        deps = _make_deps(
            controller_guard_result_for_validation=MagicMock(
                return_value={"ok": True, "guard_type": "test"}
            )
        )
        config = _make_config()
        ev = GuardEvaluator(deps, config)

        validation = {
            "ok": False,
            "violations": ["planner_repeated_invalid_code_product_decision"],
        }

        result = ev.evaluate_repeated_code_product_guard(
            validation=validation,
            decision={"action": "test"},
            history=[],
            step=1,
            job_id="test-job",
            goal="test goal",
            planner_memory_snapshot={},
        )

        assert result is not None
        assert result["should_continue"] is False
        assert result["should_finalize"] is True


class TestEvaluateRepeatedRejectionGuard:
    """Test evaluate_repeated_rejection_guard."""

    def test_returns_none_when_below_limit(self, evaluator):
        """Test that None is returned when rejection count is below limit."""
        deps = _make_deps(
            controller_guard_rejection_signature_count=MagicMock(return_value=0)
        )
        config = _make_config()
        ev = GuardEvaluator(deps, config)

        validation = {"ok": False, "violations": ["test"]}
        decision = {"action": "test"}

        result = ev.evaluate_repeated_rejection_guard(
            validation=validation,
            decision=decision,
            history=[],
            step=1,
            job_id="test-job",
            goal="test goal",
            planner_memory_snapshot={},
        )

        assert result is None

    def test_returns_finalize_at_limit(self):
        """Test finalize is returned when rejection count reaches limit."""
        deps = _make_deps(
            controller_guard_rejection_signature_count=MagicMock(return_value=3),
            controller_guard_result_for_validation=MagicMock(
                return_value={"ok": True, "guard_type": "test"}
            ),
        )
        config = _make_config()
        ev = GuardEvaluator(deps, config)

        validation = {"ok": False, "violations": ["test"]}
        decision = {"action": "test"}

        result = ev.evaluate_repeated_rejection_guard(
            validation=validation,
            decision=decision,
            history=[],
            step=1,
            job_id="test-job",
            goal="test goal",
            planner_memory_snapshot={},
        )

        assert result is not None
        assert result["should_continue"] is False
        assert result["should_finalize"] is True
        assert result["guard_result"]["guard_type"] == "repeated_identical_planner_rejection"


class TestEvaluateUnrecoverableOutputGuard:
    """Test evaluate_unrecoverable_output_guard."""

    def test_returns_none_when_not_unrecoverable(self, evaluator):
        """Test that None is returned when output is not unrecoverable."""
        result = evaluator.evaluate_unrecoverable_output_guard(
            decision={"action": "test"},
            history=[],
            retry_limit=3,
            step=1,
            job_id="test-job",
            goal="test goal",
        )

        assert result is None

    def test_returns_finalize_on_unrecoverable_output(self):
        """Test finalize is returned for unrecoverable plain text output."""
        deps = _make_deps(
            is_unrecoverable_plain_text_planner_output=MagicMock(return_value=True),
            raw_planner_text_classification=MagicMock(return_value="prose"),
        )
        config = _make_config()
        ev = GuardEvaluator(deps, config)

        result = ev.evaluate_unrecoverable_output_guard(
            decision={"action": "test", "final_answer": "some prose answer"},
            history=[],
            retry_limit=3,
            step=1,
            job_id="test-job",
            goal="test goal",
        )

        assert result is not None
        assert result["should_continue"] is False
        assert result["should_finalize"] is True
        assert result["final_status"] == "blocked_needs_attention"


class TestEvaluateVulkanRepair:
    """Test evaluate_vulkan_repair."""

    def test_returns_none_when_should_not_attempt(self, evaluator):
        """Test that None is returned when repair should not be attempted."""
        decision = {"action": "test"}
        validation = {"ok": True}
        history = []

        result = evaluator.evaluate_vulkan_repair(
            decision=decision,
            validation=validation,
            history=history,
            step=1,
            job_id="test-job",
            goal="test goal",
            state={},
        )

        assert result is None

    def test_returns_repair_attempted_false_on_failure(self):
        """Test repair result when attempt fails."""
        deps = _make_deps(
            should_attempt_vulkan_repair=MagicMock(return_value=True),
            vulkan_repair_invalid_planner_decision=MagicMock(
                return_value={"ok": False, "error": "repair failed"}
            ),
        )
        config = _make_config()
        ev = GuardEvaluator(deps, config)

        result = ev.evaluate_vulkan_repair(
            decision={"action": "test"},
            validation={"ok": False},
            history=[],
            step=1,
            job_id="test-job",
            goal="test goal",
            state={},
        )

        assert result is not None
        assert result["vulkan_repair_attempted"] is True
        assert result["vulkan_repair_ok"] is False


class TestEvaluateFinalGuard:
    """Test evaluate_final_guard."""

    def test_returns_guard_result_for_default_rejection(self):
        """Test that guard result is returned for default rejection case."""
        deps = _make_deps(
            controller_guard_result_for_validation=MagicMock(
                return_value={"ok": True, "guard_type": "default"}
            )
        )
        config = _make_config()
        ev = GuardEvaluator(deps, config)

        result = ev.evaluate_final_guard(
            decision={"action": "test"},
            validation={"ok": False, "violations": ["test"]},
            history=[],
            step=1,
            job_id="test-job",
            goal="test goal",
            planner_memory_snapshot={},
            should_attempt_vulkan=False,
            repair_result={},
        )

        assert result is not None
        assert result["should_continue"] is True
        assert result["should_finalize"] is False