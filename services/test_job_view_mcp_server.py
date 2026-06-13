from __future__ import annotations

import json
import sys
import time
from pathlib import Path

SERVICES_ROOT = Path(__file__).resolve().parent
CODEX_BRIDGE_ROOT = SERVICES_ROOT / "codex_bridge"
for import_root in (SERVICES_ROOT, CODEX_BRIDGE_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from codex_bridge import job_view_mcp_server  # noqa: E402


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _make_job(root: Path, job_id: str = "job-demo") -> Path:
    job_dir = root / "qwen-agent-workspace" / "vulkan-broker" / "agent-jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    now = time.time()
    _write_json(
        job_dir / "job.json",
        {
            "job_id": job_id,
            "status": "completed",
            "goal": "demo job view",
            "current_step": 1,
            "workspace": str(job_dir),
            "created_at": now,
            "updated_at": now,
            "final_summary": "done",
        },
    )
    _write_json(
        job_dir / "final.json",
        {
            "ok": True,
            "status": "completed",
            "tool_context_for_30b": {"repo_read": {"ok": True, "content": "demo"}},
        },
    )
    events = [
        {"event_type": "planner_request_started", "step": 1, "message": "start", "payload": {"planner_model": "qwen"}},
        {"event_type": "planner_decision", "step": 1, "message": "decision", "payload": {"action": "final"}},
        {"event_type": "tool_result", "step": 1, "message": "tool", "payload": {"tool": "repo_read", "ok": True}},
    ]
    (job_dir / "events.ndjson").write_text(
        "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
        encoding="utf-8",
    )
    (job_dir / "planner-stream").mkdir(exist_ok=True)
    (job_dir / "planner-stream" / "step-001.content.txt").write_text("final answer", encoding="utf-8")
    return job_dir


def _set_job_env(monkeypatch, root: Path) -> None:
    workspace = root / "qwen-agent-workspace" / "vulkan-broker"
    job_root = workspace / "agent-jobs"
    monkeypatch.setenv("AICARMINE_CODEX_MCP_REPO_ROOT", str(root))
    monkeypatch.setenv("AICARMINE_LAB_REPO", str(root))
    monkeypatch.setenv("AICARMINE_VULKAN_WORKSPACE", str(workspace))
    monkeypatch.setenv("AICARMINE_AGENT_JOB_ROOT", str(job_root))
    monkeypatch.setenv("AICARMINE_AGENT_JOB_DB", str(job_root / "agent_jobs.sqlite3"))


def test_job_view_lists_views_and_renders_dashboard(monkeypatch, tmp_path) -> None:
    _set_job_env(monkeypatch, tmp_path)
    _make_job(tmp_path)

    views = job_view_mcp_server._list_views({}, tmp_path)
    rendered = job_view_mcp_server._render(
        {
            "view": "job_dashboard",
            "job_id": "job-demo",
            "include_html": True,
            "include_outline": True,
            "max_chars": 20000,
        },
        tmp_path,
    )

    assert views["ok"] is True
    assert any(view["name"] == "ia_view" for view in views["views"])
    assert rendered["ok"] is True
    assert rendered["mode"] == "local_renderer_no_http"
    assert "Job job-demo" in rendered["html"]
    assert rendered["outline"]["title"] == "AI-Carmine Agent Job job-demo"
    assert rendered["outline"]["counts"]["links"] >= 1


def test_job_view_payload_outline_links_and_validate(monkeypatch, tmp_path) -> None:
    _set_job_env(monkeypatch, tmp_path)
    _make_job(tmp_path)

    payload = job_view_mcp_server._ia_payload({"job_id": "job-demo", "include_heavy": False}, tmp_path)
    outline = job_view_mcp_server._outline({"view": "ia_view", "job_id": "job-demo"}, tmp_path)
    links = job_view_mcp_server._links({"view": "ia_view", "job_id": "job-demo"}, tmp_path)
    validation = job_view_mcp_server._validate_html({"view": "ia_view", "job_id": "job-demo"}, tmp_path)

    assert payload["ok"] is True
    assert payload["payload"]["read_only"] is True
    assert payload["payload"]["mutation_check"]["event_count_changed"] is False
    assert outline["ok"] is True
    assert outline["outline"]["counts"]["details"] >= 1
    assert links["ok"] is True
    assert any("/jobs/job-demo" in link["href"] for link in links["links"])
    assert validation["ok"] is True
    assert validation["validation"]["has_html_tag"] is True
    assert validation["validation"]["warnings"] == []
