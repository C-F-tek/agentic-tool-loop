from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.prompt_context_windows import (  # noqa: E402
    PROMPT_CONTEXT_WINDOW_TRACKING_REQUIRED_KEYS,
    bounded_prompt_context_tool_result_payload,
    compact_prompt_context_window_item,
)


def _window_item(**overrides):
    item = {
        "document_id": "doc-1",
        "section": "evidence_contract",
        "store": "job_local_sqlite",
        "metadata": {"kind": "evidence_contract"},
        "window_start": 0,
        "window_end": 100,
        "full_chars": 200,
        "window_chars": 100,
        "complete": False,
        "has_more_before": False,
        "has_more_after": True,
        "sha256": "full-hash",
        "text": "hello",
        "ignored": "drop",
    }
    item.update(overrides)
    return item


def test_compact_prompt_context_window_item_keeps_required_tracking_fields() -> None:
    payload = compact_prompt_context_window_item(_window_item())

    for key in PROMPT_CONTEXT_WINDOW_TRACKING_REQUIRED_KEYS:
        assert key in payload
    assert payload["text"] == "hello"
    assert payload["window_sha256"]
    assert "ignored" not in payload


def test_bounded_prompt_context_tool_result_payload_for_prompt_window() -> None:
    result = {
        "tool": "planner_scratchpad_read",
        "ok": True,
        "mode": "prompt_context_window",
        "items": [_window_item()],
    }

    payload = bounded_prompt_context_tool_result_payload(
        result,
        code_product_build_state_kind="code_product_build_state",
    )

    assert payload["schema"] == "planner_bounded_tool_result.v1"
    assert payload["tool"] == "planner_scratchpad_read"
    assert payload["mode"] == "prompt_context_window"
    assert payload["items"][0]["document_id"] == "doc-1"
    assert payload["planner_can_request_more"]["arguments"] == {
        "kind": "prompt_context_window",
        "document_id": "doc-1",
        "offset": 100,
        "max_chars": 100,
    }


def test_bounded_prompt_context_tool_result_payload_for_code_product_state_adds_target() -> None:
    result = {
        "tool": "planner_scratchpad_read",
        "ok": True,
        "mode": "code_product_build_state",
        "target_file": "a.py",
        "items": [_window_item()],
    }

    payload = bounded_prompt_context_tool_result_payload(
        result,
        code_product_build_state_kind="code_product_build_state",
    )

    assert payload["planner_can_request_more"]["arguments"]["kind"] == "code_product_build_state"
    assert payload["planner_can_request_more"]["arguments"]["target_file"] == "a.py"


def test_bounded_prompt_context_tool_result_payload_rejects_other_tools() -> None:
    assert bounded_prompt_context_tool_result_payload(
        {"tool": "repo_read", "ok": True},
        code_product_build_state_kind="code_product_build_state",
    ) == {}
