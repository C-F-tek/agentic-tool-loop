from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.history_queries import (  # noqa: E402
    failed_code_edit_proposal_validation_row,
    history_has_tool,
    history_tool_result,
    successful_code_edit_proposals,
)


def test_history_has_tool_checks_decision_and_tool_result() -> None:
    history = [
        {"decision": {"tool": "repo_read"}},
        {"tool_result": {"tool": "repo_apply_patch", "ok": True}},
    ]

    assert history_has_tool(history, "repo_read")
    assert history_has_tool(history, "repo_apply_patch")
    assert not history_has_tool(history, "repo_validate")


def test_history_tool_result_prefers_tool_result_and_accepts_flat_tool_row() -> None:
    result = {"tool": "repo_read", "ok": True}

    assert history_tool_result({"tool_result": result, "tool": "repo_tree"}) is result
    assert history_tool_result({"tool": "repo_tree", "ok": True}) == {"tool": "repo_tree", "ok": True}
    assert history_tool_result({"decision": {"tool": "repo_read"}}) == {}
    assert history_tool_result("bad") == {}  # type: ignore[arg-type]


def test_successful_code_edit_proposals_returns_only_ok_results() -> None:
    ok_result = {"tool": "repo_propose_code_edit", "ok": True, "target_file": "a.py"}
    history = [
        {"tool_result": {"tool": "repo_propose_code_edit", "ok": False}},
        {"tool_result": ok_result},
        {"tool_result": {"tool": "repo_read", "ok": True}},
    ]

    assert successful_code_edit_proposals(history) == [ok_result]


def test_failed_code_edit_proposal_validation_row_builds_route_shift_guard() -> None:
    row = failed_code_edit_proposal_validation_row({
        "step": 3,
        "decision": {"tool": "repo_propose_code_edit", "arguments": {"target_file": "a.py"}},
        "tool_result": {
            "tool": "repo_propose_code_edit",
            "ok": False,
            "errors": ["unified_diff_missing", "unidiff_parse_error"],
        },
    })

    assert row["step"] == 3
    assert row["guard_type"] == "tool_result_validation"
    assert "repo_propose_code_edit_missing_unified_diff" in row["violations"]
    assert "invalid_code_product_candidate" in row["violations"]
    assert "code_product_route_shift_required" in row["violations"]
    assert row["rejected_decision"]["tool"] == "repo_propose_code_edit"
