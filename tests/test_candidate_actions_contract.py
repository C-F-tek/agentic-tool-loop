from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.tool_surface.candidate_actions import (  # noqa: E402
    candidate_action_args,
    candidate_action_is_build_state_read,
    candidate_action_is_build_state_write,
    candidate_action_tool,
    candidate_actions_from_evidence,
    decision_matches_prompt_context_continuation,
    dedupe_candidate_actions,
    final_composition_tool_names_from_candidates,
    preserve_required_next_tool_call_for_prompt,
    required_next_tool_call_from_action,
)


def _candidate_action_deps(**overrides):
    deps = {
        "repo_rel_token": lambda path: str(path).replace("\\", "/").strip("/"),
        "repo_analysis_goal": lambda goal: "repo" in goal.lower(),
        "repo_doc_or_config": lambda path: str(path).lower().endswith((".md", ".toml", ".json")),
        "low_signal_top_dir": lambda path: False,
        "rank_core_candidates": lambda _file_memory, _list_rows: [],
        "path_exists_repo_relative": lambda _path: True,
        "repo_readable_evidence_file": lambda _path: True,
        "goal_target_scope": lambda _goal: "",
        "input_error_goal": lambda _goal: False,
        "path_under_scope": lambda path, scope: str(path).startswith(scope),
        "core_discovery_read_paths": lambda _candidates, **_kwargs: [],
        "scoped_concrete_read_target": 3,
        "repo_concrete_read_target": 4,
        "scope_read_candidates_from_evidence": lambda _rows, _scope, **_kwargs: [],
        "multi_file_prompt_read_chars": lambda: 1200,
        "meaningful_read_candidates_from_evidence": lambda _rows, **_kwargs: [],
        "single_file_prompt_read_chars": lambda: 800,
        "repo_code_file": lambda path: str(path).endswith(".py"),
    }
    deps.update(overrides)
    return deps


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


def test_candidate_actions_from_evidence_returns_empty_when_final_allowed() -> None:
    assert candidate_actions_from_evidence(
        "analizza repo",
        [],
        [{"paths_preview": ["README.md"]}],
        [],
        True,
        **_candidate_action_deps(),
    ) == []


def test_candidate_actions_from_evidence_reads_scoped_candidates() -> None:
    actions = candidate_actions_from_evidence(
        "analizza services",
        [],
        [{"path": "services", "paths_preview": ["services/a.py"]}],
        [],
        False,
        **_candidate_action_deps(
            goal_target_scope=lambda _goal: "services",
            scope_read_candidates_from_evidence=lambda _rows, _scope, **_kwargs: ["services/a.py"],
        ),
    )

    assert actions == [{
        "action": "tool",
        "tool": "repo_read",
        "arguments": {"paths": ["services/a.py"], "max_chars": 1200},
        "reason": "Read up to 3 dynamically discovered readable files inside requested scope services before finalizing.",
    }]


def test_candidate_actions_from_evidence_lists_missing_scope_before_reading() -> None:
    actions = candidate_actions_from_evidence(
        "analizza services",
        [],
        [],
        [],
        False,
        **_candidate_action_deps(goal_target_scope=lambda _goal: "services"),
    )

    assert actions[0]["tool"] == "repo_list_files"
    assert actions[0]["arguments"] == {"path": "services", "limit": 120}


def test_candidate_actions_from_evidence_prefers_meaningful_repo_reads() -> None:
    actions = candidate_actions_from_evidence(
        "analizza repo",
        [],
        [{"path": "services", "paths_preview": ["services/a.py"]}],
        [],
        False,
        **_candidate_action_deps(
            meaningful_read_candidates_from_evidence=lambda _rows, **_kwargs: ["services/a.py"],
        ),
    )

    assert actions[0]["tool"] == "repo_read"
    assert actions[0]["arguments"] == {"paths": ["services/a.py"], "max_chars": 1200}
    assert actions[1]["arguments"] == {"path": "services/a.py", "max_chars": 800}


def test_candidate_actions_from_evidence_filters_unreadable_discovery_paths_before_prompting() -> None:
    actions = candidate_actions_from_evidence(
        "analizza repo e proponi diff",
        [],
        [{"path": ".", "paths_preview": ["README.md"]}],
        [],
        False,
        **_candidate_action_deps(
            core_discovery_read_paths=lambda _candidates, **_kwargs: [
                "ia_carmine/runtime/heap_gate/provider_context.py",
                "README.md",
            ],
            path_exists_repo_relative=lambda path: path == "README.md",
            repo_readable_evidence_file=lambda path: path == "README.md",
        ),
    )

    serialized = json.dumps(actions, ensure_ascii=False, sort_keys=True)
    assert "ia_carmine/runtime/heap_gate/provider_context.py" not in serialized
    assert actions[0]["tool"] == "repo_read"
    assert actions[0]["arguments"] == {"paths": ["README.md"], "max_chars": 1200}


def test_candidate_actions_from_evidence_uses_docs_and_code_from_listed_paths() -> None:
    actions = candidate_actions_from_evidence(
        "describe project",
        [],
        [{"path": ".", "paths_preview": ["README.md", "app.py"]}],
        [],
        False,
        **_candidate_action_deps(),
    )

    assert actions[0]["arguments"] == {"paths": ["README.md"], "max_chars": 1200}
    assert actions[1]["arguments"] == {"path": "README.md", "max_chars": 800}
    assert actions[2]["arguments"] == {"path": "app.py", "max_chars": 800}


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
