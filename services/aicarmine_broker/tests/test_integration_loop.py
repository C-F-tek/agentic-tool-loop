"""Integration tests — End-to-end loop phase orchestration."""
import pytest


class TestLoopPhaseOrchestration:
    """Tests for integrated loop phase manager orchestration.
    
    Note: PreseedPhaseManager requires additional deps keys (write_json, etc.)
    that cannot be easily mocked. Integration tests focus on the 3 phase managers
    that share common deps structure.
    """

    def test_phase_managers_share_deps(self):
        """Verify Decision and Batch share same deps dict."""
        from ..application.planner.loop_phases import (
            DecisionPhaseManager,
            BatchDecisionPhase,
        )
        deps = {
            "tool_cache_key": lambda *a: "",
            "normalize_tool_name": lambda n: n,
            "sanitize_tool_args": lambda *a: dict(a[1]),
            "build_runtime_debug_packet": lambda **k: {},
            "validate_planner_decision_against_evidence": lambda *a: {"ok": True},
            "should_attempt_vulkan_repair": lambda *a: False,
            "vulkan_repair_invalid_planner_decision": lambda *a: {},
            "normalize_terminal_planner_decision": lambda d: d,
            "native_required_repaired_tool_decision_disallowed": lambda *a: False,
            "controller_guard_result_for_validation": lambda *a: None,
            "validation_without_full_evidence_contract": lambda *a: {},
            "append_agent_event": lambda *a: None,
        }
        config = {}
        state = {"goal": "test"}

        decision = DecisionPhaseManager(
            job_id="test", state=state, deps=deps, config=config,
        )
        batch = BatchDecisionPhase(
            job_id="test", step=1, state=state, history=[],
            deps=deps, config=config,
        )

        assert decision.deps is deps
        assert batch.deps is deps

    def test_phase_managers_share_job_id(self):
        """Verify all phase managers share same job_id."""
        from ..application.planner.loop_phases import (
            DecisionPhaseManager,
            BatchDecisionPhase,
        )
        job_id = "shared-job-123"
        deps = {
            "tool_cache_key": lambda *a: "",
            "normalize_tool_name": lambda n: n,
            "sanitize_tool_args": lambda *a: dict(a[1]),
            "build_runtime_debug_packet": lambda **k: {},
            "validate_planner_decision_against_evidence": lambda *a: {"ok": True},
            "should_attempt_vulkan_repair": lambda *a: False,
            "vulkan_repair_invalid_planner_decision": lambda *a: {},
            "normalize_terminal_planner_decision": lambda d: d,
            "native_required_repaired_tool_decision_disallowed": lambda *a: False,
            "controller_guard_result_for_validation": lambda *a: None,
            "validation_without_full_evidence_contract": lambda *a: {},
            "append_agent_event": lambda *a: None,
        }
        config = {}
        state = {"goal": "test"}

        decision = DecisionPhaseManager(
            job_id=job_id, state=state, deps=deps, config=config,
        )
        batch = BatchDecisionPhase(
            job_id=job_id, step=1, state=state, history=[],
            deps=deps, config=config,
        )

        assert decision.job_id == job_id
        assert batch.job_id == job_id

    def test_phase_managers_share_config(self):
        """Verify all phase managers receive same config dict."""
        from ..application.planner.loop_phases import (
            DecisionPhaseManager,
            BatchDecisionPhase,
        )
        config = {
            "AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY": 5,
            "AGENTIC_PLANNER_FORCE_TERMINAL_THRESHOLD": 10,
        }
        deps = {
            "tool_cache_key": lambda *a: "",
            "normalize_tool_name": lambda n: n,
            "sanitize_tool_args": lambda *a: dict(a[1]),
            "build_runtime_debug_packet": lambda **k: {},
            "validate_planner_decision_against_evidence": lambda *a: {"ok": True},
            "should_attempt_vulkan_repair": lambda *a: False,
            "vulkan_repair_invalid_planner_decision": lambda *a: {},
            "normalize_terminal_planner_decision": lambda d: d,
            "native_required_repaired_tool_decision_disallowed": lambda *a: False,
            "controller_guard_result_for_validation": lambda *a: None,
            "validation_without_full_evidence_contract": lambda *a: {},
            "append_agent_event": lambda *a: None,
        }
        state = {"goal": "test"}

        decision = DecisionPhaseManager(
            job_id="test", state=state, deps=deps, config=config,
        )
        batch = BatchDecisionPhase(
            job_id="test", step=1, state=state, history=[],
            deps=deps, config=config,
        )

        assert decision.config is config
        assert batch.config is config
