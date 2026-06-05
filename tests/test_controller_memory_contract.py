from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.controller.memory import (  # noqa: E402
    controller_memory_lesson_text,
    loop_turn_memory_text,
    write_controller_memory_lesson,
    write_loop_turn_memory,
)


def test_controller_memory_lesson_text_includes_operational_evidence() -> None:
    text = controller_memory_lesson_text(
        "job-1",
        {"goal": "analizza repo"},
        "blocked_needs_attention",
        "next step",
        {"history": [{"step": 1}], "blocked_by": "validator"},
        {
            "successful_repo_read_paths": ["a.py"],
            "repo_list_files_evidence": [{"path": "services"}],
            "validation_rejections_tail": [{"summary": "do not repeat"}],
            "finalization_contract": {"reason": "need evidence"},
        },
        "repo",
    )

    assert "job=job-1" in text
    assert "target=repo" in text
    assert "successful_reads=a.py" in text
    assert "listed_paths=services" in text
    assert "do_not_repeat_error=do not repeat" in text
    assert "blocker=validator" in text


def test_write_controller_memory_lesson_writes_expected_record(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def memory_write(payload: dict[str, Any], root: Path) -> dict[str, Any]:
        captured["payload"] = payload
        captured["root"] = root
        return {"ok": True, "tool": "runtime_sqlite_memory_write"}

    written = write_controller_memory_lesson(
        "job-1",
        {"goal": "goal"},
        "completed",
        "summary",
        {"history": []},
        tmp_path,
        planner_evidence_contract=lambda _goal, _history: {"target_kind": "repo"},
        controller_memory_target_key=lambda _goal, _contract: "repo",
        runtime_sqlite_memory_write=memory_write,
    )

    assert written["ok"] is True
    assert written["target_key"] == "repo"
    assert written["controller_owned"] is True
    assert captured["root"] == tmp_path
    assert captured["payload"]["kind"] == "controller_job_lesson"
    assert captured["payload"]["metadata"]["job_id"] == "job-1"


def test_loop_turn_memory_text_clips_decision_payload() -> None:
    text = loop_turn_memory_text(
        "job-1",
        {"goal": "goal"},
        {
            "step": 2,
            "decision": {"action": "tool", "tool": "repo_read", "arguments": {"path": "a.py"}},
            "tool_result": {"tool": "repo_read", "ok": True, "summary": "read ok"},
        },
        {"successful_repo_read_paths": ["a.py"], "required_next_progress": "final", "history_count": 3},
        "repo",
        prompt_clip_value=lambda value, **_kwargs: value,
    )

    assert "loop_turn_key=job-1:2:" in text
    assert "decision_tool=repo_read" in text
    assert '"path": "a.py"' in text
    assert "result_ok=True" in text
    assert "required_next_progress=final" in text


def test_write_loop_turn_memory_marks_controller_loop_record(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def memory_write(payload: dict[str, Any], root: Path) -> dict[str, Any]:
        captured["payload"] = payload
        captured["root"] = root
        return {"ok": True}

    written = write_loop_turn_memory(
        "job-1",
        {"goal": "goal"},
        {"step": 3, "decision": {"action": "tool", "tool": "repo_tree"}, "tool_result": {"tool": "repo_tree", "ok": True}},
        tmp_path,
        [],
        planner_evidence_contract=lambda _goal, _history: {},
        controller_memory_target_key=lambda _goal, _contract: "repo",
        runtime_sqlite_memory_write=memory_write,
        prompt_clip_value=lambda value, **_kwargs: value,
    )

    assert written["target_key"] == "repo"
    assert written["controller_owned"] is True
    assert written["loop_turn_memory"] is True
    assert captured["payload"]["kind"] == "controller_loop_turn"
    assert captured["payload"]["metadata"]["decision_tool"] == "repo_tree"


def test_write_loop_turn_memory_returns_typed_error_on_memory_failure(tmp_path: Path) -> None:
    def memory_write(_payload: dict[str, Any], _root: Path) -> dict[str, Any]:
        raise RuntimeError("db closed")

    written = write_loop_turn_memory(
        "job-1",
        {"goal": "goal"},
        {"step": 3},
        tmp_path,
        [],
        planner_evidence_contract=lambda _goal, _history: {},
        controller_memory_target_key=lambda _goal, _contract: "repo",
        runtime_sqlite_memory_write=memory_write,
        prompt_clip_value=lambda value, **_kwargs: value,
    )

    assert written["ok"] is False
    assert written["error"] == "controller_loop_turn_memory_write_failed"
    assert written["error_type"] == "RuntimeError"
    assert written["controller_owned"] is True
    assert written["loop_turn_memory"] is True


def test_planner_memory_surface_separates_availability_from_query_records(tmp_path: Path) -> None:
    from aicarmine_broker.memory_tools import planner_memory_surface

    db_path = tmp_path / "memory.sqlite"
    surface = planner_memory_surface({"db": str(db_path), "goal": "analizza repo"}, tmp_path)

    assert surface["available"] is True
    assert surface["memory_feature_available"] is True
    assert surface["memory_query_ok"] is True
    assert surface["memory_records_available"] is False
    assert surface["available_meaning"] == "feature_available_not_query_success"
    assert surface["record_count"] == 0


def test_planner_memory_surface_query_ok_false_on_sqlite_error(tmp_path: Path, monkeypatch) -> None:
    import aicarmine_broker.memory_tools as memory_tools

    def fake_search(args: dict[str, object], root: Path) -> dict[str, object]:
        return {
            "ok": False,
            "tool": "runtime_sqlite_memory_search",
            "count": 0,
            "items": [],
            "error": "sqlite_memory_search_error",
            "details": "database is locked",
        }

    monkeypatch.setattr(memory_tools, "runtime_sqlite_memory_search", fake_search)

    surface = memory_tools.planner_memory_surface(
        {"db": str(tmp_path / "memory.sqlite"), "goal": "analizza repo", "target_key": "repo"},
        tmp_path,
    )

    assert surface["memory_feature_available"] is True
    assert surface["memory_query_ok"] is False
    assert surface["memory_records_available"] is False
    assert surface["memory_query_error"] == "sqlite_memory_search_error"
    assert surface["memory_query_details"] == "database is locked"


def test_runtime_sqlite_memory_cleanup_apply_requires_consent(tmp_path: Path) -> None:
    from aicarmine_broker.memory_tools import (
        runtime_sqlite_memory_cleanup,
        runtime_sqlite_memory_write,
    )

    db_path = tmp_path / "memory.sqlite"
    runtime_sqlite_memory_write(
        {"db": str(db_path), "text": "cleanup target", "kind": "test_cleanup"},
        tmp_path,
    )

    blocked = runtime_sqlite_memory_cleanup(
        {
            "db": str(db_path),
            "apply": True,
            "expired_only": False,
            "older_than_days": 0,
            "kind": "test_cleanup",
        },
        tmp_path,
        allow_command=True,
        user_consent="",
    )

    assert blocked["ok"] is False
    assert blocked["needs_consent"] is True
    assert blocked["error"] == "memory_cleanup_requires_user_consent"
    assert blocked["would_delete_count"] == 1

    applied = runtime_sqlite_memory_cleanup(
        {
            "db": str(db_path),
            "apply": True,
            "expired_only": False,
            "older_than_days": 0,
            "kind": "test_cleanup",
        },
        tmp_path,
        allow_command=True,
        user_consent="confirm",
    )

    assert applied["ok"] is True
    assert applied["dry_run"] is False
    assert applied["count"] == 1


def test_memory_cleanup_requires_filter_even_with_consent(tmp_path: Path) -> None:
    from aicarmine_broker.memory_tools import (
        runtime_sqlite_memory_cleanup,
        runtime_sqlite_memory_write,
    )

    db_path = tmp_path / "memory.sqlite"
    runtime_sqlite_memory_write(
        {"db": str(db_path), "text": "cleanup target", "kind": "test_cleanup"},
        tmp_path,
    )

    result = runtime_sqlite_memory_cleanup(
        {
            "db": str(db_path),
            "apply": True,
            "expired_only": False,
        },
        tmp_path,
        allow_command=True,
        user_consent="confirm",
    )

    assert result["ok"] is False
    assert result["error"] == "cleanup_requires_filter"
    assert result["dry_run"] is False


def test_memory_cleanup_apply_requires_command_permission_even_with_consent(tmp_path: Path) -> None:
    from aicarmine_broker.memory_tools import (
        runtime_sqlite_memory_cleanup,
        runtime_sqlite_memory_write,
    )

    db_path = tmp_path / "memory.sqlite"
    runtime_sqlite_memory_write(
        {"db": str(db_path), "text": "cleanup target", "kind": "permission_cleanup"},
        tmp_path,
    )

    blocked = runtime_sqlite_memory_cleanup(
        {
            "db": str(db_path),
            "apply": True,
            "expired_only": False,
            "older_than_days": 0,
            "kind": "permission_cleanup",
        },
        tmp_path,
        allow_command=False,
        user_consent="confirm",
    )

    assert blocked["ok"] is False
    assert blocked["needs_consent"] is True
    assert blocked["error"] == "memory_cleanup_requires_command_permission"
    assert blocked["would_delete_count"] == 1

    dry_run = runtime_sqlite_memory_cleanup(
        {
            "db": str(db_path),
            "apply": False,
            "expired_only": False,
            "older_than_days": 0,
            "kind": "permission_cleanup",
        },
        tmp_path,
        allow_command=False,
        user_consent="",
    )

    assert dry_run["ok"] is True
    assert dry_run["dry_run"] is True
    assert dry_run["count"] == 1


def test_dispatcher_passes_user_consent_to_memory_cleanup(tmp_path: Path) -> None:
    from aicarmine_broker.application.tool_surface.dispatcher import (
        DispatchRequest,
        build_default_dispatcher,
    )
    from aicarmine_broker.memory_tools import runtime_sqlite_memory_write

    db_path = tmp_path / "memory.sqlite"
    runtime_sqlite_memory_write(
        {"db": str(db_path), "text": "cleanup target", "kind": "dispatch_cleanup"},
        tmp_path,
    )
    dispatcher = build_default_dispatcher()

    blocked = dispatcher.dispatch(
        DispatchRequest(
            name="runtime_sqlite_memory_cleanup",
            args={
                "db": str(db_path),
                "apply": True,
                "expired_only": False,
                "older_than_days": 0,
                "kind": "dispatch_cleanup",
            },
            root=tmp_path,
            allow_command=True,
            user_consent="",
        )
    )
    assert blocked["error"] == "memory_cleanup_requires_user_consent"

    applied = dispatcher.dispatch(
        DispatchRequest(
            name="runtime_sqlite_memory_cleanup",
            args={
                "db": str(db_path),
                "apply": True,
                "expired_only": False,
                "older_than_days": 0,
                "kind": "dispatch_cleanup",
            },
            root=tmp_path,
            allow_command=True,
            user_consent="confirm",
        )
    )
    assert applied["ok"] is True
    assert applied["count"] == 1
