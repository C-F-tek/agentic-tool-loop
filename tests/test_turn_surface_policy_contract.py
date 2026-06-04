from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.turn_surface_policy import (  # noqa: E402
    apply_turn_surface_policy,
    candidate_tool_names,
    contract_final_required_now,
)


def _order(names: set[str]) -> list[str]:
    return sorted(names)


def test_contract_final_required_now_from_finalization_and_progress() -> None:
    contract = {
        "finalization_contract": {"final_allowed": True},
        "required_next_progress": "produce action=final now",
    }

    assert contract_final_required_now(contract)


def test_apply_turn_surface_policy_filters_final_to_answer_chunk_write() -> None:
    contract = {
        "finalization_contract": {"final_allowed": True},
        "required_next_progress": "produce action=final now",
        "candidate_next_actions": [
            {"tool": "repo_read", "arguments": {"path": "a.py"}},
            {"tool": "planner_scratchpad_write", "arguments": {"kind": "answer_chunk", "text": "x"}},
        ],
    }

    result = apply_turn_surface_policy(contract, order_tool_names=_order)

    assert result["candidate_next_actions"] == [
        {"tool": "planner_scratchpad_write", "arguments": {"kind": "answer_chunk", "text": "x"}}
    ]
    assert result["turn_tool_surface_policy"]["allowed_tool_names"] == ["planner_scratchpad_write"]
    assert result["turn_tool_surface_policy"]["required_next_tool_call"]["tool"] == "planner_scratchpad_write"


def test_apply_turn_surface_policy_filters_incomplete_code_product_proposals() -> None:
    contract = {
        "required_next_progress": "call repo_propose_code_edit with complete payload from candidate_next_actions",
        "code_product_contract": {"required": True},
        "candidate_next_actions": [
            {
                "tool": "repo_propose_code_edit",
                "arguments": {"edit_kind": "unified_diff", "old_text": "old", "new_text": "new"},
            },
            {
                "tool": "repo_propose_code_edit",
                "arguments": {
                    "edit_kind": "unified_diff",
                    "unified_diff": "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n",
                },
            },
        ],
    }

    result = apply_turn_surface_policy(contract, order_tool_names=_order)

    assert len(result["candidate_next_actions"]) == 1
    assert result["candidate_next_actions"][0]["arguments"]["unified_diff"].startswith("---")


def test_apply_turn_surface_policy_locks_empty_tool_surface_for_block() -> None:
    contract = {
        "required_next_progress": "return action=block because code_product_build_state blocked_incomplete",
        "code_product_contract": {"required": True},
        "candidate_next_actions": [{"tool": "repo_read", "arguments": {"path": "a.py"}}],
    }

    result = apply_turn_surface_policy(contract, order_tool_names=_order)

    assert result["candidate_next_actions"] == []
    assert result["turn_tool_surface_policy"]["locked_empty_tool_surface"] is True


def test_candidate_tool_names_reads_candidate_actions() -> None:
    assert candidate_tool_names({
        "candidate_next_actions": [
            {"tool": "repo.read"},
            {"tool": "planner_scratchpad_write"},
        ]
    }) == {"repo_read", "planner_scratchpad_write"}
