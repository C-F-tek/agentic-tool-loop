from __future__ import annotations

from aicarmine_broker.application.job.wait_response import build_wait_timeout_response


def test_wait_timeout_response_preserves_status_and_adds_continuation() -> None:
    original = {
        "ok": True,
        "status": "running",
        "current_step": 4,
        "status_message": "reading",
        "working_memory_for_30b": {
            "candidate_next_actions": [{"tool": "repo_read"}],
            "rejections_tail": [{}, {}],
        },
    }

    response = build_wait_timeout_response(
        job_id="job-x",
        last_status=original,
        timeout_seconds=9,
        events_tail=[
            {
                "time": "t",
                "step": 1,
                "event_type": "planner_decision",
                "message": "waiting",
                "payload": {"status": "running"},
            }
        ],
    )

    assert original["status"] == "running"
    assert response["mode"] == "agent_job_wait_timeout"
    assert response["wait_completed"] is False
    assert response["wait_timeout_seconds"] == 9
    assert response["events_tail_digest"][0]["status"] == "running"
    assert "candidate_next_actions=1 recent_rejections=2" in response["message_for_30b"]
    assert response["answer_for_30b"] == response["message_for_30b"]
    assert response["next_action_for_30b"] == {
        "action": "continue_same_openwebui_context",
        "status": "running",
        "job_id": "job-x",
        "tool_call": {
            "tool_name": "vulkan_helper",
            "arguments": {"action": "status", "job_id": "job-x"},
        },
        "do_not": [
            "do_not_drop_openwebui_context",
            "do_not_treat_dashboard_url_as_only_result",
            "do_not_start_duplicate_job_for_same_request",
        ],
    }
    assert response["continuation_surface"]["call_protocol"] == {
        "action": "status",
        "job_id": "job-x",
    }
    assert response["continuation_surface"]["result_protocol"] == {
        "action": "result",
        "job_id": "job-x",
    }
