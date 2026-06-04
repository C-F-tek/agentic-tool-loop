from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.prompt.history_messages import (  # noqa: E402
    clean_planner_history_value,
    planner_controller_guard_history_payload,
    planner_history_item_messages,
    planner_history_messages_for_ollama,
    planner_tool_result_message_payload,
)


def _store_window_stub(root: Path, **kwargs: Any) -> dict[str, Any]:
    text = str(kwargs.get("text") or "")
    max_chars = int(kwargs.get("max_chars") or 20)
    return {
        "document_id": "window-doc",
        "section": kwargs.get("section"),
        "window_start": 0,
        "window_end": min(max_chars, len(text)),
        "full_chars": len(text),
        "window_chars": min(max_chars, len(text)),
        "complete": len(text) <= max_chars,
        "has_more_before": False,
        "has_more_after": len(text) > max_chars,
        "sha256": "full",
        "window_sha256": "window",
        "text": text[:max_chars],
    }


def test_clean_planner_history_value_removes_transport_noise() -> None:
    cleaned = clean_planner_history_value({
        "artifact": "reads/a.json",
        "store": "job_local_sqlite",
        "summary": "repo_read ok artifact=reads/a.json",
        "nested": {"cache_key": "x", "path": "a.py"},
    })

    assert cleaned == {"summary": "repo_read ok", "nested": {"path": "a.py"}}


def test_planner_controller_guard_history_payload_keeps_operational_fields() -> None:
    payload = planner_controller_guard_history_payload(
        {"step": 3},
        {
            "tool": "controller_guard",
            "ok": True,
            "guard_type": "missing_code_product_candidate",
            "violations": ["missing_code_product_candidate"],
            "summary": "blocked artifact=ignored",
            "evidence_contract": {
                "required_next_progress": "call repo_propose_code_edit",
                "planner_may_choose_final": False,
                "verified_content_read_count": 2,
            },
        },
    )

    assert payload["schema"] == "planner_controller_guard_history.v1"
    assert payload["guard_type"] == "missing_code_product_candidate"
    assert payload["summary"] == "blocked"
    assert payload["required_next_progress"] == "call repo_propose_code_edit"


def test_planner_tool_result_message_payload_preserves_bounded_prompt_window() -> None:
    payload = planner_tool_result_message_payload(
        {"step": 1, "decision": {"arguments": {"document_id": "doc"}}},
        {
            "tool": "planner_scratchpad_read",
            "ok": True,
            "mode": "prompt_context_window",
            "items": [{
                "document_id": "doc",
                "section": "evidence",
                "window_start": 0,
                "window_end": 10,
                "full_chars": 20,
                "window_chars": 10,
                "complete": False,
                "has_more_before": False,
                "has_more_after": True,
                "sha256": "full",
                "text": "real text",
            }],
        },
        root=Path("."),
        goal="goal",
        window_chars=100,
        code_product_build_state_kind="code_product_build_state",
        store_prompt_text_window=_store_window_stub,
    )

    assert payload["schema"] == "planner_bounded_tool_result.v1"
    assert payload["items"][0]["document_id"] == "doc"
    assert payload["items"][0]["text"] == "real text"
    assert payload["planner_can_request_more"]["arguments"]["offset"] == 10


def test_planner_tool_result_message_payload_windows_large_payload() -> None:
    payload = planner_tool_result_message_payload(
        {"step": 5, "decision": {"tool": "repo_read"}},
        {
            "tool": "repo_read",
            "ok": True,
            "items": [{"path": "a.py", "content": "x" * 5000}],
        },
        root=Path("."),
        goal="goal",
        window_chars=80,
        code_product_build_state_kind="code_product_build_state",
        store_prompt_text_window=_store_window_stub,
    )

    assert payload["schema"] == "planner_tool_history_window.v1"
    assert payload["result_window"]["document_id"] == "window-doc"
    assert payload["planner_can_request_more"]["tool"] == "planner_scratchpad_read"


def test_planner_history_item_messages_preserves_native_tool_call_role_boundary() -> None:
    messages = planner_history_item_messages(
        {
            "step": 2,
            "decision": {
                "tool": "repo_read",
                "native_tool_call": True,
                "raw_native_tool_call": {"id": "call-1", "function": {"name": "repo_read", "arguments": "{}"}},
            },
            "tool_result": {"tool": "repo_read", "ok": True, "path": "a.py"},
        },
        root=Path("."),
        goal="goal",
        window_chars=500,
        code_product_build_state_kind="code_product_build_state",
        store_prompt_text_window=_store_window_stub,
    )

    assert messages[0]["role"] == "assistant"
    assert messages[0]["tool_calls"][0]["id"] == "call-1"
    assert messages[1]["role"] == "tool"
    assert messages[1]["tool_call_id"] == "call-1"
    assert json.loads(messages[1]["content"])["tool"] == "repo_read"


def test_planner_history_messages_for_ollama_reports_skipped_items() -> None:
    messages, report = planner_history_messages_for_ollama(
        [
            {"step": 1, "tool_result": {"tool": "repo_read", "ok": True, "path": "a.py", "content": "x" * 2000}},
            {"step": 2, "tool_result": {"tool": "repo_read", "ok": True, "path": "b.py", "content": "y" * 2000}},
        ],
        root=Path("."),
        goal="goal",
        window_chars=120,
        max_chars=260,
        native_tools_enabled=True,
        code_product_build_state_kind="code_product_build_state",
        store_prompt_text_window=_store_window_stub,
    )

    assert report["enabled"] is True
    assert report["message_count"] == len(messages)
    assert report["skipped_history_items"] >= 1
