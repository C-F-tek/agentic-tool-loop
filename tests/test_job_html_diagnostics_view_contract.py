from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker import job_html  # noqa: E402


def test_ia_view_keeps_new_diagnostics_in_light_payload(monkeypatch, tmp_path: Path) -> None:
    events = [
        {
            "time": "t1",
            "step": 1,
            "event_type": "planner_decision",
            "message": "Decision: terminal_search_files",
            "payload": {
                "action": "tool",
                "tool": "terminal_search_files",
                "arguments": {"query": "needle"},
                "native_tool_call": True,
            },
        },
        {
            "time": "t2",
            "step": 1,
            "event_type": "planner_decision_rejected",
            "message": "validator rejected",
            "payload": {
                "ok": False,
                "guard_type": "validator_rejection",
                "reason": "repo_read_path_not_from_prior_file_evidence",
                "runtime_debug_packet": {
                    "schema": "runtime_debug_packet.v1",
                    "phase": "VALIDATE_DECISION",
                    "step": 1,
                    "validator_result": {
                        "ok": False,
                        "violations": ["repo_read_path_not_from_prior_file_evidence"],
                    },
                    "evidence_coverage": {
                        "coverage_score": 0.42,
                        "coverage_score_ready": False,
                        "final_ready": False,
                    },
                    "required_next_progress_model": {"kind": "candidate_hint"},
                    "candidate_next_actions_count": 1,
                    "rejected_candidate_actions_count": 0,
                },
            },
        },
        {
            "time": "t3",
            "step": 1,
            "event_type": "tool_result",
            "message": "search result",
            "payload": {
                "ok": True,
                "tool": "terminal_search_files",
                "search_quality": {
                    "schema": "search_quality.v1",
                    "quality": "partial",
                    "must_retry": True,
                    "reason": "search incomplete",
                    "count": 1,
                    "truncated": False,
                    "search_complete": False,
                    "unreadable_files": 1,
                    "diagnostic_only": True,
                },
                "command_execution_policy": {
                    "schema": "command_execution_policy.v1",
                    "allowed": True,
                    "command_class": "readonly",
                    "reason": "readonly command allowed by diagnostic policy",
                    "cwd_under_repo": True,
                    "side_effect_scope": "repo_local",
                    "consent_required": False,
                    "diagnostic_only": True,
                },
            },
        },
    ]

    monkeypatch.setattr(job_html, "agent_job_root", lambda _job_id: tmp_path)
    monkeypatch.setattr(
        job_html,
        "load_agent_job_state",
        lambda _job_id: {
            "job_id": "job-ui",
            "status": "running_agentic",
            "goal": "ui diagnostics",
            "current_step": 1,
            "workspace": str(tmp_path),
        },
    )
    monkeypatch.setattr(job_html, "read_agent_events", lambda _job_id, _limit=5000: list(events))

    payload = job_html.agent_job_ia_view_payload("job-ui", include_heavy=False)
    step = payload["steps"][0]
    tool_result = step["history_tool_result_fed_back_to_planner"]

    assert tool_result["search_quality"]["schema"] == "search_quality.v1"
    assert tool_result["command_execution_policy"]["schema"] == "command_execution_policy.v1"


def test_ia_view_html_groups_diagnostics_without_validator_duplication(monkeypatch, tmp_path: Path) -> None:
    events = [
        {
            "time": "t1",
            "step": 1,
            "event_type": "planner_decision",
            "message": "Decision: terminal_search_files",
            "payload": {"action": "tool", "tool": "terminal_search_files", "native_tool_call": True},
        },
        {
            "time": "t2",
            "step": 1,
            "event_type": "planner_decision_rejected",
            "message": "validator rejected",
            "payload": {
                "ok": False,
                "guard_type": "validator_rejection",
                "runtime_debug_packet": {
                    "schema": "runtime_debug_packet.v1",
                    "phase": "VALIDATE_DECISION",
                    "step": 1,
                    "validator_result": {"ok": False, "violations": ["bad_path"]},
                    "evidence_coverage": {"coverage_score": 0.2, "final_ready": False},
                    "required_next_progress_model": {"kind": "candidate_hint"},
                    "candidate_next_actions_count": 1,
                },
            },
        },
        {
            "time": "t3",
            "step": 1,
            "event_type": "tool_result",
            "message": "search result",
            "payload": {
                "ok": True,
                "tool": "terminal_search_files",
                "search_quality": {"quality": "partial", "must_retry": True, "reason": "incomplete"},
                "command_execution_policy": {"command_class": "readonly", "allowed": True},
            },
        },
    ]

    monkeypatch.setattr(job_html, "agent_job_root", lambda _job_id: tmp_path)
    monkeypatch.setattr(
        job_html,
        "load_agent_job_state",
        lambda _job_id: {
            "job_id": "job-ui",
            "status": "running_agentic",
            "goal": "ui diagnostics",
            "current_step": 1,
            "workspace": str(tmp_path),
        },
    )
    monkeypatch.setattr(job_html, "read_agent_events", lambda _job_id, _limit=5000: list(events))

    html = job_html.agent_job_ia_view_html("job-ui")

    assert "Diagnostics Summary" in html
    assert "Validator Guard / Rejection (compact)" in html
    assert "runtime_debug_available" in html
    assert "Runtime Debug Packet" in html
    assert "search_quality" in html
    assert "command_policy" in html
    assert "History/Tool Result Fed Back To Planner" in html
    assert "runtime_debug_packet" not in html
