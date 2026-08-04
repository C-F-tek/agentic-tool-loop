"""Tests for aicarmine_broker.planner_core.json_io module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from aicarmine_broker.planner_core.json_io import (
    parse_strict_json_object_diagnostics,
    _parse_strict_json_object,
    _planner_stream_repetition_reason,
    _planner_stream_repeated_path_segment_reason,
)


class TestParseStrictJsonDiagnostics:
    """Test parse_strict_json_object_diagnostics function."""

    def test_empty_input(self):
        result = parse_strict_json_object_diagnostics("")
        assert result["ok"] is False
        assert result["error_type"] == "empty"

    def test_non_json_start(self):
        result = parse_strict_json_object_diagnostics("Hello world")
        assert result["ok"] is False
        assert result["error_type"] == "not_json_object"
        assert result["start_preview"] == "Hello world"

    def test_valid_simple_json(self):
        text = '{"action": "tool", "tool": "repo_read"}'
        result = parse_strict_json_object_diagnostics(text)
        assert result["ok"] is True
        assert result["decoded"]["action"] == "tool"

    def test_trailing_content(self):
        text = '{"action": "tool"} extra stuff'
        result = parse_strict_json_object_diagnostics(text)
        assert result["ok"] is False
        assert result["error_type"] == "trailing_content"

    def test_not_object_decoded(self):
        text = '[1, 2, 3]'
        result = parse_strict_json_object_diagnostics(text)
        assert result["ok"] is False
        assert result["error_type"] == "not_json_object"
        assert result["decoded_type"] == "list"

    def test_json_decode_error(self):
        text = '{"action": "tool", invalid}'
        result = parse_strict_json_object_diagnostics(text)
        assert result["ok"] is False
        assert result["error_type"] == "json_decode_error"
        assert "line" in result
        assert "column" in result


class TestParseStrictJsonObject:
    """Test _parse_strict_json_object function."""

    def test_valid_planner_decision(self):
        text = '{"action": "tool", "tool": "repo_read", "args": {"path": "/test.py"}}'
        result = _parse_strict_json_object(text)
        assert result["action"] == "tool"
        assert result["tool"] == "repo_read"

    def test_valid_final_answer(self):
        text = '{"action": "final", "final_answer": "Task complete"}'
        result = _parse_strict_json_object(text)
        assert result["action"] == "final"
        assert result["final_answer"] == "Task complete"

    def test_invalid_fenced_json(self):
        text = '```\n{"action": "tool"}\n```'
        result = _parse_strict_json_object(text)
        assert result == {}

    def test_invalid_prose_before_json(self):
        text = 'Let me analyze this...\n\n{"action": "tool"}'
        result = _parse_strict_json_object(text)
        assert result == {}

    def test_invalid_multiple_objects(self):
        text = '{"action": "tool"} {"action": "final"}'
        result = _parse_strict_json_object(text)
        assert result == {}

    def test_empty_text(self):
        result = _parse_strict_json_object("")
        assert result == {}


class TestPlannerStreamRepetitionReason:
    """Test _planner_stream_repetition_reason function."""

    def test_poisoned_tokens_halt(self):
        text = 'halted'
        reason = _planner_stream_repetition_reason(text)
        assert "dead_stop_token" in reason

    def test_role_boundary_marker(self):
        text = 'Assistant: some content'
        reason = _planner_stream_repetition_reason(text)
        assert "role_boundary_marker" in reason

    def test_repeated_line(self):
        lines = ["line1", "line1", "line1"]
        text = "\n".join(lines)
        reason = _planner_stream_repetition_reason(text)
        assert "repeated_line" in reason

    def test_no_repetition(self):
        text = '{"action": "tool", "tool": "repo_read"}'
        reason = _planner_stream_repetition_reason(text)
        assert reason == ""

    def test_long_non_json_stream(self):
        text = "x" * 9000
        reason = _planner_stream_repetition_reason(text)
        assert "long_non_json_stream_without_object" in reason


class TestPlannerStreamRepeatedPathSegment:
    """Test _planner_stream_repeated_path_segment_reason function."""

    def test_repeated_path_segment(self):
        text = 'Tools/Tools/Tools/Tools/Tools/Tools/Tools/Tools/Tools/Tools/Tools/Tools/Tools/Tools/Tools/Tools/file.py'
        reason = _planner_stream_repeated_path_segment_reason(text)
        assert "repeated_repo_path_segment_in_json" in reason

    def test_normal_path(self):
        text = '/src/main.py'
        reason = _planner_stream_repeated_path_segment_reason(text)
        assert reason == ""

    def test_short_path(self):
        text = 'a/b/c/d/e/f/g/h/i/j/k/l/m/n/o/p/q/r/s/t'
        reason = _planner_stream_repeated_path_segment_reason(text)
        assert reason == ""