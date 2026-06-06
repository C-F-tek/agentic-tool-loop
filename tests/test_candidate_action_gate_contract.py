from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.tool_surface.action_proof_ledger import attach_action_proof  # noqa: E402
from aicarmine_broker.application.tool_surface.candidate_action_gate import (  # noqa: E402
    candidate_rejection_reason,
    gate_candidate_actions,
)


def test_candidate_gate_keeps_proof_positive_repo_read() -> None:
    action = attach_action_proof(
        {"tool": "repo_read", "arguments": {"paths": ["README.md"]}},
        source="test",
        path_exists=True,
        path_readable=True,
        under_scope=True,
        validator_admissible=True,
    )

    gate = gate_candidate_actions([action])

    assert gate["candidate_next_actions"] == [action]
    assert gate["rejected_candidate_actions"] == []
    assert gate["diagnostic_only"] is True


def test_candidate_gate_rejects_missing_path_candidate() -> None:
    action = attach_action_proof(
        {"tool": "repo_read", "arguments": {"paths": ["missing.py"]}},
        source="test",
        path_exists=False,
        path_readable=False,
        under_scope=True,
        validator_admissible=False,
    )

    gate = gate_candidate_actions([action])

    assert gate["candidate_next_actions"] == []
    assert gate["rejected_candidate_actions"][0]["rejection_reason"] == "candidate_path_not_existing"
    assert gate["rejected_candidate_actions"][0]["diagnostic_only"] is True


def test_candidate_gate_rejects_out_of_scope_candidate() -> None:
    action = attach_action_proof(
        {"tool": "repo_read", "arguments": {"paths": ["other/file.py"]}},
        source="test",
        path_exists=True,
        path_readable=True,
        under_scope=False,
        validator_admissible=True,
    )

    assert candidate_rejection_reason(action) == "candidate_path_out_of_scope"


def test_candidate_gate_keeps_non_path_candidate_with_source_proof() -> None:
    action = attach_action_proof(
        {"tool": "runtime_sqlite_memory_search", "arguments": {"query": "planner"}},
        source="test",
    )

    gate = gate_candidate_actions([action])

    assert gate["candidate_next_actions"] == [action]
    assert gate["rejected_candidate_actions"] == []


def test_candidate_gate_keeps_scratchpad_build_state_target_file_metadata() -> None:
    action = attach_action_proof(
        {
            "tool": "planner_scratchpad_write",
            "arguments": {
                "kind": "code_product_build_state",
                "target_file": "ia_carmine/x.py",
                "text": "{}",
            },
        },
        source="test",
    )

    gate = gate_candidate_actions([action])

    assert gate["candidate_next_actions"] == [action]
    assert gate["rejected_candidate_actions"] == []


def test_candidate_gate_still_rejects_repo_propose_without_target_path_proof() -> None:
    action = attach_action_proof(
        {
            "tool": "repo_propose_code_edit",
            "arguments": {
                "target_file": "ia_carmine/x.py",
                "edit_kind": "unified_diff",
                "unified_diff": "--- a/ia_carmine/x.py\n+++ b/ia_carmine/x.py\n",
            },
        },
        source="test",
    )

    assert candidate_rejection_reason(action) == "candidate_path_not_existing"


def test_candidate_gate_rejects_missing_validator_admissibility_for_repo_read() -> None:
    action = attach_action_proof(
        {"tool": "repo_read", "arguments": {"paths": ["README.md"]}},
        source="test",
        path_exists=True,
        path_readable=True,
        under_scope=True,
        validator_admissible=False,
    )

    assert candidate_rejection_reason(action) == "candidate_not_validator_admissible"


def test_candidate_gate_keeps_validation_tool_with_existing_non_evidence_path() -> None:
    action = attach_action_proof(
        {"tool": "repo_ruff_check", "arguments": {"paths": ["Tools/check.py"]}},
        source="test",
        path_exists=True,
        path_readable=False,
        under_scope=True,
    )

    gate = gate_candidate_actions([action])

    assert candidate_rejection_reason(action) == ""
    assert gate["candidate_next_actions"] == [action]
    assert gate["rejected_candidate_actions"] == []


def test_candidate_gate_keeps_repo_write_file_create_target_under_scope() -> None:
    action = attach_action_proof(
        {
            "tool": "repo_write_file",
            "arguments": {
                "path": "macro-runtime-test.txt",
                "content": "macro runtime payload test\n",
                "overwrite": True,
            },
        },
        source="test",
        path_exists=False,
        path_readable=True,
        under_scope=True,
    )

    gate = gate_candidate_actions([action])

    assert candidate_rejection_reason(action) == ""
    assert gate["candidate_next_actions"] == [action]
    assert gate["rejected_candidate_actions"] == []
