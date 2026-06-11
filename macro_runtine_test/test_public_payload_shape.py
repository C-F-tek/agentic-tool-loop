from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "services"
if str(SERVICES) not in sys.path:
    sys.path.insert(0, str(SERVICES))

from aicarmine_broker.application.job.terminal_response import build_compact_terminal_response
from macro_runtine_test.payload_assertions import assert_public_payload_contract
from vulkan_bridge.application.public_payload_linter import lint_public_payload


def test_openwebui_terminal_response_is_sealed_and_owner_focused() -> None:
    content = "alpha\nbeta\n"
    tool_context = {
        "type": "agentic_loop_complete_structured_context",
        "not_a_summary": True,
        "contract": {"planner_decides": True},
        "execution_contract": {"controller_validates_only": True},
        "planner": {"decisions": [{"step": 1, "tool": "repo_read"}]},
        "turn_memory": {"successful_tool_turns": [{"tool": "repo_read"}]},
        "successful_tool_turns": [{"tool": "repo_read"}],
        "failed_tool_turns": [{"tool": "repo_search", "ok": False}],
        "evidence_contract_at_finish": {"large": "diagnostic"},
        "agent_flow_diagnostics": {"debug": True},
        "executed_tools": [{"tool": "repo_read"}],
        "history": [{"step": 1}],
        "events_tail_digest": [{"event": "noise"}],
        "result_digest": {"history_tail": [{"artifact": "local_path_omitted"}]},
        "artifacts": [
            {
                "producer_step": 1,
                "tool": "repo_read",
                "ok": True,
                "artifact": {
                    "kind": "repo_read",
                    "repo_path": "README.md",
                    "line_count": 2,
                    "truncated": False,
                    "preview_only": False,
                    "content": content,
                },
            }
        ],
    }
    response = build_compact_terminal_response(
        job_id="job-unit-public-payload",
        state={
            "status": "completed",
            "goal": "Analizza README.md",
            "public_tool_name": "vulkan_helper",
            "tool_context_for_30b": tool_context,
            "result": {"ok": True, "status": "completed", "history": []},
        },
        final_data={},
        events_tail=[],
        events_path="",
        job_url_value="",
        public_result_inline_chars=2000,
        public_summary_chars=2000,
        public_answer_chars=2000,
        audience="openwebui",
        job_root=None,
    )

    expected_prefix = [
        "ok",
        "service",
        "mode",
        "job_id",
        "status",
        "required_top_level_keys",
        "evidence_guide",
        "primary_payload",
        "payload_index",
        "priority_evidence",
    ]
    assert list(response)[: len(expected_prefix)] == expected_prefix
    assert "final_summary" not in response
    assert "next_action_for_30b" not in response
    assert "operator_diagnostics" not in response
    assert "agent_context_for_30b" not in response
    assert not any("for_30b" in key for key in response)

    primary = response["primary_payload"]
    assert primary["schema"] == "openwebui.primary_payload.v1"
    assert primary["owner"] == "application.evidence"
    assert primary["request_type"] == "repo_analysis"
    assert primary["primary_location"] == "priority_evidence.items[0].content"
    assert primary["content_not_duplicated_here"] is True
    assert "content" not in primary

    parsed_context = json.loads(response["tool_context"])
    assert parsed_context["type"] == "agentic_loop_public_evidence_context"
    assert parsed_context["artifacts"][0]["artifact"]["content"] == content
    for noisy_key in (
        "contract",
        "execution_contract",
        "planner",
        "turn_memory",
        "successful_tool_turns",
        "failed_tool_turns",
        "evidence_contract_at_finish",
        "agent_flow_diagnostics",
        "executed_tools",
        "history",
        "events_tail_digest",
        "result_digest",
    ):
        assert noisy_key not in parsed_context
    assert response["priority_evidence"]["items"][0]["content"] == content

    contract = assert_public_payload_contract(response)
    assert contract["payload_ok"] is True


def test_openwebui_tool_result_payload_uses_artifact_location_without_priority_warning() -> None:
    tool_context = {
        "type": "agentic_loop_complete_structured_context",
        "not_a_summary": True,
        "artifacts": [
            {
                "producer_step": 1,
                "tool": "runtime_sqlite_memory_cleanup",
                "ok": True,
                "artifact": {
                    "kind": "tool_result",
                    "summary": "cleanup dry-run found 0 rows",
                    "count": 0,
                    "dry_run": True,
                    "items": [],
                },
            }
        ],
    }
    response = build_compact_terminal_response(
        job_id="job-unit-public-tool-result",
        state={
            "status": "completed",
            "goal": "Run cleanup dry-run",
            "public_tool_name": "vulkan_helper",
            "tool_context_for_30b": tool_context,
            "result": {"ok": True, "status": "completed", "history": []},
        },
        final_data={},
        events_tail=[],
        events_path="",
        job_url_value="",
        public_result_inline_chars=2000,
        public_summary_chars=2000,
        public_answer_chars=2000,
        audience="openwebui",
        job_root=None,
    )

    primary = response["primary_payload"]
    assert primary["owner"] == "application.tool_surface"
    assert primary["request_type"] == "tool_result"
    assert primary["primary_location"] == "tool_context.artifacts[0].artifact"
    assert "content" not in primary

    search_order = response["payload_index"]["search_order"]
    assert "primary_payload.primary_location" in search_order
    assert "tool_context.artifacts[0].artifact" in search_order
    assert "priority_evidence.items[0].content" not in search_order
    assert not any("for_30b" in key for key in response)

    lint = lint_public_payload(response, mode="block")
    assert lint["ok"] is True
    assert {
        "rule": "priority_evidence_items_have_no_concrete_payload",
        "path": "priority_evidence.items",
    } not in lint["warnings"]
