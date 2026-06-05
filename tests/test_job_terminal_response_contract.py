from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))

from aicarmine_broker.application.job.terminal_response import (
    build_compact_terminal_response,
    build_missing_job_response,
    verify_local_final_path,
)


def test_missing_job_response_shape() -> None:
    assert build_missing_job_response("job-x") == {
        "ok": False,
        "service": "vulkan_agent",
        "tool_name": "vulkan_helper",
        "error": "job_not_found",
        "job_id": "job-x",
    }


def test_compact_terminal_response_uses_state_tool_context_first() -> None:
    response = build_compact_terminal_response(
        job_id="job-x",
        state={
            "status": "completed",
            "public_tool_name": "vulkan_helper",
            "goal": "analyze",
            "final_path": "final.json",
            "final_markdown_path": "final.md",
            "final_summary": "summary",
            "answer_for_30b": "answer",
            "next_action_for_30b": {"action": "done"},
            "tool_context_for_30b": {
                "answer_for_30b": "context-answer",
                "evidence_digest_for_30b": "evidence",
            },
            "result": {"ok": True, "history": [{"tool": "repo_read"}]},
        },
        final_data={"answer_for_30b": "final-answer"},
        events_tail=[
            {
                "time": f"t{i}",
                "step": i,
                "event_type": "event",
                "message": "msg",
                "payload": {"tool": "repo_read", "ok": True},
            }
            for i in range(7)
        ],
        events_path="events.ndjson",
        job_url_value="http://127.0.0.1:3572/jobs/job-x",
        public_result_inline_chars=1000,
        public_summary_chars=100,
        public_answer_chars=1000,
    )

    assert response["ok"] is True
    assert response["job_ok"] is True
    assert response["mode"] == "agent_job_final_compact"
    assert "answer_for_30b" not in response
    assert "message_for_30b" not in response
    assert "summary_for_30b" not in response
    assert "answer" in response["evidence_guide_for_30b"]
    assert response["evidence_digest_for_30b"] == "evidence"
    assert response["next_action_for_30b"] == {"action": "done"}
    assert "answer_for_30b" not in response["tool_context_for_30b"]
    assert response["materialization_report"]["owner"] == "3572_broker"
    assert "payload_index_for_30b" in response
    assert "priority_evidence_for_30b" in response
    assert response["artifacts"] == ["final.json", "final.md", "events.ndjson"]
    assert len(response["events_tail_digest"]) == 5
    assert response["events_tail_digest"][0]["time"] == "t2"
    assert response["agent_context_for_30b"]["alias_of"] == "tool_context_for_30b"


def test_operator_terminal_response_contains_verified_local_paths(tmp_path: Path) -> None:
    final_path = tmp_path / "final.json"
    final_path.write_text(json.dumps({"ok": True, "answer": "inline"}), encoding="utf-8")
    final_markdown = tmp_path / "final.md"
    final_markdown.write_text("done", encoding="utf-8")
    events_path = tmp_path / "events.ndjson"

    response = build_compact_terminal_response(
        job_id="job-operator",
        state={
            "status": "completed",
            "public_tool_name": "vulkan_helper",
            "goal": "analyze",
            "final_path": str(final_path),
            "final_markdown_path": str(final_markdown),
            "final_summary": "summary",
            "tool_context_for_30b": {"answer_for_30b": "inline answer"},
            "result": {"ok": True},
            "workspace": str(tmp_path),
        },
        final_data={},
        events_tail=[],
        events_path=str(events_path),
        job_url_value="http://127.0.0.1:3572/jobs/job-operator",
        public_result_inline_chars=1000,
        public_summary_chars=100,
        public_answer_chars=1000,
        audience="operator",
    )

    assert response["final_path"] == str(final_path)
    assert response["final_markdown_path"] == str(final_markdown)
    assert response["events_path"] == str(events_path)
    assert response["full_result_available"] is True
    assert response["final_path_verification"]["final_path_verified"] is True
    assert response["full_result_hint"] == (
        "Full result is available in final_path and was verified readable by the local runtime."
    )


def test_compact_terminal_response_uses_final_data_context_when_state_missing() -> None:
    response = build_compact_terminal_response(
        job_id="job-x",
        state={
            "status": "blocked_needs_attention",
            "public_tool_name": "vulkan_helper",
            "goal": "analyze",
            "final_summary": "",
            "result": {"status": "blocked_needs_attention"},
        },
        final_data={
            "tool_context_for_30b": {
                "answer_for_30b": "from-context",
                "next_action_for_30b": {"action": "inspect"},
            },
            "working_memory_for_30b": {"k": "v"},
        },
        events_tail=[],
        events_path="events.ndjson",
        job_url_value="http://127.0.0.1:3572/jobs/job-x",
        public_result_inline_chars=1000,
        public_summary_chars=100,
        public_answer_chars=1000,
    )

    assert response["job_ok"] is False
    assert "answer_for_30b" not in response
    assert "from-context" in response["evidence_guide_for_30b"]
    assert response["next_action_for_30b"] == {"action": "inspect"}
    assert response["working_memory_for_30b"] == {"k": "v"}


def test_compact_terminal_response_builds_structured_context_from_state_history() -> None:
    response = build_compact_terminal_response(
        job_id="job-x",
        state={
            "status": "failed",
            "goal": "analyze",
            "final_summary": "failed summary",
            "history": [
                {
                    "step": 1,
                    "tool": "repo_read",
                    "ok": True,
                    "items": [
                        {
                            "ok": True,
                            "path": "README.md",
                            "content_preview": "preview only",
                        }
                    ],
                }
            ],
            "result": {"ok": False, "status": "failed"},
        },
        final_data={},
        events_tail=[],
        events_path="events.ndjson",
        job_url_value="http://127.0.0.1:3572/jobs/job-x",
        public_result_inline_chars=1000,
        public_summary_chars=100,
        public_answer_chars=1000,
    )

    assert "tool_context_for_30b.artifacts" in response["evidence_guide_for_30b"]
    assert "failed summary" in response["evidence_guide_for_30b"]
    assert response["tool_context_for_30b"]["type"] == (
        "agentic_loop_complete_structured_context"
    )
    assert response["tool_context_for_30b"]["not_a_summary"] is True
    assert response["tool_context_for_30b"]["history_count"] == 1
    assert response["tool_context_for_30b"]["history"][0]["items"][0]["content_chars"] == len("preview only")
    assert "answer_for_30b" not in response["tool_context_for_30b"]


def test_failed_terminal_response_sanitizes_local_path_from_public_answer() -> None:
    raw = (
        r"PermissionError: [WinError 5] Accesso negato: "
        r"'C:\Users\carmi\AI\agent-jobs\job-x\.job.json.tmp' -> "
        r"'C:\Users\carmi\AI\agent-jobs\job-x\job.json'"
    )

    response = build_compact_terminal_response(
        job_id="job-x",
        state={
            "status": "failed",
            "goal": "analyze",
            "final_summary": raw,
            "result": {"ok": False, "error_type": "PermissionError"},
        },
        final_data={},
        events_tail=[],
        events_path="events.ndjson",
        job_url_value="http://127.0.0.1:3572/jobs/job-x",
        public_result_inline_chars=1000,
        public_summary_chars=1000,
        public_answer_chars=1000,
        audience="openwebui",
    )

    assert r"C:\Users\carmi" not in response["evidence_guide_for_30b"]
    assert "[local_path_omitted]" in response["evidence_guide_for_30b"]
    assert response["operator_diagnostics"]["local_events_path"] == "events.ndjson"


def test_final_path_claim_requires_absolute_existing_valid_json(tmp_path: Path) -> None:
    relative = verify_local_final_path("final.json")
    assert relative["final_path_verified"] is False
    assert relative["final_path_error"] == "not_absolute"

    final_path = tmp_path / "final.json"
    final_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
    verified = verify_local_final_path(final_path)

    assert verified["final_path_verified"] is True
    assert verified["final_path_size_bytes"] > 0
    assert len(verified["final_path_sha256"]) == 64
    assert verified["openwebui_can_read_final_path"] is False


def test_final_path_claim_requires_non_empty_file(tmp_path: Path) -> None:
    final_path = tmp_path / "final.json"
    final_path.write_text("", encoding="utf-8")

    verified = verify_local_final_path(final_path)

    assert verified["final_path_verified"] is False
    assert verified["final_path_error"] == "empty_file"
    assert verified["final_path_size_bytes"] == 0
    assert len(verified["final_path_sha256"]) == 64


def test_final_path_claim_requires_non_empty_json(tmp_path: Path) -> None:
    final_path = tmp_path / "final.json"
    final_path.write_text("{}", encoding="utf-8")

    verified = verify_local_final_path(final_path)

    assert verified["final_path_verified"] is False
    assert verified["final_path_error"] == "empty_json"
    assert verified["final_path_content_type"] == "application/json"


def test_final_path_claim_requires_valid_json_when_json_expected(tmp_path: Path) -> None:
    final_path = tmp_path / "final.json"
    final_path.write_text("{not-json", encoding="utf-8")

    verified = verify_local_final_path(final_path)

    assert verified["final_path_verified"] is False
    assert verified["final_path_error"] == "invalid_json"
    assert verified["final_path_content_type"] == "application/json"


def test_unverified_final_path_does_not_claim_full_result_available(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing-final.json"

    response = build_compact_terminal_response(
        job_id="job-missing-final",
        state={
            "status": "completed",
            "public_tool_name": "vulkan_helper",
            "goal": "analyze",
            "final_path": str(missing_path),
            "final_summary": "summary",
            "tool_context_for_30b": {"answer_for_30b": "inline answer"},
            "result": {"ok": True},
        },
        final_data={},
        events_tail=[],
        events_path=str(tmp_path / "events.ndjson"),
        job_url_value="http://127.0.0.1:3572/jobs/job-missing-final",
        public_result_inline_chars=1000,
        public_summary_chars=100,
        public_answer_chars=1000,
    )

    assert response["full_result_available"] is False
    assert response["final_path_verification"]["final_path_error"] == "missing_file"
    assert response["full_result_hint"] == (
        "final_path was expected but is not currently verified readable."
    )


def test_openwebui_terminal_response_keeps_local_paths_under_diagnostics(tmp_path: Path) -> None:
    final_path = tmp_path / "final.json"
    final_path.write_text(json.dumps({"ok": True, "answer": "inline"}), encoding="utf-8")

    response = build_compact_terminal_response(
        job_id="job-openwebui",
        state={
            "status": "completed",
            "public_tool_name": "vulkan_helper",
            "goal": "analyze",
            "final_path": str(final_path),
            "final_markdown_path": str(tmp_path / "final.md"),
            "final_summary": "summary",
            "tool_context_for_30b": {"answer_for_30b": "inline answer"},
            "result": {"ok": True},
            "workspace": str(tmp_path),
        },
        final_data={},
        events_tail=[],
        events_path=str(tmp_path / "events.ndjson"),
        job_url_value="http://127.0.0.1:3572/jobs/job-openwebui",
        public_result_inline_chars=1000,
        public_summary_chars=100,
        public_answer_chars=1000,
        audience="openwebui",
    )

    assert "final_path" not in response
    assert "events_path" not in response
    assert response["artifacts"] == []
    assert response["operator_diagnostics"]["local_final_path"] == str(final_path)
    assert response["operator_diagnostics"]["final_path_verification"]["final_path"] == str(final_path)
    assert "final_path" not in response["final_path_verification"]
    public_response = dict(response)
    public_response.pop("operator_diagnostics")
    assert str(tmp_path) not in json.dumps(public_response, ensure_ascii=False, default=str)
    assert "answer_for_30b" not in response["tool_context_for_30b"]
    assert "inline answer" in response["evidence_guide_for_30b"]
    assert "OpenWebUI cannot read local paths" in response["full_result_hint"]
    assert response["openwebui_usage"]["primary_payload_fields"] == [
        "evidence_guide_for_30b",
        "payload_index_for_30b.concrete_results",
        "priority_evidence_for_30b.items[0].content",
        "tool_context_for_30b.artifacts[*].artifact",
    ]


def test_openwebui_terminal_response_materializes_repo_read_content() -> None:
    response = build_compact_terminal_response(
        job_id="job-materialized",
        state={
            "status": "completed",
            "goal": "describe readme",
            "final_summary": "summary",
            "tool_context_for_30b": {
                "not_a_summary": True,
                "evidence_digest_for_30b": "repo_read README.md",
                "artifacts": [
                    {
                        "producer_step": 1,
                        "tool": "repo_read",
                        "ok": True,
                        "artifact": {
                            "kind": "repo_read",
                            "repo_path": "README.md",
                            "truncated": False,
                            "content": "# Demo\n",
                        },
                    }
                ],
            },
            "result": {"ok": True},
        },
        final_data={},
        events_tail=[],
        events_path="events.ndjson",
        job_url_value="http://127.0.0.1:3572/jobs/job-materialized",
        public_result_inline_chars=1000,
        public_summary_chars=100,
        public_answer_chars=1000,
        audience="openwebui",
    )

    priority_item = response["priority_evidence_for_30b"]["items"][0]
    index_row = response["payload_index_for_30b"]["concrete_results"][0]

    assert response["materialization_report"]["owner"] == "3572_broker"
    assert response["materialization_report"]["ok"] is True
    assert priority_item["content"] == "# Demo\n"
    assert index_row["primary_location"] == "priority_evidence_for_30b.items[0].content"
    assert "content" not in index_row
