from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_openapi_exposes_only_vulkan_helper() -> None:
    from vulkan_bridge.app import app

    schema = app.openapi()

    assert set(schema["paths"]) == {"/vulkan_helper"}
    assert schema["x-aicarmine-public-surface"] == ["vulkan_helper"]
    assert "/repo_read" not in schema["paths"]
    assert "/repo_command" not in schema["paths"]


def test_openapi_exposes_only_vulkan_helper_when_registry_loader_returns_internal_tools() -> None:
    from vulkan_bridge.app import OPENWEBUI_VISIBLE_TOOL_ALIASES, app
    from vulkan_bridge.openapi_builder import build_native_helper_openapi

    schema = build_native_helper_openapi(
        app,
        visible_tool_aliases=OPENWEBUI_VISIBLE_TOOL_ALIASES,
        registry_loader=lambda: {
            "registry_hash": "demo",
            "tools": {"repo_read": {}, "repo_command": {}, "vulkan_helper": {}},
        },
    )

    assert set(schema["paths"]) == {"/vulkan_helper"}
    assert schema["x-aicarmine-public-surface"] == ["vulkan_helper"]


def test_openapi_visibility_is_not_derived_from_legacy_public_aliases() -> None:
    from vulkan_bridge import app as bridge_app

    schema = bridge_app.app.openapi()

    assert "repo_read" in bridge_app.OPENWEBUI_PUBLIC_TOOLS
    assert bridge_app.OPENWEBUI_VISIBLE_TOOL_ALIASES == ("vulkan_helper",)
    assert set(schema["paths"]) == {"/vulkan_helper"}
    assert "/helper_for_all" not in schema["paths"]
    assert "/repo_read" not in schema["paths"]


def test_openapi_exposes_only_vulkan_helper_when_registry_loader_fails() -> None:
    from vulkan_bridge.app import OPENWEBUI_VISIBLE_TOOL_ALIASES, app
    from vulkan_bridge.openapi_builder import build_native_helper_openapi

    def failing_loader() -> dict:
        raise RuntimeError("registry unavailable")

    schema = build_native_helper_openapi(
        app,
        visible_tool_aliases=OPENWEBUI_VISIBLE_TOOL_ALIASES,
        registry_loader=failing_loader,
    )

    assert set(schema["paths"]) == {"/vulkan_helper"}
    assert schema["x-aicarmine-public-surface"] == ["vulkan_helper"]
    assert "registry unavailable" in schema["x-aicarmine-registry-load-error"]


def test_vulkan_helper_response_schema_names_primary_payload_fields() -> None:
    from vulkan_bridge.openapi_builder import vulkan_helper_completed_response_schema

    properties = vulkan_helper_completed_response_schema()["properties"]

    assert "evidence_guide_for_30b" in properties
    assert "payload_index_for_30b" in properties
    assert "priority_evidence_for_30b" in properties
    assert "tool_context_for_30b" in properties
    assert "openwebui_usage" in properties
    assert "job_ok" not in properties


def test_bridge_app_does_not_patch_compactors_with_globals() -> None:
    app_source = ROOT / "services" / "vulkan_bridge" / "app.py"
    text = app_source.read_text(encoding="utf-8")

    assert "globals(" not in text
    assert "globals()[name]" not in text
    assert "globals()[_agentic_v9_name]" not in text
    assert "_agentic_v9_wrap_compactor" not in text
    assert "_agentic_v9_false_predicate" not in text


def test_bridge_has_no_dynamic_truncated_request_policy_hooks() -> None:
    app_source = ROOT / "services" / "vulkan_bridge" / "app.py"
    text = app_source.read_text(encoding="utf-8")

    assert "_should_block_truncated_user_request" not in text
    assert "_looks_like_truncated_user_request" not in text
    assert "_requires_full_user_request" not in text
    assert "truncated_request_policy" not in text


def test_agentic_v9_facade_imports_only_explicit_builders() -> None:
    from vulkan_bridge import agentic_v9

    assert "_agentic_v9_build_openwebui_response" in agentic_v9.__all__
    assert "_compact_for_openwebui" in agentic_v9.__all__
    assert "_agentic_v9_wrap_compactor" not in agentic_v9.__all__
    assert not hasattr(agentic_v9, "_agentic_v9_wrap_compactor")


def test_legacy_compactor_name_uses_explicit_openwebui_builder() -> None:
    from vulkan_bridge import app

    result = app._compact_for_openwebui(
        {
            "ok": True,
            "job_ok": True,
            "service": "vulkan_agent",
            "status": "completed",
            "tool_name": "vulkan_helper",
            "tool_context_for_30b": {"answer_for_30b": "inline"},
            "payload_index_for_30b": {},
            "priority_evidence_for_30b": {},
            "openwebui_usage": {},
        }
    )

    assert "tool_name" not in result
    assert "tool_result_for" not in result
    assert "called_by_30b" not in result
    assert "required_top_level_keys" in result
    assert "tool_name" not in result["required_top_level_keys"]
    assert "tool_result_for" not in result["required_top_level_keys"]
    assert "called_by_30b" not in result["required_top_level_keys"]
    tool_context = json.loads(result["tool_context_for_30b"])
    assert "answer_for_30b" not in tool_context
    assert result["evidence_guide_for_30b"]


def test_legacy_context_compactor_name_uses_explicit_builder() -> None:
    from vulkan_bridge import app

    result = app._agentic_v2_compact_context_for_openwebui(
        {"job": {"status": "completed", "goal": "g"}, "answer_for_30b": "inline"}
    )

    assert result["service"] == "vulkan_agent"
    tool_context = json.loads(result["tool_context_for_30b"])
    assert "answer_for_30b" not in tool_context
    assert result["evidence_guide_for_30b"]


def test_terminal_openwebui_response_sanitizes_local_pointers_but_preserves_payload() -> None:
    from vulkan_bridge import app

    local_path = r"C:\Users\carmi\AI\qwen-agent-workspace\vulkan-broker\agent-jobs\job-x\final.json"
    diff = "--- a/ia_carmine/demo.py\n+++ b/ia_carmine/demo.py\n@@ -1 +1 @@\n-old\n+new\n"

    result = app._compact_for_openwebui(
        {
            "ok": True,
            "job_ok": False,
            "service": "vulkan_agent",
            "status": "blocked_needs_attention",
            "tool_name": "vulkan_helper",
            "job_id": "job-x",
            "tool_context_for_30b": {
                "type": "agentic_loop_complete_structured_context",
                "job": {
                    "job_id": "job-x",
                    "workspace": local_path,
                    "planner_url": "http://127.0.0.1:11434",
                },
                "artifacts": [
                    {
                        "tool": "repo_propose_code_edit",
                        "artifact_path": local_path,
                        "artifact": {
                            "kind": "code_edit_proposal",
                            "target_file": "ia_carmine/demo.py",
                            "edit_kind": "unified_diff",
                            "unified_diff": diff,
                        },
                    }
                ],
            },
            "result": {
                "history": [
                    {
                        "step": 1,
                        "decision": {"tool": "repo_propose_code_edit"},
                        "tool_result": {"ok": True, "tool": "repo_propose_code_edit", "artifact_path": local_path},
                    }
                ],
                "final_path": local_path,
            },
        }
    )

    payload = json.dumps(result, ensure_ascii=False, default=str)
    tool_context = json.loads(result["tool_context_for_30b"])

    assert "evidence_guide_for_30b" in result
    assert "answer_for_30b" not in result
    assert "message_for_30b" not in result
    assert "summary_for_30b" not in result
    assert "content" not in result
    assert result["openwebui_usage"]["evidence_guide_field"] == "evidence_guide_for_30b"
    for duplicate_key in (
        "answer_for_30b",
        "message_for_30b",
        "summary_for_30b",
        "content",
        "evidence_guide_for_30b",
        "final_answer",
        "composed_answer",
    ):
        assert duplicate_key not in tool_context
    assert tool_context["artifacts"][0]["artifact"]["unified_diff"] == diff
    assert "C:\\Users\\carmi\\AI" not in payload
    assert "artifact_path" not in payload
    assert "final_path" not in payload
    assert "workspace" not in tool_context["job"]
    assert result["public_payload_lint"]["schema"] == "public_payload_lint.v1"
    assert result["public_payload_lint"]["ok"] is True


def test_nonterminal_openwebui_response_uses_single_guide_and_structured_context() -> None:
    from vulkan_bridge import app

    result = app._compact_for_openwebui(
        {
            "ok": True,
            "service": "vulkan_agent",
            "status": "running",
            "job_id": "job-running",
            "goal": "analyze repo",
            "answer_for_30b": "legacy answer",
            "message_for_30b": "legacy answer",
            "summary_for_30b": "legacy answer",
            "content": "legacy answer",
            "tool_context_for_30b": {
                "answer_for_30b": "context answer",
                "summary_for_30b": "context summary",
                "working": True,
            },
            "result": {
                "answer_for_30b": "result answer",
                "summary_for_30b": "result answer",
                "status": "running",
                "history": [{"step": 1}],
            },
        }
    )

    tool_context = json.loads(result["tool_context_for_30b"])

    assert result["evidence_guide_for_30b"]
    assert result["openwebui_usage"]["evidence_guide_field"] == "evidence_guide_for_30b"
    for duplicate_key in (
        "answer_for_30b",
        "message_for_30b",
        "summary_for_30b",
        "content",
        "text",
        "tool_observation_for_30b",
        "openwebui_tool_observation",
        "openwebui_protocol_observation",
    ):
        assert duplicate_key not in result
        assert duplicate_key not in tool_context
    assert tool_context["type"] == "agentic_loop_nonterminal_structured_context"
    assert tool_context["top_level_evidence_guide_field"] == "evidence_guide_for_30b"
    assert tool_context["working"] is True
    assert "evidence_guide_for_30b" not in tool_context.get("result_digest", {})


def test_terminal_openwebui_response_with_blocked_job_keeps_public_tool_ok_and_indexes_partial_old_new_text() -> None:
    from vulkan_bridge import app

    local_path = r"C:\Users\carmi\AI\qwen-agent-workspace\vulkan-broker\agent-jobs\job-x\final.json"

    result = app._compact_for_openwebui(
        {
            "ok": False,
            "job_ok": False,
            "service": "vulkan_agent",
            "status": "blocked_needs_attention",
            "tool_name": "vulkan_helper",
            "job_id": "job-x",
            "tool_context_for_30b": {
                "type": "agentic_loop_complete_structured_context",
                "job": {
                    "job_id": "job-x",
                    "workspace": local_path,
                },
                "partial_products_for_30b": [
                    {
                        "kind": "partial_code_product_candidate",
                        "source": "validator_rejected_repo_propose_code_edit",
                        "target_file": "ia_carmine/demo.py",
                        "edit_kind": "unified_diff",
                        "payload_is_complete": False,
                        "validator_accepted": False,
                        "old_text": "old",
                        "new_text": "new",
                    }
                ],
                "artifacts": [],
            },
            "result": {
                "status": "blocked_needs_attention",
                "final_path": local_path,
            },
        }
    )

    payload = json.dumps(result, ensure_ascii=False, default=str)
    partial = result["payload_index_for_30b"]["partial_results"][0]

    assert result["ok"] is True
    assert "job_ok" not in result
    assert result["openwebui_usage"]["internal_job_status"]["completed"] is False
    assert result["payload_index_for_30b"]["internal_job_status"]["completed"] is False
    assert partial["payload_type"] == "partial_old_text_new_text"
    assert partial["primary_location"] == {
        "old_text": "priority_evidence_for_30b.items[0].old_text",
        "new_text": "priority_evidence_for_30b.items[0].new_text",
    }
    assert "job_ok=false" not in payload
    assert "C:\\Users\\carmi\\AI" not in payload
    assert "final_path" not in payload


def test_terminal_openwebui_response_rehydrates_final_path_without_exposing_local_path(tmp_path: Path) -> None:
    from vulkan_bridge import app

    diff = "--- a/ia_carmine/demo.py\n+++ b/ia_carmine/demo.py\n@@ -1 +1 @@\n-old\n+new\n"
    final_path = tmp_path / "final.json"
    hidden_artifact_path = tmp_path / "tool-results" / "proposal.json"
    final_payload = {
        "ok": True,
        "job_ok": True,
        "service": "vulkan_agent",
        "status": "completed",
        "mode": "agent_job_final_waited_compact",
        "tool_name": "vulkan_helper",
        "tool_result_for": "vulkan_helper",
        "called_by_30b": "vulkan_helper",
        "job_id": "job-final-path",
        "goal": "produce diff",
        "tool_context_for_30b": {
            "type": "agentic_loop_complete_structured_context",
            "job": {
                "job_id": "job-final-path",
                "workspace": str(tmp_path),
            },
            "artifacts": [
                {
                    "tool": "repo_propose_code_edit",
                    "artifact_path": str(hidden_artifact_path),
                    "artifact": {
                        "kind": "code_edit_proposal",
                        "target_file": "ia_carmine/demo.py",
                        "edit_kind": "unified_diff",
                        "source_writes_performed": False,
                        "patch_application_performed": False,
                        "manual_review_required": True,
                        "unified_diff": diff,
                    },
                }
            ],
        },
        "result": {
            "final_path": str(final_path),
            "workspace": str(tmp_path),
        },
    }
    final_path.write_text(json.dumps(final_payload), encoding="utf-8")

    result = app._compact_for_openwebui(
        {
            "ok": True,
            "job_ok": True,
            "service": "vulkan_agent",
            "status": "completed",
            "tool_name": "vulkan_helper",
            "job_id": "job-final-path",
            "final_path": str(final_path),
            "result": {"compact_placeholder": True},
        }
    )

    payload = json.dumps(result, ensure_ascii=False, default=str)
    tool_context = json.loads(result["tool_context_for_30b"])
    priority_items = result["priority_evidence_for_30b"]["items"]

    assert tool_context["artifacts"][0]["artifact"]["unified_diff"] == diff
    assert priority_items[0]["kind"] == "code_edit_proposal"
    assert priority_items[0]["unified_diff"] == diff
    assert result["payload_index_for_30b"]["concrete_results"][0]["payload_type"] == "unified_diff"
    assert str(tmp_path) not in payload
    assert "artifact_path" not in payload
    assert "final_path" not in payload
    assert "workspace" not in payload
