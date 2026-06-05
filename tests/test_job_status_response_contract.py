from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))

from aicarmine_broker.application.job.status_response import build_compact_status_response


def test_compact_status_response_builds_running_context() -> None:
    response = build_compact_status_response(
        job_id="job-x",
        state={
            "status": "running",
            "goal": "analyze",
            "current_step": 3,
            "status_message": "reading",
            "public_tool_name": "vulkan_helper",
            "created_at": 1.0,
            "updated_at": 2.0,
            "workspace": "workspace",
            "working_memory_for_30b": {"candidate_next_actions": []},
            "evidence_contract": {"final_allowed": False},
        },
        events=[
            {
                "time": f"t{i}",
                "step": i,
                "event_type": "event",
                "message": "msg",
                "payload": {"tool": "repo_read", "ok": True},
            }
            for i in range(12)
        ],
        job_url_value="http://127.0.0.1:3572/jobs/job-x",
    )

    assert response["mode"] == "agent_job_status"
    assert response["job_id"] == "job-x"
    assert response["status"] == "running"
    assert response["evidence_guide_for_30b"].startswith("GUIDA STATO LOOP INTERNO")
    assert "Agent job job-x status=running" in response["evidence_guide_for_30b"]
    assert "answer_for_30b" not in response
    assert "message_for_30b" not in response
    assert "summary_for_30b" not in response
    assert "content" not in response
    assert response["tool_context_for_30b"]["type"] == (
        "agentic_loop_running_structured_context"
    )
    assert response["tool_context_for_30b"]["job"]["current_step"] == 3
    assert len(response["tool_context_for_30b"]["events_tail_digest"]) == 10
    assert response["tool_context_for_30b"]["events_tail_digest"][0]["time"] == "t2"


def test_compact_status_response_preserves_existing_context_and_answer() -> None:
    response = build_compact_status_response(
        job_id="job-x",
        state={
            "status": "running",
            "goal": "analyze",
            "answer_for_30b": "existing answer",
            "tool_context_for_30b": {"type": "existing"},
            "agent_context_for_30b": {"type": "agent"},
            "structured_context_for_30b": {"type": "structured"},
            "structured_result_for_30b": {"type": "result"},
        },
        events=[],
        job_url_value="http://127.0.0.1:3572/jobs/job-x",
    )

    assert "existing answer" in response["evidence_guide_for_30b"]
    assert "answer_for_30b" not in response
    assert "message_for_30b" not in response
    assert response["tool_context_for_30b"] == {"type": "existing"}
    assert response["agent_context_for_30b"] == {"type": "agent"}
    assert response["structured_context_for_30b"] == {"type": "structured"}
    assert response["structured_result_for_30b"] == {"type": "result"}
