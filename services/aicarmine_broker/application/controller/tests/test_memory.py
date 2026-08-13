"""Tests for controller-owned SQLite memory helpers."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _get_module():
    """Import controller/memory.py properly using importlib."""
    import importlib.util
    import sys

    _controller_dir = Path(__file__).resolve().parent
    _module_name = "controller_memory_test"
    _spec = importlib.util.spec_from_file_location(
        _module_name, _controller_dir / ".." / "memory.py"
    )
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_module_name] = _module
    _spec.loader.exec_module(_module)
    return _module


_m = _get_module()
_clip_memory_text = _m._clip_memory_text
_memory_text_diagnostics = _m._memory_text_diagnostics
_controller_memory_lesson_raw_text = _m._controller_memory_lesson_raw_text
controller_memory_lesson_text = _m.controller_memory_lesson_text
write_controller_memory_lesson = _m.write_controller_memory_lesson
_loop_turn_memory_raw_text = _m._loop_turn_memory_raw_text
loop_turn_memory_text = _m.loop_turn_memory_text
write_loop_turn_memory = _m.write_loop_turn_memory
CONTROLLER_MEMORY_LESSON_TEXT_LIMIT = _m.CONTROLLER_MEMORY_LESSON_TEXT_LIMIT
LOOP_TURN_MEMORY_TEXT_LIMIT = _m.LOOP_TURN_MEMORY_TEXT_LIMIT


class TestClipMemoryText:
    """Tests for _clip_memory_text."""

    def test_returns_string(self):
        result = _clip_memory_text("hello", limit=100)
        assert isinstance(result, str)

    def test_no_clip_when_short(self):
        result = _clip_memory_text("short text", limit=100)
        assert result == "short text"

    def test_clips_when_long(self):
        long_text = "x" * 200
        result = _clip_memory_text(long_text, limit=100)
        assert len(result) < len(long_text)
        assert "...[truncated" in result

    def test_handles_none_input(self):
        result = _clip_memory_text(None, limit=100)
        assert result == ""

    def test_handles_empty_string(self):
        result = _clip_memory_text("", limit=100)
        assert result == ""

    def test_respects_limit_with_suffix(self):
        text = "x" * 500
        result = _clip_memory_text(text, limit=50)
        # Total length should be <= limit (including suffix)
        assert len(result) <= 50

    def test_truncation_count_correct(self):
        text = "x" * 200
        result = _clip_memory_text(text, limit=100)
        assert "truncated 100 chars" in result


class TestMemoryTextDiagnostics:
    """Tests for _memory_text_diagnostics."""

    def test_returns_tuple(self):
        clipped, metadata = _memory_text_diagnostics("test", limit=100)
        assert isinstance(clipped, str)
        assert isinstance(metadata, dict)

    def test_clipped_text(self):
        clipped, _ = _memory_text_diagnostics("short", limit=100)
        assert clipped == "short"

    def test_metadata_keys(self):
        _, metadata = _memory_text_diagnostics("test", limit=100)
        assert "text_chars_before_clip" in metadata
        assert "text_truncated" in metadata
        assert "text_limit" in metadata

    def test_text_truncated_false_when_short(self):
        _, metadata = _memory_text_diagnostics("short", limit=100)
        assert metadata["text_truncated"] is False

    def test_text_truncated_true_when_long(self):
        _, metadata = _memory_text_diagnostics("x" * 200, limit=100)
        assert metadata["text_truncated"] is True

    def test_text_limit_in_metadata(self):
        _, metadata = _memory_text_diagnostics("test", limit=50)
        assert metadata["text_limit"] == 50


class TestControllerMemoryLessonRawText:
    """Tests for _controller_memory_lesson_raw_text."""

    def test_basic_output(self):
        job_id = "test-job-123"
        state = {"goal": "fix bug in auth"}
        status = "completed"
        final_summary = "Fixed the issue"
        result = {"history": [], "blocked_by": None}
        contract = {}
        target_key = "auth_fix"

        text = _controller_memory_lesson_raw_text(
            job_id, state, status, final_summary, result, contract, target_key
        )

        assert "job=test-job-123" in text
        assert "target=auth_fix" in text
        assert "status=completed" in text
        assert "goal=" in text
        assert "final_gate=" in text
        assert "history_count=0" in text

    def test_includes_successful_reads(self):
        job_id = "test-job"
        state = {"goal": "test goal"}
        status = "done"
        final_summary = "summary"
        result = {"history": []}
        contract = {
            "successful_repo_read_paths": [
                "src/main.py",
                "src/utils.py",
            ]
        }
        target_key = "test"

        text = _controller_memory_lesson_raw_text(
            job_id, state, status, final_summary, result, contract, target_key
        )

        assert "successful_reads=" in text
        assert "main.py" in text

    def test_includes_listed_paths(self):
        job_id = "test-job"
        state = {"goal": "test"}
        status = "done"
        final_summary = "summary"
        result = {"history": []}
        contract = {
            "repo_list_files_evidence": [
                {"path": "src/file1.py"},
                {"path": "src/file2.py"},
            ]
        }
        target_key = "test"

        text = _controller_memory_lesson_raw_text(
            job_id, state, status, final_summary, result, contract, target_key
        )

        assert "listed_paths=" in text

    def test_includes_last_rejection(self):
        job_id = "test-job"
        state = {"goal": "test"}
        status = "done"
        final_summary = "summary"
        result = {"history": []}
        contract = {
            "validation_rejections_tail": [
                {"summary": "File not found"},
                {"summary": "Permission denied"},
            ]
        }
        target_key = "test"

        text = _controller_memory_lesson_raw_text(
            job_id, state, status, final_summary, result, contract, target_key
        )

        assert "do_not_repeat_error=" in text
        assert "Permission denied" in text

    def test_includes_blocker(self):
        job_id = "test-job"
        state = {"goal": "test"}
        status = "blocked"
        final_summary = "summary"
        result = {"history": [], "blocked_tool": "git_push"}
        contract = {}
        target_key = "test"

        text = _controller_memory_lesson_raw_text(
            job_id, state, status, final_summary, result, contract, target_key
        )

        assert "blocker=" in text
        assert "git_push" in text

    def test_includes_correct_next(self):
        job_id = "test-job"
        state = {"goal": "test"}
        status = "done"
        final_summary = "Next step: refactor"
        result = {"history": []}
        contract = {}
        target_key = "test"

        text = _controller_memory_lesson_raw_text(
            job_id, state, status, final_summary, result, contract, target_key
        )

        assert "correct_next=" in text
        assert "refactor" in text

    def test_truncates_goal(self):
        job_id = "test-job"
        state = {"goal": "x" * 500}
        status = "done"
        final_summary = "summary"
        result = {"history": []}
        contract = {}
        target_key = "test"

        text = _controller_memory_lesson_raw_text(
            job_id, state, status, final_summary, result, contract, target_key
        )

        # Goal should be truncated to 240 chars
        goal_part = [line for line in text.split("\n") if line.startswith("goal=")][0]
        assert len(goal_part) <= 247  # "goal=" + 240


class TestControllerMemoryLessonText:
    """Tests for controller_memory_lesson_text."""

    def test_returns_string(self):
        result = controller_memory_lesson_text(
            job_id="test",
            state={"goal": "test"},
            status="done",
            final_summary="summary",
            result={"history": []},
            contract={},
            target_key="test",
        )
        assert isinstance(result, str)

    def test_applies_limit(self):
        result = controller_memory_lesson_text(
            job_id="test",
            state={"goal": "x" * 1000},
            status="done",
            final_summary="x" * 1000,
            result={"history": []},
            contract={},
            target_key="test",
        )
        assert len(result) <= CONTROLLER_MEMORY_LESSON_TEXT_LIMIT


class TestWriteControllerMemoryLesson:
    """Tests for write_controller_memory_lesson."""

    def test_successful_write(self):
        job_id = "test-job"
        state = {"goal": "fix bug"}
        status = "completed"
        final_summary = "Fixed it"
        result = {"history": [], "blocked_by": None}
        root = Path(__file__).parent

        mock_contract = MagicMock(return_value={
            "target_kind": "file",
            "resolved_goal_scope": "src",
            "resolved_goal_file": "main.py",
        })
        mock_target_key = MagicMock(return_value="fix_bug")
        mock_write = MagicMock(return_value={"ok": True, "path": "/tmp/test.db"})

        written = write_controller_memory_lesson(
            job_id=job_id,
            state=state,
            status=status,
            final_summary=final_summary,
            result=result,
            root=root,
            planner_evidence_contract=mock_contract,
            controller_memory_target_key=mock_target_key,
            runtime_sqlite_memory_write=mock_write,
        )

        assert written["ok"] is True
        assert written["target_key"] == "fix_bug"
        assert written["controller_owned"] is True

    def test_write_failure_handled(self):
        job_id = "test-job"
        state = {"goal": "test"}
        status = "failed"
        final_summary = "Failed"
        result = {"history": []}
        root = Path(__file__).parent

        mock_contract = MagicMock(return_value={})
        mock_target_key = MagicMock(return_value="test")
        mock_write = MagicMock(side_effect=Exception("Database error"))

        written = write_controller_memory_lesson(
            job_id=job_id,
            state=state,
            status=status,
            final_summary=final_summary,
            result=result,
            root=root,
            planner_evidence_contract=mock_contract,
            controller_memory_target_key=mock_target_key,
            runtime_sqlite_memory_write=mock_write,
        )

        assert written["ok"] is False
        assert written["tool"] == "runtime_sqlite_memory_write"
        assert written["error"] == "controller_memory_lesson_write_failed"
        assert "Database error" in written["details"]

    def test_result_not_dict_handled(self):
        job_id = "test-job"
        state = {"goal": "test"}
        status = "done"
        final_summary = "summary"
        result = "not a dict"
        root = Path(__file__).parent

        mock_contract = MagicMock(return_value={})
        mock_target_key = MagicMock(return_value="test")
        mock_write = MagicMock(return_value={"ok": True})

        written = write_controller_memory_lesson(
            job_id=job_id,
            state=state,
            status=status,
            final_summary=final_summary,
            result=result,
            root=root,
            planner_evidence_contract=mock_contract,
            controller_memory_target_key=mock_target_key,
            runtime_sqlite_memory_write=mock_write,
        )

        assert written["ok"] is True
        assert written["target_key"] == "test"


class TestLoopTurnMemoryRawText:
    """Tests for _loop_turn_memory_raw_text."""

    def test_basic_output(self):
        job_id = "test-job"
        state = {"goal": "fix bug"}
        row = {
            "step": 1,
            "substep": "plan",
            "preseed_index": None,
        }
        contract = {}
        target_key = "test"

        def clip_value(val, text_limit=180, list_limit=8):
            return str(val)[:text_limit]

        text = _loop_turn_memory_raw_text(
            job_id, state, row, contract, target_key,
            prompt_clip_value=clip_value,
        )

        assert "loop_turn_key=" in text
        assert "job=test-job" in text
        assert "step=1" in text
        assert "goal=" in text

    def test_includes_decision_info(self):
        job_id = "test-job"
        state = {"goal": "test"}
        row = {
            "step": 2,
            "substep": "execute",
            "decision": {
                "action": "edit_file",
                "tool": "aicarmine_repo_code_apply_patch",
                "reason": "Need to fix auth",
                "arguments": {"file": "main.py"},
            },
            "tool_result": {
                "tool": "apply_patch",
                "ok": True,
            },
        }
        contract = {}
        target_key = "test"

        def clip_value(val, text_limit=180, list_limit=8):
            return json.dumps(val, default=str)[:text_limit]

        text = _loop_turn_memory_raw_text(
            job_id, state, row, contract, target_key,
            prompt_clip_value=clip_value,
        )

        assert "decision_action=" in text
        assert "decision_tool=" in text
        assert "result_tool=" in text
        assert "result_ok=True" in text

    def test_includes_rejected_decision(self):
        job_id = "test-job"
        state = {"goal": "test"}
        row = {
            "step": 3,
            "substep": "reject",
            "decision": {
                "rejected_decision": {
                    "action": "bad_action",
                    "tool": "bad_tool",
                },
            },
        }
        contract = {}
        target_key = "test"

        def clip_value(val, text_limit=180, list_limit=8):
            return json.dumps(val, default=str)[:text_limit]

        text = _loop_turn_memory_raw_text(
            job_id, state, row, contract, target_key,
            prompt_clip_value=clip_value,
        )

        assert "rejected_decision=" in text

    def test_includes_successful_reads_from_contract(self):
        job_id = "test-job"
        state = {"goal": "test"}
        row = {"step": 1}
        contract = {
            "successful_repo_read_paths": ["src/main.py", "src/utils.py"],
            "required_next_progress": "Continue refactoring",
            "history_count": 5,
        }
        target_key = "test"

        def clip_value(val, text_limit=180, list_limit=8):
            return str(val)[:text_limit]

        text = _loop_turn_memory_raw_text(
            job_id, state, row, contract, target_key,
            prompt_clip_value=clip_value,
        )

        assert "successful_reads=" in text
        assert "main.py" in text
        assert "required_next_progress=" in text
        assert "history_count_after_turn=5" in text

    def test_filters_empty_lines(self):
        job_id = "test-job"
        state = {"goal": ""}
        row = {"step": 1, "substep": None, "preseed_index": None}
        contract = {}
        target_key = "test"

        def clip_value(val, text_limit=180, list_limit=8):
            return str(val)

        text = _loop_turn_memory_raw_text(
            job_id, state, row, contract, target_key,
            prompt_clip_value=clip_value,
        )

        # Lines ending with "=" (empty values) should be filtered
        lines = text.strip().split("\n")
        for line in lines:
            assert not line.endswith("=")


class TestLoopTurnMemoryText:
    """Tests for loop_turn_memory_text."""

    def test_returns_string(self):
        result = loop_turn_memory_text(
            job_id="test",
            state={"goal": "test"},
            row={"step": 1},
            contract={},
            target_key="test",
            prompt_clip_value=lambda x, **kwargs: str(x),
        )
        assert isinstance(result, str)

    def test_applies_limit(self):
        result = loop_turn_memory_text(
            job_id="test",
            state={"goal": "x" * 1000},
            row={"step": 1},
            contract={},
            target_key="test",
            prompt_clip_value=lambda x, **kwargs: str(x),
        )
        assert len(result) <= LOOP_TURN_MEMORY_TEXT_LIMIT


class TestWriteLoopTurnMemory:
    """Tests for write_loop_turn_memory."""

    def test_successful_write(self):
        job_id = "test-job"
        state = {"goal": "fix bug"}
        row = {"step": 1, "substep": "plan"}
        history = [{"tool": "read_file"}]
        root = Path(__file__).parent

        mock_contract = MagicMock(return_value={
            "target_kind": "file",
            "resolved_goal_scope": "src",
        })
        mock_target_key = MagicMock(return_value="fix_bug")
        mock_write = MagicMock(return_value={"ok": True, "path": "/tmp/test.db"})
        clip_value = lambda x, **kwargs: str(x)

        written = write_loop_turn_memory(
            job_id=job_id,
            state=state,
            row=row,
            root=root,
            history=history,
            planner_evidence_contract=mock_contract,
            controller_memory_target_key=mock_target_key,
            runtime_sqlite_memory_write=mock_write,
            prompt_clip_value=clip_value,
        )

        assert written["ok"] is True
        assert written["target_key"] == "fix_bug"
        assert written["controller_owned"] is True
        assert written["loop_turn_memory"] is True

    def test_write_failure_handled(self):
        job_id = "test-job"
        state = {"goal": "test"}
        row = {"step": 2}
        history = []
        root = Path(__file__).parent

        mock_contract = MagicMock(return_value={})
        mock_target_key = MagicMock(return_value="test")
        mock_write = MagicMock(side_effect=Exception("SQLite error"))

        written = write_loop_turn_memory(
            job_id=job_id,
            state=state,
            row=row,
            root=root,
            history=history,
            planner_evidence_contract=mock_contract,
            controller_memory_target_key=mock_target_key,
            runtime_sqlite_memory_write=mock_write,
            prompt_clip_value=lambda x, **kwargs: str(x),
        )

        assert written["ok"] is False
        assert written["tool"] == "runtime_sqlite_memory_write"
        assert written["error"] == "controller_loop_turn_memory_write_failed"

    def test_row_with_missing_keys(self):
        job_id = "test-job"
        state = {"goal": "test"}
        row = {}  # No step, substep, etc.
        history = []
        root = Path(__file__).parent

        mock_contract = MagicMock(return_value={})
        mock_target_key = MagicMock(return_value="empty_row")
        mock_write = MagicMock(return_value={"ok": True})

        written = write_loop_turn_memory(
            job_id=job_id,
            state=state,
            row=row,
            root=root,
            history=history,
            planner_evidence_contract=mock_contract,
            controller_memory_target_key=mock_target_key,
            runtime_sqlite_memory_write=mock_write,
            prompt_clip_value=lambda x, **kwargs: str(x),
        )

        assert written["ok"] is True
        assert written["target_key"] == "empty_row"

    def test_decision_not_dict_handled(self):
        job_id = "test-job"
        state = {"goal": "test"}
        row = {
            "step": 1,
            "decision": "not_a_dict",  # Should be handled gracefully
            "tool_result": "also_not_dict",
        }
        history = []
        root = Path(__file__).parent

        mock_contract = MagicMock(return_value={})
        mock_target_key = MagicMock(return_value="test")
        mock_write = MagicMock(return_value={"ok": True})

        written = write_loop_turn_memory(
            job_id=job_id,
            state=state,
            row=row,
            root=root,
            history=history,
            planner_evidence_contract=mock_contract,
            controller_memory_target_key=mock_target_key,
            runtime_sqlite_memory_write=mock_write,
            prompt_clip_value=lambda x, **kwargs: str(x),
        )

        assert written["ok"] is True
        # decision_action and decision_tool should be None when decision is not dict
        metadata = mock_write.call_args[0][0]["metadata"]
        assert metadata["decision_action"] is None
        assert metadata["decision_tool"] is None