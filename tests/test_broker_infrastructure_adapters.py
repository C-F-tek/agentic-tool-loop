from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_safe_rel_path_rejects_absolute_path() -> None:
    from aicarmine_broker.infrastructure import safe_rel_path

    with pytest.raises(ValueError):
        safe_rel_path("C:/Users/carmi/AI/AGENTS.md")


def test_safe_rel_path_rejects_parent_escape() -> None:
    from aicarmine_broker.infrastructure import safe_rel_path

    with pytest.raises(ValueError):
        safe_rel_path("../AGENTS.md")


def test_filesystem_repo_reads_real_content(tmp_path: Path) -> None:
    from aicarmine_broker.infrastructure import FilesystemRepo

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("hello", encoding="utf-8")
    repo = FilesystemRepo(tmp_path)

    assert repo.exists("docs/a.md")
    assert repo.read_text("docs/a.md") == "hello"
    assert repo.list_files("docs") == ("docs/a.md",)


def test_json_file_store_roundtrip(tmp_path: Path) -> None:
    from aicarmine_broker.infrastructure import JsonFileStore

    store = JsonFileStore()
    target = tmp_path / "state" / "job.json"

    store.write(target, {"ok": True})

    assert store.read(target) == {"ok": True}


def test_agent_job_sqlite_store_roundtrip(tmp_path: Path) -> None:
    from aicarmine_broker.infrastructure import AgentJobSQLiteStore

    store = AgentJobSQLiteStore(tmp_path / "jobs.sqlite", tmp_path / "jobs")

    store.init()
    store.upsert_job_state(
        {
            "job_id": "job-a",
            "status": "running",
            "goal": "analyze",
            "created_at": 1.0,
            "updated_at": 2.0,
            "workspace": str(tmp_path / "jobs" / "job-a"),
            "final_path": "",
            "error": "",
        },
        tmp_path / "jobs" / "job-a",
    )
    store.upsert_job_state(
        {
            "job_id": "job-b",
            "status": "completed",
            "goal": "done",
            "created_at": 3.0,
            "updated_at": 4.0,
            "workspace": str(tmp_path / "jobs" / "job-b"),
            "final_path": "final.json",
            "error": "",
        },
        tmp_path / "jobs" / "job-b",
    )
    store.append_event(
        {
            "job_id": "job-b",
            "ts": 5.0,
            "step": 1,
            "event_type": "tool_result",
            "message": "ok",
            "payload": {"tool": "repo_read", "ok": True},
        }
    )

    assert [row["job_id"] for row in store.list_jobs(limit=2)] == ["job-b", "job-a"]
    with sqlite3.connect(str(tmp_path / "jobs.sqlite")) as db:
        payload_json = db.execute(
            "SELECT payload_json FROM events WHERE job_id = ?",
            ("job-b",),
        ).fetchone()[0]
    assert json.loads(payload_json) == {"tool": "repo_read", "ok": True}


def test_executable_resolver_prefers_active_venv(tmp_path: Path) -> None:
    from aicarmine_broker.infrastructure import ExecutableResolver

    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    python = scripts / "python.exe"
    python.write_text("", encoding="utf-8")
    tool = scripts / "demo.exe"
    tool.write_text("", encoding="utf-8")

    resolver = ExecutableResolver(active_python=python)

    assert resolver.resolve("demo") == str(tool.resolve(strict=False))


def test_command_runner_returns_returncode_stdout_stderr(tmp_path: Path) -> None:
    from aicarmine_broker.infrastructure import SubprocessCommandRunner

    runner = SubprocessCommandRunner()
    result = runner.run(
        (sys.executable, "-c", "print('AIC_OK')"),
        cwd=tmp_path,
        timeout_seconds=10,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "AIC_OK"
    assert result.stderr == ""
