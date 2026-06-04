from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.available_tools_prompt import (  # noqa: E402
    available_tools_window_pack,
)


def test_available_tools_window_pack_stores_full_manifest_and_summarizes_tools(tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def store_prompt_text_window(root: Path, **kwargs: Any) -> dict[str, Any]:
        calls.append({"root": root, **kwargs})
        return {
            "document_id": "tools-doc",
            "window_end": 250,
            "has_more_after": True,
        }

    payload = available_tools_window_pack(
        tmp_path,
        goal="analyze",
        available_tools=[
            {"name": "repo_read", "transport": "message.tool_calls", "required": ["path"]},
            {"name": "repo_tree"},
            "bad",
        ],
        window_chars=500,
        reason="over budget",
        store_prompt_text_window=store_prompt_text_window,
    )

    assert calls[0]["root"] == tmp_path
    assert calls[0]["section"] == "available_tools"
    assert json.loads(calls[0]["text"])[0]["name"] == "repo_read"
    assert calls[0]["metadata"] == {
        "kind": "available_tools_manifest",
        "format": "json",
        "reason": "over budget",
    }
    assert payload["schema"] == "planner_available_tools_window.v1"
    assert payload["tool_count"] == 2
    assert payload["tool_names"] == ["repo_read", "repo_tree"]
    assert payload["summary"][0] == {
        "name": "repo_read",
        "transport": "message.tool_calls",
        "required": ["path"],
    }
    assert payload["planner_can_request_more"]["arguments"] == {
        "kind": "prompt_context_window",
        "document_id": "tools-doc",
        "offset": 250,
        "max_chars": 500,
    }


def test_available_tools_window_pack_marks_truncated_summary(tmp_path: Path) -> None:
    def store_prompt_text_window(root: Path, **kwargs: Any) -> dict[str, Any]:
        return {"document_id": "tools-doc", "has_more_after": False}

    payload = available_tools_window_pack(
        tmp_path,
        goal="analyze",
        available_tools=[{"name": f"tool_{idx}"} for idx in range(82)],
        window_chars=500,
        reason="over budget",
        store_prompt_text_window=store_prompt_text_window,
    )

    assert len(payload["summary"]) == 80
    assert payload["summary_truncated"] is True
    assert payload["summary_omitted_count"] == 2
