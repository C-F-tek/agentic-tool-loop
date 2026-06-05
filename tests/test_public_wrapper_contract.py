from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))

from aicarmine_broker.public_wrapper import deterministic_public_wrapper, fail_selector  # noqa: E402


NARRATIVE_DUPLICATES = {
    "answer_for_30b",
    "message_for_30b",
    "summary_for_30b",
    "content",
    "text",
    "final",
}


def test_deterministic_public_wrapper_uses_single_evidence_guide(tmp_path: Path) -> None:
    result = deterministic_public_wrapper(
        public_tool_name="vulkan_helper",
        original_args={"task": "analyze"},
        internal_tool="repo_status",
        internal_args={},
        dispatcher_result={
            "ok": True,
            "answer_for_30b": "legacy answer",
            "context_for_30b": {
                "answer_for_30b": "context answer",
                "summary_for_30b": "context summary",
                "artifact": {"content": "real artifact content"},
            },
        },
        selector_response={"message": {"tool_calls": [{"function": {"name": "repo_status"}}]}},
        root=tmp_path,
    )

    assert result["evidence_guide_for_30b"] == "legacy answer"
    assert NARRATIVE_DUPLICATES.isdisjoint(result)
    assert result["openwebui_usage"]["evidence_guide_field"] == "evidence_guide_for_30b"
    assert result["tool_context_for_30b"] == {"artifact": {"content": "real artifact content"}}
    assert "answer_for_30b" not in result["result"]
    assert "message_for_30b" not in result["result"]
    assert "summary_for_30b" not in result["result"]
    assert "content" not in result["result"]
    assert result["dispatcher_tool_result_l"] == result["result"]


def test_deterministic_public_wrapper_preserves_non_duplicate_content_payload(tmp_path: Path) -> None:
    result = deterministic_public_wrapper(
        public_tool_name="vulkan_helper",
        original_args={"task": "read"},
        internal_tool="repo_read",
        internal_args={},
        dispatcher_result={
            "ok": True,
            "answer_for_30b": "read completed",
            "content": "real file content",
        },
        selector_response={"message": {"tool_calls": [{"function": {"name": "repo_read"}}]}},
        root=tmp_path,
    )

    assert result["evidence_guide_for_30b"] == "read completed"
    assert "answer_for_30b" not in result["result"]
    assert result["result"]["content"] == "real file content"


def test_fail_selector_uses_single_evidence_guide(tmp_path: Path) -> None:
    result = fail_selector(
        "vulkan_helper",
        "analyze",
        {"task": "analyze"},
        tmp_path,
        {"ok": False},
    )

    assert "native internal tool_call" in result["evidence_guide_for_30b"]
    assert NARRATIVE_DUPLICATES.isdisjoint(result)
    assert result["tool_context_for_30b"]["top_level_evidence_guide_field"] == "evidence_guide_for_30b"


def test_deterministic_public_wrapper_tolerates_empty_selector_tool_calls(tmp_path: Path) -> None:
    result = deterministic_public_wrapper(
        public_tool_name="vulkan_helper",
        original_args={"task": "analyze"},
        internal_tool="repo_status",
        internal_args={},
        dispatcher_result={"ok": True, "summary": "ok"},
        selector_response={"message": {"tool_calls": []}},
        root=tmp_path,
    )

    assert result["ok"] is True
    assert result["internal_vulkan"]["selector_backend_tool_call"] is None
    assert NARRATIVE_DUPLICATES.isdisjoint(result)
