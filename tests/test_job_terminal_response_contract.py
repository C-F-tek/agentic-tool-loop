from __future__ import annotations

from aicarmine_broker.application.job.terminal_response import (
    build_compact_terminal_response,
    build_missing_job_response,
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
        public_answer_chars=100,
    )

    assert response["ok"] is True
    assert response["job_ok"] is True
    assert response["mode"] == "agent_job_final_compact"
    assert response["answer_for_30b"] == "answer"
    assert response["message_for_30b"] == "answer"
    assert response["evidence_digest_for_30b"] == "evidence"
    assert response["next_action_for_30b"] == {"action": "done"}
    assert response["tool_context_for_30b"]["answer_for_30b"] == "context-answer"
    assert response["artifacts"] == ["final.json", "final.md", "events.ndjson"]
    assert len(response["events_tail_digest"]) == 5
    assert response["events_tail_digest"][0]["time"] == "t2"
    assert response["agent_context_for_30b"]["alias_of"] == "tool_context_for_30b"


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
        public_answer_chars=100,
    )

    assert response["job_ok"] is False
    assert response["answer_for_30b"] == "from-context"
    assert response["next_action_for_30b"] == {"action": "inspect"}
    assert response["working_memory_for_30b"] == {"k": "v"}


def test_compact_terminal_response_builds_unavailable_context_fallback() -> None:
    response = build_compact_terminal_response(
        job_id="job-x",
        state={
            "status": "failed",
            "goal": "analyze",
            "final_summary": "failed summary",
            "result": {"ok": False},
        },
        final_data={},
        events_tail=[],
        events_path="events.ndjson",
        job_url_value="http://127.0.0.1:3572/jobs/job-x",
        public_result_inline_chars=1000,
        public_summary_chars=100,
        public_answer_chars=100,
    )

    assert response["answer_for_30b"] == "failed summary"
    assert response["tool_context_for_30b"]["type"] == (
        "agentic_loop_complete_structured_context_unavailable"
    )
    assert response["tool_context_for_30b"]["answer_for_30b"] == "failed summary"
