from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker import planner  # noqa: E402


def test_planner_validator_facade_preserves_goal_first_signature() -> None:
    result = planner.validate_planner_decision_against_evidence(
        "Read target file README.md",
        {"action": "final", "final_answer": "x"},
        [],
    )

    assert result["ok"] is False
    assert result["violations"][0].startswith("final_not_allowed_by_evidence_contract:")
    assert "README.md" in result["violations"][0]


def test_planner_validator_facade_rejects_text_tool_in_native_mode() -> None:
    result = planner.validate_planner_decision_against_evidence(
        "x",
        {"action": "tool", "tool": "unknown", "arguments": {}},
        [],
    )

    assert result["ok"] is False
    assert result["violations"] == ["planner_text_tool_call_disallowed_in_native_mode"]

