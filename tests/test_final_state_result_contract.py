from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.final_state_result import compact_final_state_result  # noqa: E402


def _ledger(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"step": item.get("step"), "tool": item.get("tool")} for item in history]


def test_compact_final_state_result_empty_for_non_dict() -> None:
    assert compact_final_state_result(None, history_ledger_builder=_ledger) == {}


def test_compact_final_state_result_preserves_terminal_fields_and_history_tail() -> None:
    result = {
        "auto_finalized_by": "",
        "blocked_by": "max_steps_reached",
        "rejected_tool": "repo_read",
        "error": None,
        "history": [{"step": step, "tool": f"tool_{step}"} for step in range(10)],
        "agent_flow_diagnostics": {"steps": 10},
        "planner_decision": {
            "action": "final",
            "tool": "",
            "reason": "done",
            "selected_by_3572": True,
            "raw": "not exposed",
        },
    }

    compact = compact_final_state_result(result, history_ledger_builder=_ledger)

    assert compact["blocked_by"] == "max_steps_reached"
    assert compact["rejected_tool"] == "repo_read"
    assert compact["history_count"] == 10
    assert compact["history_tail"][0] == {"step": 2, "tool": "tool_2"}
    assert compact["history_tail"][-1] == {"step": 9, "tool": "tool_9"}
    assert compact["agent_flow_diagnostics"] == {"steps": 10}
    assert compact["planner_decision"] == {
        "action": "final",
        "reason": "done",
        "selected_by_3572": True,
    }


def test_compact_final_state_result_omits_empty_sections() -> None:
    compact = compact_final_state_result(
        {"planner_decision": {"tool": "", "reason": None}},
        history_ledger_builder=_ledger,
    )

    assert compact["planner_decision"] == {}
