from __future__ import annotations

import json
import sys
from pathlib import Path

SERVICES_ROOT = Path(__file__).resolve().parent
CODEX_BRIDGE_ROOT = SERVICES_ROOT / "codex_bridge"
for import_root in (SERVICES_ROOT, CODEX_BRIDGE_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from codex_bridge import job_artifact_mcp_server  # noqa: E402


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _make_job(root: Path, job_id: str = "job-demo") -> Path:
    job_dir = root / "qwen-agent-workspace" / "vulkan-broker" / "agent-jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    _write_json(job_dir / "job.json", {"job_id": job_id, "status": "blocked", "goal": "demo", "current_step": 3})
    _write_json(job_dir / "final.json", {"status": "blocked_needs_attention", "blocked_by": "planner"})
    (job_dir / "events.ndjson").write_text(
        "\n".join(
            [
                json.dumps({"type": "planner_request_started", "step": 1}),
                json.dumps(
                    {
                        "type": "planner_decision_rejected",
                        "step": 2,
                        "message": "planner_decision_validation_failed",
                        "reason": "tool_not_in_turn_surface",
                    }
                ),
                json.dumps(
                    {
                        "event_type": "tool_start",
                        "step": 3,
                        "message": "Executing planner_scratchpad_write",
                        "payload": {
                            "tool": "planner_scratchpad_write",
                            "support_subturn": True,
                            "semantic_step": 2,
                            "arguments": {"kind": "answer_chunk", "tag": "part-1", "text": "chunk"},
                        },
                    }
                ),
                json.dumps(
                    {
                        "event_type": "tool_result",
                        "step": 3,
                        "message": "planner_scratchpad_write ok=True",
                        "payload": {
                            "tool": "planner_scratchpad_write",
                            "ok": True,
                            "support_subturn": True,
                            "semantic_step": 2,
                            "written": {"kind": "answer_chunk", "tag": "part-1"},
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_json(job_dir / "tool-results" / "step-002-repo_read.json", {"ok": True, "tool": "repo_read"})
    _write_json(
        job_dir / "tool-results" / "step-003-planner_scratchpad_write.json",
        {
            "ok": True,
            "tool": "planner_scratchpad_write",
            "support_subturn": True,
            "semantic_step": 2,
            "written": {"kind": "answer_chunk", "tag": "part-1"},
        },
    )
    _write_json(job_dir / "planner-prompts" / "step-002-planner-payload.json", {"model": "qwen", "messages": [], "tools": []})
    return job_dir


def _make_codex_loop_job(root: Path, job_id: str = "job-codex", port: int = 3579) -> Path:
    job_dir = root / "state" / "codex_bridge" / "agentic_loop_client" / f"port-{port}" / "workspace" / "agent-jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    _write_json(job_dir / "job.json", {"job_id": job_id, "status": "completed", "goal": "codex loop", "current_step": 1})
    return job_dir


def test_job_artifact_reader_lists_and_summarizes_jobs(tmp_path) -> None:
    _make_job(tmp_path)

    listed = job_artifact_mcp_server._list_jobs({"limit": 5}, tmp_path)
    summary = job_artifact_mcp_server._summary({"job_id": "job-demo"}, tmp_path)

    assert listed["ok"] is True
    assert listed["jobs"][0]["job_id"] == "job-demo"
    assert summary["ok"] is True
    assert summary["status"] == "blocked"
    assert summary["rejection_count"] == 1


def test_job_artifact_reader_finds_codex_dedicated_loop_jobs(tmp_path) -> None:
    _make_codex_loop_job(tmp_path)

    listed = job_artifact_mcp_server._list_jobs({"limit": 5}, tmp_path)

    assert listed["ok"] is True
    assert listed["jobs"][0]["job_id"] == "job-codex"
    assert "state" in listed["jobs"][0]["root"]


def test_job_artifact_reader_extracts_rejections_and_planner_payload(tmp_path) -> None:
    _make_job(tmp_path)

    rejections = job_artifact_mcp_server._rejections({"job_id": "job-demo"}, tmp_path)
    planner_payload = job_artifact_mcp_server._planner_payload({"job_id": "job-demo", "step": 2}, tmp_path)

    assert rejections["ok"] is True
    assert rejections["total_rejections"] == 1
    assert rejections["rejections"][0]["reason"] == "tool_not_in_turn_surface"
    assert planner_payload["ok"] is True
    assert planner_payload["summary"]["model"] == "qwen"


def test_job_artifact_reader_extracts_support_subturns(tmp_path) -> None:
    _make_job(tmp_path)

    subturns = job_artifact_mcp_server._subturns({"job_id": "job-demo", "tail": 10}, tmp_path)

    assert subturns["ok"] is True
    assert subturns["subturn_event_count"] == 2
    assert subturns["tool_result_count"] == 1
    assert subturns["events"][0]["tool"] == "planner_scratchpad_write"
    assert subturns["events"][0]["kind"] == "answer_chunk"
    assert subturns["counts"]["by_tool"]["planner_scratchpad_write"] == 2
