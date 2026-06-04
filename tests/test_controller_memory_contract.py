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
