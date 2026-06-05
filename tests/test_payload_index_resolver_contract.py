from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from vulkan_bridge.application.payload_index_resolver import resolve_payload_index  # noqa: E402


def test_payload_index_resolves_priority_content() -> None:
    result = resolve_payload_index(
        {
            "payload_index_for_30b": {
                "concrete_results": [
                    {"primary_location": "priority_evidence_for_30b.items[0].content"}
                ]
            },
            "priority_evidence_for_30b": {"items": [{"content": "# README\n"}]},
        }
    )

    assert result["ok"] is True
    assert result["resolved"][0]["path"] == "priority_evidence_for_30b.items[0].content"
    assert result["unresolved"] == []
    assert result["empty_targets"] == []


def test_payload_index_resolves_tool_context_json_string_artifact() -> None:
    result = resolve_payload_index(
        {
            "payload_index_for_30b": {
                "concrete_results": [
                    {
                        "full_context_location": (
                            "tool_context_for_30b.artifacts[0].artifact.unified_diff"
                        )
                    }
                ]
            },
            "tool_context_for_30b": json.dumps(
                {
                    "artifacts": [
                        {"artifact": {"unified_diff": "--- a/x\n+++ b/x\n"}}
                    ]
                }
            ),
        }
    )

    assert result["ok"] is True
    assert result["resolved"][0]["path"] == (
        "tool_context_for_30b.artifacts[0].artifact.unified_diff"
    )


def test_payload_index_rejects_missing_target() -> None:
    result = resolve_payload_index(
        {
            "payload_index_for_30b": {
                "concrete_results": [
                    {"primary_location": "priority_evidence_for_30b.items[1].content"}
                ]
            },
            "priority_evidence_for_30b": {"items": [{"content": "# README\n"}]},
        }
    )

    assert result["ok"] is False
    assert result["unresolved"][0]["path"] == "priority_evidence_for_30b.items[1].content"


def test_payload_index_rejects_empty_target() -> None:
    result = resolve_payload_index(
        {
            "payload_index_for_30b": {
                "concrete_results": [
                    {"primary_location": "priority_evidence_for_30b.items[0].content"}
                ]
            },
            "priority_evidence_for_30b": {"items": [{"content": ""}]},
        }
    )

    assert result["ok"] is False
    assert result["empty_targets"][0]["path"] == "priority_evidence_for_30b.items[0].content"
