"""Unit tests — PreseedPhaseManager class structure."""
import pytest


class TestPreseedPhaseManager:
    """Tests for PreseedPhaseManager class structure only.
    
    Note: execute_preseed() has internal imports from tool_contract module
    that cannot be easily mocked. Only structural tests are included here.
    """

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

    def test_init_stores_deps(self):
        """Verify PreseedPhaseManager stores deps correctly."""
        from ..application.planner.loop_phases import PreseedPhaseManager
        deps = {
            "tool_cache_key": lambda *a: "",
            "compact_tool_result_for_planner": lambda *a: {},
            "write_json": lambda *a: None,
            "append_agent_event": lambda *a: None,
            "initial_orientation_surface_from_history": lambda *a: [],
        }
        phase = PreseedPhaseManager(
            job_id="test-job",
            state={"goal": "test"},
            deps=deps,
            config={},
            root=None,
            history=[],
            loop_state=None,
        )
        assert phase.deps == deps
        assert phase.job_id == "test-job"
