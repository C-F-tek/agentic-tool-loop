from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker import planner  # noqa: E402


def test_planner_loop_facade_preserves_missing_job_shape(monkeypatch) -> None:
    monkeypatch.setattr(planner, "load_agent_job_state", lambda _job_id: None)

    result = planner.run_agentic_planner_job("missing-job")

    assert result == {"ok": False, "error": "job_not_found", "job_id": "missing-job"}

