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
    decision_matches_prompt_context_continuation,
    dedupe_candidate_actions,
    final_composition_tool_names_from_candidates,
    preserve_required_next_tool_call_for_prompt,
    required_next_tool_call_from_action,
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


def test_required_next_tool_call_from_action_keeps_only_window_arguments() -> None:
    action = {
        "tool": "planner.scratchpad.read",
        "arguments": {
            "kind": "prompt_context_window",
            "document_id": "doc-1",
            "offset": 100,
            "max_chars": 500,
            "target_file": "a.py",
            "ignored": "drop",
        },
        "reason": "continue window",
    }

    assert required_next_tool_call_from_action(action) == {
        "tool": "planner_scratchpad_read",
        "arguments": {
            "kind": "prompt_context_window",
            "document_id": "doc-1",
            "offset": 100,
            "max_chars": 500,
            "target_file": "a.py",
        },
        "reason": "continue window",
    }
    assert required_next_tool_call_from_action({"tool": "repo_read", "arguments": {"path": "a.py"}}) == {}


def test_preserve_required_next_tool_call_for_prompt_restores_exact_surface() -> None:
    matched = {
        "tool": "planner_scratchpad_read",
        "arguments": {
            "kind": "prompt_context_window",
            "document_id": "doc-1",
            "offset": 100,
            "max_chars": 500,
        },
        "reason": "continue window",
    }
    payload = {
        "evidence_contract": {
            "candidate_next_actions": [
                {"tool": "repo_read", "arguments": {"path": "a.py"}},
            ],
            "finalization_contract": {"final_allowed": True},
        }
    }
    previous = {
        "required_next_tool_call": required_next_tool_call_from_action(matched),
        "forbidden_repeated_tool_calls": [{"document_id": "doc-1", "offset": 0}],
        "candidate_next_actions": [matched],
        "required_next_progress": "read exact continuation",
        "finalization_contract": {"final_allowed": False, "reason": "required continuation"},
    }

    preserve_required_next_tool_call_for_prompt(payload, previous)

    evidence = payload["evidence_contract"]
    assert payload["required_next_tool_call"] == previous["required_next_tool_call"]
    assert evidence["required_next_tool_call"] == previous["required_next_tool_call"]
    assert evidence["forbidden_repeated_tool_calls"] == [{"document_id": "doc-1", "offset": 0}]
    assert evidence["candidate_next_actions"][0] == matched
    assert evidence["required_next_progress"] == "read exact continuation"
    assert evidence["planner_may_choose_final"] is False
    assert evidence["finalization_contract"]["final_allowed"] is False


def test_decision_matches_prompt_context_continuation_requires_exact_window() -> None:
    continuation = {
        "tool": "planner_scratchpad_read",
        "arguments": {
            "kind": "prompt_context_window",
            "document_id": "doc-1",
            "offset": 100,
            "max_chars": 500,
        },
    }
    decision = {
        "tool": "planner.scratchpad.read",
        "arguments": {
            "kind": "prompt_context_window",
            "document_id": "doc-1",
            "offset": 100,
            "max_chars": 500,
        },
    }

    assert decision_matches_prompt_context_continuation(decision, continuation) is True
    assert decision_matches_prompt_context_continuation(
        {**decision, "tool": "repo_read"},
        continuation,
    ) is False
    assert decision_matches_prompt_context_continuation(
        {"tool": "planner_scratchpad_read", "arguments": {**decision["arguments"], "document_id": "other"}},
        continuation,
    ) is False
    assert decision_matches_prompt_context_continuation(
        {"tool": "planner_scratchpad_read", "arguments": {**decision["arguments"], "offset": 101}},
        continuation,
    ) is False
    assert decision_matches_prompt_context_continuation(
        {"tool": "planner_scratchpad_read", "arguments": {**decision["arguments"], "max_chars": 400}},
        continuation,
    ) is False


def test_decision_matches_prompt_context_continuation_ignores_non_read_continuation() -> None:
    assert decision_matches_prompt_context_continuation(
        {"tool": "repo_read", "arguments": {"path": "a.py"}},
        {"tool": "repo_read"},
    ) is True
