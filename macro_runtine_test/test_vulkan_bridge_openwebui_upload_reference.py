from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "services"
if str(SERVICES) not in sys.path:
    sys.path.insert(0, str(SERVICES))

import vulkan_bridge.app as bridge  # noqa: E402


def _sample_public_payload() -> dict[str, Any]:
    diff = "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@\n-old\n+new\n"
    return {
        "ok": True,
        "service": "vulkan_bridge",
        "mode": "agent_job_final_waited_compact",
        "job_id": "job-unit-openwebui-upload",
        "status": "completed",
        "payload_index": {
            "concrete_results": [
                {
                    "kind": "code_edit_proposal",
                    "payload_type": "unified_diff",
                    "primary_location": "priority_evidence.items[0].unified_diff",
                    "full_context_location": "tool_context.artifacts[0].artifact.unified_diff",
                    "payload_is_complete": True,
                }
            ],
            "search_order": [
                "payload_index.concrete_results",
                "priority_evidence.items[0].unified_diff",
                "tool_context.artifacts[0].artifact.unified_diff",
            ],
        },
        "priority_evidence": {
            "items": [
                {
                    "kind": "code_edit_proposal",
                    "payload_is_complete": True,
                    "unified_diff": diff,
                }
            ]
        },
        "tool_context": json.dumps(
            {
                "artifacts": [
                    {
                        "producer_step": 3,
                        "tool": "repo_propose_code_edit",
                        "ok": True,
                        "artifact": {
                            "kind": "code_edit_proposal",
                            "target_file": "app.py",
                            "edit_kind": "unified_diff",
                            "unified_diff": diff,
                        },
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
    }


def test_openwebui_upload_reference_resolves_cached_payload_with_full_diff(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(bridge, "OPENWEBUI_TOOL_PAYLOAD_CACHE_DIR", tmp_path)
    payload = _sample_public_payload()
    bridge._remember_openwebui_tool_payload(payload, alias_called="vulkan_helper")

    response = bridge._openwebui_upload_reference_response(
        {
            "request": (
                "Read the uploaded file "
                "D:/home/carmi/.config/open-webui/uploads/agent-tool-context.txt completely."
            )
        },
        alias_called="vulkan_helper",
    )

    assert response is not None
    assert response["ok"] is True
    assert response["resolved_openwebui_upload_reference"] is True
    assert response["bridge_status"] == "OPENWEBUI_UPLOAD_REFERENCE_RESOLVED"
    assert response["payload"]["priority_evidence"]["items"][0]["unified_diff"] == (
        payload["priority_evidence"]["items"][0]["unified_diff"]
    )
    concrete_values = [item["value"] for item in response["concrete_payloads"]]
    assert payload["priority_evidence"]["items"][0]["unified_diff"] in concrete_values


def test_openwebui_upload_reference_can_select_tool_context_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(bridge, "OPENWEBUI_TOOL_PAYLOAD_CACHE_DIR", tmp_path)
    payload = _sample_public_payload()
    bridge._remember_openwebui_tool_payload(payload, alias_called="vulkan_helper")

    response = bridge._openwebui_upload_reference_response(
        {
            "request": (
                "Read _file://d:/home/carmi/.config/open-webui/uploads/agent-tool-context.txt "
                "path tool_context.artifacts[0].artifact.unified_diff"
            )
        },
        alias_called="vulkan_helper",
    )

    assert response is not None
    assert response["selected_exists"] is True
    assert response["selected_path"] == "tool_context.artifacts[0].artifact.unified_diff"
    assert response["selected_value"] == payload["priority_evidence"]["items"][0]["unified_diff"]
    assert "payload" not in response


def test_handle_helper_browses_upload_reference_without_forwarding_to_3572(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(bridge, "OPENWEBUI_TOOL_PAYLOAD_CACHE_DIR", tmp_path)
    payload = _sample_public_payload()
    bridge._remember_openwebui_tool_payload(payload, alias_called="vulkan_helper")

    def fail_post_json(*args, **kwargs):
        raise AssertionError("OpenWebUI upload payload browsing must not start a 3572 job")

    monkeypatch.setattr(bridge, "_post_json", fail_post_json)

    response = bridge._handle_helper(
        bridge.VulkanHelperRequest(
            request="Leggi _file://d:/home/carmi/.config/open-webui/uploads/agent-tool-context.txt"
        ),
        alias_called="vulkan_helper",
    )

    assert response["ok"] is True
    assert response["mode"] == "openwebui_upload_payload_browser"
    assert response["payload"]["job_id"] == "job-unit-openwebui-upload"


def test_v9_terminal_fallback_materializes_code_edit_payload_without_missing_helpers() -> None:
    diff = "diff --git a/core.py b/core.py\n--- a/core.py\n+++ b/core.py\n@@\n-old\n+new\n"
    tool_context = {
        "type": "agentic_loop_complete_structured_context",
        "artifacts": [
            {
                "producer_step": 4,
                "tool": "repo_propose_code_edit",
                "ok": True,
                "artifact": {
                    "kind": "code_edit_proposal",
                    "target_file": "core.py",
                    "edit_kind": "unified_diff",
                    "payload_is_complete": True,
                    "validator_accepted": True,
                    "unified_diff": diff,
                },
            }
        ],
    }
    decoded = {
        "ok": True,
        "service": "vulkan_agent",
        "mode": "agent_job_final_waited_compact",
        "job_id": "job-unit-v9-fallback",
        "status": "completed",
        "job_ok": True,
        "final_summary": "Diff pronto.",
        "tool_context_for_30b": json.dumps(tool_context, ensure_ascii=False),
        "result": {"ok": True, "status": "completed"},
    }

    response = bridge._compact_for_openwebui(decoded)

    assert response["ok"] is True
    assert response["payload_index"]["concrete_results"][0]["primary_location"] == (
        "priority_evidence.items[0].unified_diff"
    )
    assert response["payload_index"]["concrete_results"][0]["full_context_location"] == (
        "tool_context.artifacts[0].artifact.unified_diff"
    )
    assert response["priority_evidence"]["items"][0]["unified_diff"] == diff
    parsed_context = json.loads(response["tool_context"])
    assert parsed_context["artifacts"][0]["artifact"]["unified_diff"] == diff
    assert response["materialization_report"]["ok"] is True
    assert not any("for_30b" in key for key in response)
