from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))

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
    assert "candidate_next_actions=1 recent_rejections=2" in response["evidence_guide_for_30b"]
    assert "answer_for_30b" not in response
    assert "message_for_30b" not in response
    assert "summary_for_30b" not in response
    assert "content" not in response
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


def test_wait_terminal_response_uses_openwebui_audience(tmp_path: Path, monkeypatch) -> None:
    from aicarmine_broker import job_store

    final_path = tmp_path / "final.json"
    final_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
    monkeypatch.setattr(job_store, "AGENT_JOB_ROOT", tmp_path / "jobs")
    root = job_store.agent_job_root("job-terminal")
    root.mkdir(parents=True)
    job_store.write_json(
        job_store.agent_job_state_path("job-terminal"),
        {
            "job_id": "job-terminal",
            "status": "completed",
            "goal": "done",
            "created_at": time.time(),
            "updated_at": time.time(),
            "workspace": str(root),
            "final_path": str(final_path),
            "tool_context_for_30b": {"answer_for_30b": "inline"},
            "result": {"ok": True},
        },
    )

    response = job_store.wait_for_agent_terminal("job-terminal", timeout_seconds=1)

    assert response["wait_completed"] is True
    assert response["mode"] == "agent_job_final_compact"
    assert "final_path" not in response
    assert response["operator_diagnostics"]["local_final_path"] == str(final_path)
    assert response["openwebui_usage"]["structured_context_field"] == "tool_context_for_30b"
    assert "payload_index_for_30b.concrete_results" in response["openwebui_usage"]["primary_payload_fields"]
