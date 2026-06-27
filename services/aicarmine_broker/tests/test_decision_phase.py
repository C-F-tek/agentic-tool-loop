"""Unit tests — Phase manager classes from loop_phases.py."""
import pytest


class TestDecisionPhaseManager:
    """Tests for DecisionPhaseManager class."""

    def test_has_all_required_methods(self):
        """Verify DecisionPhaseManager has all required guard evaluation methods."""
        from ..application.planner.loop_phases import DecisionPhaseManager
        required = [
            "evaluate_decision",
            "evaluate_memory_claim_guard",
            "evaluate_support_subturn_guard",
            "evaluate_incomprehensible_output_guard",
            "evaluate_unrecoverable_output_guard",
            "evaluate_repeated_code_product_guard",
            "evaluate_repeated_rejection_guard",
            "evaluate_final_guard",
            "evaluate_native_tool_call_guard",
        ]
        for method_name in required:
            assert hasattr(DecisionPhaseManager, method_name), f"Missing method: {method_name}"

    def test_init_requires_job_id_and_state(self):
        """Verify DecisionPhaseManager init requires job_id and state."""
        from ..application.planner.loop_phases import DecisionPhaseManager
        deps = {}
        config = {}
        phase = DecisionPhaseManager(
            job_id="test-job",
            state={"goal": "test"},
            deps=deps,
            config=config,
        )
        assert phase.job_id == "test-job"
        assert phase.state == {"goal": "test"}
        assert phase.deps == deps
        assert phase.config == config

    def test_evaluate_decision_returns_dict(self):
        """Verify evaluate_decision returns expected structure."""
        from ..application.planner.loop_phases import DecisionPhaseManager
        deps = {
            "validate_planner_decision_against_evidence": lambda *a: {"ok": True, "violations": []}
        }
        config = {}
        phase = DecisionPhaseManager(
            job_id="test-job",
            state={"goal": "test goal"},
            deps=deps,
            config=config,
        )
        result = phase.evaluate_decision(
            decision={"action": "tool", "tool": "test"},
            history=[],
            contract={},
        )
        assert isinstance(result, dict)
        assert "ok" in result

    def test_evaluate_memory_claim_guard_returns_none_when_no_guard(self):
        """Verify evaluate_memory_claim_guard returns None when no guard function."""
        from ..application.planner.loop_phases import DecisionPhaseManager
        phase = DecisionPhaseManager(
            job_id="test-job",
            state={"goal": "test"},
            deps={},
            config={},
        )
        result = phase.evaluate_memory_claim_guard(
            memory_claim_text="test claim",
            decision={"action": "tool"},
            validation={"ok": True},
            history=[],
            step=1,
            job_id="test-job",
            goal="test goal",
            planner_memory_snapshot={},
        )
        assert result is None

    def test_evaluate_support_subturn_guard_returns_none_when_no_guard(self):
        """Verify evaluate_support_subturn_guard returns None when no guard function."""
        from ..application.planner.loop_phases import DecisionPhaseManager
        phase = DecisionPhaseManager(
            job_id="test-job",
            state={"goal": "test"},
            deps={},
            config={},
        )
        result = phase.evaluate_support_subturn_guard(
            decision={"action": "tool", "tool": "test"},
            validation={"ok": True},
            history=[],
            step=1,
            semantic_step=1,
            support_subturns_used=0,
            job_id="test-job",
            goal="test goal",
        )
        assert result is None


class TestFinalizationPhaseManager:
    """Tests for FinalizationPhaseManager class."""

    def test_has_init_method(self):
        """Verify FinalizationPhaseManager has __init__."""
        from ..application.planner.loop_phases import FinalizationPhaseManager
        assert hasattr(FinalizationPhaseManager, "__init__")

    def test_init_signature(self):
        """Verify FinalizationPhaseManager init signature (job_id, state, deps)."""
        from ..application.planner.loop_phases import FinalizationPhaseManager
        deps = {
            "finalize_agentic_job": lambda *a: None,
        }
        phase = FinalizationPhaseManager(
            job_id="test-job",
            state={"goal": "test"},
            deps=deps,
        )
        assert phase.job_id == "test-job"
        assert phase.state == {"goal": "test"}


class TestLoopPhaseManager:
    """Tests for LoopPhaseManager class."""

    def test_has_execute_turn_method(self):
        """Verify LoopPhaseManager has execute_turn method."""
        from ..application.planner.loop_phases import LoopPhaseManager
        assert hasattr(LoopPhaseManager, "execute_turn")

    def test_coverage_satisfied_returns_bool(self):
        """Verify coverage_satisfied returns bool."""
        from ..application.planner.loop_phases import LoopPhaseManager
        deps = {
            "planner_evidence_contract": lambda *a: {},
            "planner_memory_surface": lambda *a: {},
            "controller_memory_target_key": lambda *a: "planner",
            "load_agent_job_state": lambda *a: {"goal": "test"},
            "write_agent_job_state": lambda *a: None,
            "validate_planner_decision_against_evidence": lambda *a: {"ok": True},
            "dispatch_tool": lambda *a: {"ok": True},
            "tool_cache_hit": lambda *a: None,
            "tool_cache_key": lambda *a: "",
            "repeated_tool_call_count": lambda *a: 0,
            "append_agent_event": lambda *a: None,
            "sanitize_tool_args": lambda *a: dict(a[1]),
        }
        phase = LoopPhaseManager(
            job_id="test",
            state={"goal": "test"},
            deps=deps,
            config={},
            root=None,
            history=[],
            loop_state=None,
            max_steps=50,
        )
        result = phase.coverage_satisfied({"coverage_satisfied": True})
        assert isinstance(result, bool)

    def test_support_subturn_decision_returns_bool(self):
        """Verify support_subturn_decision returns bool."""
        from ..application.planner.loop_phases import LoopPhaseManager
        deps = {
            "planner_evidence_contract": lambda *a: {},
            "planner_memory_surface": lambda *a: {},
            "controller_memory_target_key": lambda *a: "planner",
            "load_agent_job_state": lambda *a: {"goal": "test"},
            "write_agent_job_state": lambda *a: None,
            "validate_planner_decision_against_evidence": lambda *a: {"ok": True},
            "dispatch_tool": lambda *a: {"ok": True},
            "tool_cache_hit": lambda *a: None,
            "tool_cache_key": lambda *a: "",
            "repeated_tool_call_count": lambda *a: 0,
            "append_agent_event": lambda *a: None,
            "sanitize_tool_args": lambda *a: dict(a[1]),
        }
        phase = LoopPhaseManager(
            job_id="test",
            state={"goal": "test"},
            deps=deps,
            config={},
            root=None,
            history=[],
            loop_state=None,
            max_steps=50,
        )
        result = phase.support_subturn_decision({"action": "tool", "is_terminal": False})
        assert isinstance(result, bool)

    def test_force_terminal_decision_active_returns_bool(self):
        """Verify force_terminal_decision_active returns bool."""
        from ..application.planner.loop_phases import LoopPhaseManager
        deps = {
            "planner_evidence_contract": lambda *a: {},
            "planner_memory_surface": lambda *a: {},
            "controller_memory_target_key": lambda *a: "planner",
            "load_agent_job_state": lambda *a: {"goal": "test"},
            "write_agent_job_state": lambda *a: None,
            "validate_planner_decision_against_evidence": lambda *a: {"ok": True},
            "dispatch_tool": lambda *a: {"ok": True},
            "tool_cache_hit": lambda *a: None,
            "tool_cache_key": lambda *a: "",
            "repeated_tool_call_count": lambda *a: 0,
            "append_agent_event": lambda *a: None,
            "sanitize_tool_args": lambda *a: dict(a[1]),
        }
        phase = LoopPhaseManager(
            job_id="test",
            state={"goal": "test"},
            deps=deps,
            config={},
            root=None,
            history=[],
            loop_state=None,
            max_steps=50,
        )
        result = phase.force_terminal_decision_active(semantic_step=10, max_steps=5)
        assert isinstance(result, bool)
        assert result is True

    def test_build_runtime_debug_packet_returns_dict(self):
        """Verify build_runtime_debug_packet returns dict."""
        from ..application.planner.loop_phases import LoopPhaseManager
        deps = {
            "planner_evidence_contract": lambda *a: {},
            "planner_memory_surface": lambda *a: {},
            "controller_memory_target_key": lambda *a: "planner",
            "load_agent_job_state": lambda *a: {"goal": "test"},
            "write_agent_job_state": lambda *a: None,
            "validate_planner_decision_against_evidence": lambda *a: {"ok": True},
            "dispatch_tool": lambda *a: {"ok": True},
            "tool_cache_hit": lambda *a: None,
            "tool_cache_key": lambda *a: "",
            "repeated_tool_call_count": lambda *a: 0,
            "append_agent_event": lambda *a: None,
            "sanitize_tool_args": lambda *a: dict(a[1]),
        }
        phase = LoopPhaseManager(
            job_id="test",
            state={"goal": "test"},
            deps=deps,
            config={},
            root=None,
            history=[],
            loop_state=None,
            max_steps=50,
        )
        result = phase.build_runtime_debug_packet(
            step_number=1,
            phase="decision",
            planner_decision={"action": "tool", "tool": "test"},
            validation={"ok": True, "violations": []},
        )
        assert isinstance(result, dict)
        assert "schema" in result
        assert result.get("step") == 1


class TestPreseedPhaseManager:
    """Tests for PreseedPhaseManager class."""

    def test_has_execute_preseed_method(self):
        """Verify PreseedPhaseManager has execute_preseed method."""
        from ..application.planner.loop_phases import PreseedPhaseManager
        assert hasattr(PreseedPhaseManager, "execute_preseed")

    def test_init_signature(self):
        """Verify PreseedPhaseManager init signature."""
        from ..application.planner.loop_phases import PreseedPhaseManager
        deps = {
            "tool_cache_key": lambda *a: "",
            "compact_tool_result_for_planner": lambda *a: {},
            "write_json": lambda *a: None,
            "append_agent_event": lambda *a: None,
            "initial_orientation_surface_from_history": lambda *a: [],
        }
        config = {}
        root = None
        job_id = "test"
        state = {"goal": "test"}
        history = []
        loop_state = None
        phase = PreseedPhaseManager(
            job_id=job_id,
            state=state,
            deps=deps,
            config=config,
            root=root,
            history=history,
            loop_state=loop_state,
        )
        assert phase.job_id == job_id
        assert phase.state == state


class TestBatchDecisionPhase:
    """Tests for BatchDecisionPhase class."""

    def test_has_init_method(self):
        """Verify BatchDecisionPhase has __init__."""
        from ..application.planner.loop_phases import BatchDecisionPhase
        assert hasattr(BatchDecisionPhase, "__init__")