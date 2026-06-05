from __future__ import annotations

from vulkan_bridge.application.response_values import (
    bridge_result_digest,
    compact_text,
    json_size,
)


def test_bridge_compact_text_points_to_inline_payload_not_local_paths() -> None:
    assert compact_text("a\r\nb\rc", 100) == "a\nb\nc"

    result = compact_text("x" * 100, 80)

    assert result.startswith("x" * 16)
    assert result.endswith("... <full result is available in inline payload fields when present>")
    assert "job_url/final_path" not in result


def test_bridge_json_size_uses_json_default_str() -> None:
    class Demo:
        def __str__(self) -> str:
            return "demo"

    assert json_size({"a": 1}) == len('{"a": 1}')
    assert json_size(Demo()) == len('"demo"')


def test_bridge_result_digest_keeps_existing_fields() -> None:
    digest = bridge_result_digest(
        {
            "ok": True,
            "job_ok": False,
            "status": "blocked_needs_attention",
            "job_id": "job-x",
            "answer_for_30b": "answer",
            "history": [{"a": 1}, {"b": 2}],
            "history_tail": [{"i": i} for i in range(7)],
            "artifacts": ["a", 1, "b"],
            "ignored": "x",
        }
    )

    assert digest == {
        "ok": True,
        "job_ok": False,
        "status": "blocked_needs_attention",
        "job_id": "job-x",
        "answer_for_30b": "answer",
        "history_count": 2,
        "history_tail": [{"i": i} for i in range(2, 7)],
        "artifacts": ["a", "b"],
    }


def test_bridge_result_digest_preview_for_non_dict() -> None:
    assert bridge_result_digest("") == {}
    assert bridge_result_digest("hello") == {"preview": "hello"}


def test_app_facades_delegate_to_response_value_helpers() -> None:
    from vulkan_bridge import app

    payload = {"status": "completed", "history": [1, 2]}

    assert app._compact_text("abc", 10) == compact_text("abc", 10)
    assert app._json_size(payload) == json_size(payload)
    assert app._bridge_result_digest(payload) == bridge_result_digest(payload)
