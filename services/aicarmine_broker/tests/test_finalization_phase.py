"""Unit tests — FinalizationPhaseManager finalize() method."""
import pytest


class TestFinalizationPhaseManager:
    """Tests for FinalizationPhaseManager finalize() method."""

    def test_finalize_cancelled(self):
        """Verify cancelled status returns correct dict."""
        from ..application.planner.loop_phases import FinalizationPhaseManager
        deps = {
            "finalize_agentic_job": lambda *a: {"status": a[2], "message": a[3], "extra": a[4]},
        }
        phase = FinalizationPhaseManager(
            job_id="test-job",
            state={"goal": "test"},
            deps=deps,
        )
        result = phase.finalize("cancelled", "Job cancelled by user", {"reason": "user_request"})
        assert isinstance(result, dict)
        assert result["status"] == "cancelled"

    def test_finalize_completed(self):
        """Verify completed status with history and decision."""
        from ..application.planner.loop_phases import FinalizationPhaseManager
        deps = {
            "finalize_agentic_job": lambda *a: {"status": a[2], "message": a[3], "extra": a[4]},
        }
        phase = FinalizationPhaseManager(
            job_id="test-job",
            state={"goal": "test"},
            deps=deps,
        )
        result = phase.finalize("completed", "Job completed successfully", {"history_len": 10})
        assert isinstance(result, dict)
        assert result["status"] == "completed"

    def test_finalize_blocked_needs_attention(self):
        """Verify blocked_needs_attention with extra context."""
        from ..application.planner.loop_phases import FinalizationPhaseManager
        deps = {
            "finalize_agentic_job": lambda *a: {"status": a[2], "message": a[3], "extra": a[4]},
        }
        phase = FinalizationPhaseManager(
            job_id="test-job",
            state={"goal": "test"},
            deps=deps,
        )
        result = phase.finalize("blocked_needs_attention", "Guard rejected decision", {"violation": "test"})
        assert isinstance(result, dict)
        assert result["status"] == "blocked_needs_attention"

    def test_finalize_blocked_needs_consent(self):
        """Verify blocked_needs_consent for approval mode blocks."""
        from ..application.planner.loop_phases import FinalizationPhaseManager
        deps = {
            "finalize_agentic_job": lambda *a: {"status": a[2], "message": a[3], "extra": a[4]},
        }
        phase = FinalizationPhaseManager(
            job_id="test-job",
            state={"goal": "test"},
            deps=deps,
        )
        result = phase.finalize("blocked_needs_consent", "Tool requires user consent", {"approval_mode": "safe_write_lab"})
        assert isinstance(result, dict)
        assert result["status"] == "blocked_needs_consent"