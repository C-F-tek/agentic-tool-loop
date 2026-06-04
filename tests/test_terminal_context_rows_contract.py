from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.public_payload.terminal_context_rows import (  # noqa: E402
    executed_tool_rows,
    planner_decision_rows,
    terminal_context_alias,
    validation_rejection_rows,
)


def test_terminal_context_alias_points_to_tool_context_payload() -> None:
    assert terminal_context_alias() == {
        "schema": "agentic_terminal_context_alias.v1",
        "alias_of": "tool_context_for_30b",
        "same_payload": True,
    }


def test_planner_decision_rows_keeps_decision_facts_only() -> None:
    rows = planner_decision_rows([
        {"step": 1},
        {
            "step": 2,
            "decision": {
                "action": "tool",
                "tool": "repo_read",
                "arguments": {"path": "a.py"},
                "reason": "read target",
                "raw": "ignored",
            },
        },
    ])

    assert rows == [{
        "step": 2,
        "action": "tool",
        "tool": "repo_read",
        "arguments": {"path": "a.py"},
        "reason": "read target",
    }]


def test_validation_rejection_rows_filters_controller_guard_validation_only() -> None:
    rows = validation_rejection_rows([
        {"step": 1, "tool_result": {"tool": "controller_guard", "guard_type": "other"}},
        {
            "step": 2,
            "tool_result": {
                "tool": "controller_guard",
                "guard_type": "planner_decision_validation",
                "violations": ["missing_evidence"],
                "rejected_decision": {"action": "final"},
                "evidence_contract": {"final_allowed": False},
                "summary": "blocked",
                "artifact": "ignored",
            },
        },
    ])

    assert rows == [{
        "step": 2,
        "violations": ["missing_evidence"],
        "rejected_decision": {"action": "final"},
        "evidence_contract": {"final_allowed": False},
        "summary": "blocked",
    }]


def test_executed_tool_rows_omits_controller_guard() -> None:
    rows = executed_tool_rows([
        {"step": 1, "tool_result": {"tool": "controller_guard", "ok": True}},
        {
            "step": 2,
            "tool_result": {
                "tool": "repo_list_files",
                "ok": True,
                "path": ".",
                "count": 10,
                "total_matches": 20,
                "items_total": 30,
                "paths_total": 40,
                "stdout": "ignored",
            },
        },
    ])

    assert rows == [{
        "step": 2,
        "tool": "repo_list_files",
        "ok": True,
        "path": ".",
        "count": 10,
        "total_matches": 20,
        "items_total": 30,
        "paths_total": 40,
    }]
