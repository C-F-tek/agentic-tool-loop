from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker import planner  # noqa: E402


def test_planner_turn_facade_preserves_input_error_block(monkeypatch) -> None:
    monkeypatch.setattr(planner, "_input_error_goal", lambda _goal: True)

    decision = planner.planner_decision("job-test", {"goal": "bad input"}, 1, [])

    assert decision["action"] == "block"
    assert decision["reason"] == "missing_user_request_no_fallback"
    assert "No semantic fallback" in decision["final_answer"]

