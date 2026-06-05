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


def test_planner_validator_facade_accepts_native_repo_read_without_name_error() -> None:
    result = planner.validate_planner_decision_against_evidence(
        "analizza la repository e proponi diff concreti per il refactoring del codice",
        {
            "action": "tool",
            "tool": "repo_read",
            "arguments": {
                "path": "ia_carmine/runtime/heap_gate/provider_context.py",
                "max_chars": 6000,
            },
            "native_tool_call": True,
            "raw_native_tool_call": {
                "id": "call_test",
                "function": {
                    "name": "repo_read",
                    "arguments": {
                        "path": "ia_carmine/runtime/heap_gate/provider_context.py",
                        "max_chars": 6000,
                    },
                },
            },
        },
        [],
    )

    assert result["ok"] is True
    assert result["violations"] == []


def test_planner_validator_facade_code_product_low_signal_target_does_not_name_error() -> None:
    result = planner.validate_planner_decision_against_evidence(
        "analizza la repo e proponi diff concreti per rafctoring di codice",
        {
            "action": "tool",
            "tool": "repo_propose_code_edit",
            "arguments": {
                "target_file": "services/aicarmine_broker/planner.py",
                "edit_kind": "no_op",
                "rationale": "No concrete diff yet.",
                "no_op_rationale": "No concrete diff yet.",
            },
            "native_tool_call": True,
            "raw_native_tool_call": {
                "id": "call_test",
                "function": {
                    "name": "repo_propose_code_edit",
                    "arguments": {
                        "target_file": "services/aicarmine_broker/planner.py",
                        "edit_kind": "no_op",
                        "rationale": "No concrete diff yet.",
                        "no_op_rationale": "No concrete diff yet.",
                    },
                },
            },
        },
        [],
    )

    assert isinstance(result["violations"], list)
    assert "code_product_target_not_read:services/aicarmine_broker/planner.py" in result["violations"]
