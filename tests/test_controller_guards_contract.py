from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.controller.guards import (  # noqa: E402
    controller_guard_count,
    controller_guard_rejection_signature,
    controller_guard_rejection_signature_count,
    recoverable_planner_block,
)


def _signature_key(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def test_controller_guard_count_matches_summary_or_reason() -> None:
    history = [
        {"tool_result": {"tool": "controller_guard", "summary": "native tool call required"}},
        {"decision": {"reason": "native tool call required"}, "tool_result": {"tool": "controller_guard"}},
        {"tool_result": {"tool": "repo_read", "summary": "native tool call required"}},
    ]

    assert controller_guard_count(history, "native tool") == 2


def test_controller_guard_rejection_signature_keeps_only_relevant_decision_fields() -> None:
    signature = controller_guard_rejection_signature(
        {"violations": ["native_tool_not_in_turn_surface", 123]},
        {"action": "tool", "tool": "repo_read", "arguments": {"path": "a.py"}, "raw": "ignored"},
    )

    assert signature == {
        "violations": ["native_tool_not_in_turn_surface", "123"],
        "rejected_decision": {"action": "tool", "tool": "repo_read", "arguments": {"path": "a.py"}},
    }


def test_controller_guard_rejection_signature_count_uses_stored_or_derived_signature() -> None:
    signature = controller_guard_rejection_signature(
        {"violations": ["same"]},
        {"action": "tool", "tool": "repo_read", "arguments": {"path": "a.py"}},
    )
    history = [
        {"tool_result": {"tool": "controller_guard", "invalid_decision_signature": signature}},
        {"tool_result": {
            "tool": "controller_guard",
            "violations": ["same"],
            "rejected_decision": {"action": "tool", "tool": "repo_read", "arguments": {"path": "a.py"}},
        }},
        {"tool_result": {"tool": "controller_guard", "violations": ["other"]}},
    ]

    assert controller_guard_rejection_signature_count(
        history,
        signature,
        invalid_decision_signature_key=_signature_key,
    ) == 2


def test_recoverable_planner_block_detects_known_degenerate_markers() -> None:
    assert recoverable_planner_block({"reason": "planner stream degenerate output"})
    assert recoverable_planner_block({"raw_planner_text_preview": "<|endoftext|>"})
    assert not recoverable_planner_block({"reason": "semantic code product violation"})
