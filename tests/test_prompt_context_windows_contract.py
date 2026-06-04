from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.prompt_context_windows import (  # noqa: E402
    PROMPT_CONTEXT_WINDOW_TRACKING_REQUIRED_KEYS,
    bounded_prompt_context_tool_result_payload,
    compact_prompt_context_window_item,
    evidence_contract_continuation_action,
    forbidden_repeated_prompt_window_calls,
    planner_scratchpad_next_window_action_from_history,
    prompt_context_continuation_from_payload,
    prompt_context_continue_action,
    prompt_window_consumed_offsets,
    prompt_window_tracking_metadata_errors,
    required_working_set_continuation_action,
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
        "window_sha256": "window-hash",
        "text": "hello",
        "ignored": "drop",
    }
    item.update(overrides)
    return item


def _history_row(item=None, **result_overrides):
    result = {
        "tool": "planner_scratchpad_read",
        "ok": True,
        "mode": "prompt_context_window",
        "items": [_window_item() if item is None else item],
    }
    result.update(result_overrides)
    return {"step": 3, "tool_result": result}


def _history_tool_result(row):
    return row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}


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


def test_prompt_window_consumed_offsets_tracks_latest_window_end() -> None:
    history = [
        _history_row(_window_item(document_id="doc-1", window_end=100)),
        _history_row(_window_item(document_id="doc-1", window_end=180)),
    ]

    assert prompt_window_consumed_offsets(
        history,
        history_tool_result=_history_tool_result,
        code_product_build_state_kind="code_product_build_state",
    ) == {"doc-1": 180}


def test_prompt_window_tracking_metadata_errors_reports_missing_required_keys() -> None:
    bad_item = _window_item()
    bad_item.pop("window_sha256", None)

    errors = prompt_window_tracking_metadata_errors(
        [_history_row(bad_item), {"step": 4, "tool_result": {"tool": "planner_scratchpad_read", "ok": True, "mode": "prompt_context_window", "items": ["bad"]}}],
        history_tool_result=_history_tool_result,
        code_product_build_state_kind="code_product_build_state",
    )

    assert errors[0]["error"] == "prompt_context_window_tracking_metadata_missing"
    assert "window_sha256" in errors[0]["missing"]
    assert errors[1]["error"] == "prompt_context_window_item_not_object"


def test_prompt_context_continue_action_builds_exact_read_call() -> None:
    action = prompt_context_continue_action(
        _window_item(next_unconsumed_offset=120),
        max_chars=300,
        reason="continue",
        code_product_build_state_kind="code_product_build_state",
    )

    assert action == {
        "action": "tool",
        "tool": "planner_scratchpad_read",
        "arguments": {
            "kind": "prompt_context_window",
            "document_id": "doc-1",
            "offset": 120,
            "max_chars": 500,
        },
        "reason": "continue",
    }


def test_planner_scratchpad_next_window_action_from_history_advances_offset() -> None:
    history = [_history_row(_window_item(document_id="doc-1", window_start=0, window_end=100, full_chars=250))]

    action = planner_scratchpad_next_window_action_from_history(
        {"document_id": "doc-1", "max_chars": 80},
        history,
        history_tool_result=_history_tool_result,
        code_product_build_state_kind="code_product_build_state",
    )

    assert action["tool"] == "planner_scratchpad_read"
    assert action["arguments"]["offset"] == 100
    assert action["arguments"]["max_chars"] == 500


def test_required_working_set_continuation_action_uses_unconsumed_required_window() -> None:
    required = {"repo_reads": [{"content_window": _window_item(window_end=100, full_chars=250)}]}

    action = required_working_set_continuation_action(
        required,
        history=[],
        window_chars=900,
        history_tool_result=_history_tool_result,
        code_product_build_state_kind="code_product_build_state",
    )

    assert action["arguments"]["offset"] == 100
    assert action["arguments"]["max_chars"] == 900


def test_evidence_contract_continuation_action_uses_full_contract_window() -> None:
    action = evidence_contract_continuation_action(
        {"full_evidence_contract_window": _window_item(window_end=100, full_chars=250)},
        history=[],
        window_chars=700,
        history_tool_result=_history_tool_result,
        code_product_build_state_kind="code_product_build_state",
    )

    assert action["reason"].startswith("Continue consuming the real evidence_contract")
    assert action["arguments"]["offset"] == 100


def test_prompt_context_continuation_from_payload_prefers_required_next_tool_call() -> None:
    payload = {
        "evidence_contract": {
            "required_next_progress": "continue",
            "required_next_tool_call": {
                "tool": "planner_scratchpad_read",
                "arguments": {
                    "kind": "code_product_build_state",
                    "document_id": "doc-1",
                    "offset": 200,
                    "max_chars": 500,
                    "target_file": "a.py",
                },
            },
        }
    }

    continuation = prompt_context_continuation_from_payload(
        payload,
        code_product_build_state_kind="code_product_build_state",
    )

    assert continuation["arguments"]["kind"] == "code_product_build_state"
    assert continuation["arguments"]["target_file"] == "a.py"
    assert continuation["reason"] == "continue"


def test_forbidden_repeated_prompt_window_calls_reports_consumed_windows() -> None:
    continuation_action = {
        "tool": "planner_scratchpad_read",
        "arguments": {"kind": "prompt_context_window", "document_id": "doc-1", "offset": 100, "max_chars": 100},
    }

    calls = forbidden_repeated_prompt_window_calls(
        [_history_row(_window_item(document_id="doc-1", window_start=0, window_end=100, window_chars=100))],
        continuation_action,
        history_tool_result=_history_tool_result,
        required_next_tool_call_from_action=lambda action: {"tool": action["tool"], "arguments": action["arguments"]},
        code_product_build_state_kind="code_product_build_state",
    )

    assert calls == [{
        "tool": "planner_scratchpad_read",
        "arguments": {
            "kind": "prompt_context_window",
            "document_id": "doc-1",
            "offset": 0,
            "max_chars": 100,
        },
        "window_end": 100,
        "reason": "already_consumed",
    }]
