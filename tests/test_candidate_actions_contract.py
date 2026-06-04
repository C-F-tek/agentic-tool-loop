from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.candidate_actions import (  # noqa: E402
    candidate_action_args,
    candidate_action_is_build_state_read,
    candidate_action_is_build_state_write,
    candidate_action_tool,
    dedupe_candidate_actions,
    final_composition_tool_names_from_candidates,
)


def test_candidate_action_accessors_normalize_tool_and_args() -> None:
    action = {"tool": "repo.read", "arguments": {"path": "AGENTS.md"}}

    assert candidate_action_tool(action) == "repo_read"
    assert candidate_action_args(action) == {"path": "AGENTS.md"}
    assert candidate_action_tool("bad") == ""
    assert candidate_action_args({"arguments": []}) == {}


def test_build_state_read_write_detection() -> None:
    write = {"tool": "planner_scratchpad_write", "arguments": {"kind": "code_product_build_state"}}
    read = {"tool": "planner_scratchpad_read", "arguments": {"mode": "code_product_build_state"}}

    assert candidate_action_is_build_state_write(write)
    assert candidate_action_is_build_state_read(read)
    assert not candidate_action_is_build_state_read(write)


def test_dedupe_candidate_actions_skips_non_dict_and_preserves_order() -> None:
    first = {"tool": "repo_read", "arguments": {"path": "a.py"}}
    second = {"tool": "repo_tree", "arguments": {"path": "."}}

    assert dedupe_candidate_actions([first, "bad", first.copy(), second], limit=4) == [first, second]


def test_final_composition_tool_names_from_candidates() -> None:
    contract = {
        "candidate_next_actions": [
            {"tool": "planner_scratchpad_write", "arguments": {"kind": "answer_chunk"}},
            {"tool": "repo_read", "arguments": {"path": "a.py"}},
        ]
    }

    assert final_composition_tool_names_from_candidates(contract) == {"planner_scratchpad_write"}
