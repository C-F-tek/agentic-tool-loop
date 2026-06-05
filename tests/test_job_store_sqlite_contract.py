from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_write_agent_job_state_filesystem_survives_sqlite_failure(tmp_path: Path, monkeypatch) -> None:
    from aicarmine_broker import job_store

    class FailingSQLiteStore:
        def upsert_job_state(self, _state: dict, _root: Path) -> None:
            raise RuntimeError("sqlite locked")

    monkeypatch.setattr(job_store, "AGENT_JOB_ROOT", tmp_path / "jobs")
    monkeypatch.setattr(job_store, "_job_sqlite_store", lambda: FailingSQLiteStore())

    state = {
        "job_id": "job-sqlite-fail",
        "status": "running",
        "goal": "diagnose",
        "created_at": time.time(),
    }

    job_store.write_agent_job_state(state)

    state_path = job_store.agent_job_state_path("job-sqlite-fail")
    stored = json.loads(state_path.read_text(encoding="utf-8"))
    assert stored["_persistence_warning"]["sqlite_write_failed"] is True
    assert stored["_persistence_warning"]["sqlite_is_secondary_index"] is True
    assert stored["_persistence_warning"]["sqlite_failure_requires_investigation"] is True

    events_path = job_store.agent_job_events_path("job-sqlite-fail")
    event_text = events_path.read_text(encoding="utf-8")
    assert "sqlite_write_failed" in event_text
    assert "filesystem_only" in event_text


def test_write_agent_job_state_records_sqlite_warning(tmp_path: Path, monkeypatch) -> None:
    from aicarmine_broker import job_store

    class FailingSQLiteStore:
        def upsert_job_state(self, _state: dict, _root: Path) -> None:
            raise RuntimeError("database is locked")

    monkeypatch.setattr(job_store, "AGENT_JOB_ROOT", tmp_path / "jobs")
    monkeypatch.setattr(job_store, "_job_sqlite_store", lambda: FailingSQLiteStore())

    job_store.write_agent_job_state(
        {
            "job_id": "job-warning",
            "status": "running",
            "goal": "diagnose",
            "created_at": time.time(),
        }
    )

    stored = json.loads(job_store.agent_job_state_path("job-warning").read_text(encoding="utf-8"))
    warning = stored["_persistence_warning"]

    assert warning["sqlite_write_failed"] is True
    assert warning["sqlite_error_type"] == "RuntimeError"
    assert warning["filesystem_state_written"] is True
    assert warning["sqlite_is_secondary_index"] is True


def test_append_agent_event_filesystem_survives_sqlite_failure(tmp_path: Path, monkeypatch) -> None:
    from aicarmine_broker import job_store

    class FailingSQLiteStore:
        def append_event(self, _event: dict) -> None:
            raise RuntimeError("database is locked")

    monkeypatch.setattr(job_store, "AGENT_JOB_ROOT", tmp_path / "jobs")
    monkeypatch.setattr(job_store, "_job_sqlite_store", lambda: FailingSQLiteStore())

    job_store.append_agent_event("job-event-survives", "demo", "message", {"x": 1})

    events_path = job_store.agent_job_events_path("job-event-survives")
    lines = events_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert json.loads(lines[0])["event_type"] == "demo"
    assert json.loads(lines[1])["event_type"] == "sqlite_event_write_failed"


def test_append_agent_event_records_sqlite_warning_event(tmp_path: Path, monkeypatch) -> None:
    from aicarmine_broker import job_store

    class FailingSQLiteStore:
        def append_event(self, _event: dict) -> None:
            raise RuntimeError("sqlite locked")

    monkeypatch.setattr(job_store, "AGENT_JOB_ROOT", tmp_path / "jobs")
    monkeypatch.setattr(job_store, "_job_sqlite_store", lambda: FailingSQLiteStore())

    job_store.append_agent_event("job-event-fail", "demo", "message", {"x": 1})

    event_text = job_store.agent_job_events_path("job-event-fail").read_text(encoding="utf-8")
    assert "sqlite_event_write_failed" in event_text
    assert "sqlite_is_secondary_index" in event_text
    assert "sqlite_failure_requires_investigation" in event_text
    assert "filesystem_only" in event_text


def test_list_agent_jobs_merges_sqlite_and_filesystem(tmp_path: Path, monkeypatch) -> None:
    from aicarmine_broker import job_store

    class DemoSQLiteStore:
        def list_jobs(self, _limit: int) -> list[dict]:
            return [
                {
                    "job_id": "job-mixed",
                    "status": "queued",
                    "goal": "old",
                    "created_at": 1,
                    "updated_at": 1,
                    "workspace": "sqlite",
                    "final_path": "",
                    "error": "",
                },
                {
                    "job_id": "job-sqlite-only",
                    "status": "completed",
                    "goal": "sqlite only",
                    "created_at": 2,
                    "updated_at": 2,
                    "workspace": "sqlite",
                    "final_path": "",
                    "error": "",
                },
            ]

    monkeypatch.setattr(job_store, "AGENT_JOB_ROOT", tmp_path / "jobs")
    monkeypatch.setattr(job_store, "_job_sqlite_store", lambda: DemoSQLiteStore())
    fs_root = job_store.agent_job_root("job-mixed")
    fs_root.mkdir(parents=True)
    job_store.write_json(
        job_store.agent_job_state_path("job-mixed"),
        {
            "job_id": "job-mixed",
            "status": "completed",
            "goal": "filesystem current",
            "created_at": 1,
            "updated_at": 3,
            "workspace": str(fs_root),
        },
    )

    rows = job_store.list_agent_jobs(10)
    by_id = {row["job_id"]: row for row in rows}

    assert by_id["job-mixed"]["status"] == "completed"
    assert by_id["job-mixed"]["index_source"] == "mixed"
    assert by_id["job-mixed"]["sqlite_index_present"] is True
    assert by_id["job-sqlite-only"]["index_source"] == "sqlite_only"
    assert by_id["job-sqlite-only"]["filesystem_state_missing"] is True


def test_list_agent_jobs_marks_sqlite_only_rows(tmp_path: Path, monkeypatch) -> None:
    from aicarmine_broker import job_store

    class DemoSQLiteStore:
        def list_jobs(self, _limit: int) -> list[dict]:
            return [
                {
                    "job_id": "job-sqlite-only",
                    "status": "completed",
                    "goal": "sqlite only",
                    "created_at": 2,
                    "updated_at": 2,
                    "workspace": "sqlite",
                    "final_path": "",
                    "error": "",
                },
            ]

    monkeypatch.setattr(job_store, "AGENT_JOB_ROOT", tmp_path / "jobs")
    monkeypatch.setattr(job_store, "_job_sqlite_store", lambda: DemoSQLiteStore())

    rows = job_store.list_agent_jobs(10)

    assert rows[0]["job_id"] == "job-sqlite-only"
    assert rows[0]["index_source"] == "sqlite_only"
    assert rows[0]["filesystem_state_missing"] is True


def test_list_agent_jobs_filesystem_fallback_marks_sqlite_error(tmp_path: Path, monkeypatch) -> None:
    from aicarmine_broker import job_store

    class FailingSQLiteStore:
        def list_jobs(self, _limit: int) -> list[dict]:
            raise RuntimeError("sqlite locked")

    monkeypatch.setattr(job_store, "AGENT_JOB_ROOT", tmp_path / "jobs")
    monkeypatch.setattr(job_store, "_job_sqlite_store", lambda: FailingSQLiteStore())
    fs_root = job_store.agent_job_root("job-fs")
    fs_root.mkdir(parents=True)
    job_store.write_json(
        job_store.agent_job_state_path("job-fs"),
        {
            "job_id": "job-fs",
            "status": "running",
            "goal": "visible",
            "created_at": 1,
            "updated_at": 1,
            "workspace": str(fs_root),
        },
    )

    rows = job_store.list_agent_jobs(10)

    assert rows[0]["job_id"] == "job-fs"
    assert rows[0]["index_source"] == "filesystem_fallback"
    assert rows[0]["sqlite_failure_requires_investigation"] is True
    assert "sqlite locked" in rows[0]["sqlite_index_error"]


def test_list_agent_jobs_marks_filesystem_fallback_source(tmp_path: Path, monkeypatch) -> None:
    from aicarmine_broker import job_store

    class EmptySQLiteStore:
        def list_jobs(self, _limit: int) -> list[dict]:
            return []

    monkeypatch.setattr(job_store, "AGENT_JOB_ROOT", tmp_path / "jobs")
    monkeypatch.setattr(job_store, "_job_sqlite_store", lambda: EmptySQLiteStore())
    fs_root = job_store.agent_job_root("job-fs-only")
    fs_root.mkdir(parents=True)
    job_store.write_json(
        job_store.agent_job_state_path("job-fs-only"),
        {
            "job_id": "job-fs-only",
            "status": "running",
            "goal": "visible",
            "created_at": 1,
            "updated_at": 1,
            "workspace": str(fs_root),
        },
    )

    rows = job_store.list_agent_jobs(10)

    assert rows[0]["job_id"] == "job-fs-only"
    assert rows[0]["index_source"] == "filesystem_fallback"
    assert rows[0]["sqlite_index_missing"] is True


def test_job_store_survives_real_sqlite_connect_failure(tmp_path: Path, monkeypatch) -> None:
    from aicarmine_broker import job_store
    from aicarmine_broker.infrastructure import job_sqlite_store

    def failing_connect(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(job_store, "AGENT_JOB_ROOT", tmp_path / "jobs")
    monkeypatch.setattr(job_store, "AGENT_JOB_DB", tmp_path / "jobs.sqlite")
    monkeypatch.setattr(job_sqlite_store.sqlite3, "connect", failing_connect)

    job_store.write_agent_job_state(
        {
            "job_id": "job-real-sqlite-fail",
            "status": "running",
            "goal": "diagnose sqlite",
            "created_at": time.time(),
        }
    )
    job_store.append_agent_event("job-real-sqlite-fail", "demo", "message", {"x": 1})

    stored = json.loads(
        job_store.agent_job_state_path("job-real-sqlite-fail").read_text(encoding="utf-8")
    )
    events = [
        json.loads(line)
        for line in job_store.agent_job_events_path("job-real-sqlite-fail")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    rows = job_store.list_agent_jobs(10)

    assert stored["_persistence_warning"]["sqlite_error_type"] == "OperationalError"
    assert [event["event_type"] for event in events] == [
        "sqlite_write_failed",
        "demo",
        "sqlite_event_write_failed",
    ]
    assert rows[0]["job_id"] == "job-real-sqlite-fail"
    assert rows[0]["index_source"] == "filesystem_fallback"
    assert rows[0]["sqlite_failure_requires_investigation"] is True
