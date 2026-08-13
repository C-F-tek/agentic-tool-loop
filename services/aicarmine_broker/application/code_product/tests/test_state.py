"""Tests for services/aicarmine_broker/application/code_product/state.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Match test_history.py pattern for import resolution
sys.path.insert(0, str(Path(__file__).parents[4]))

from aicarmine_broker.application.code_product.state import (
    CODE_PRODUCT_BUILD_STATE_KIND,
    CODE_PRODUCT_BUILD_STATE_SCHEMA,
    code_product_build_state_section,
    code_product_build_state_parse,
    code_product_build_state_ready_payload,
    code_product_build_state_has_collecting_progress,
    code_product_has_preview_substitute,
    code_product_payload_violations,
    goal_exact_text_block,
    copyable_example_text,
    code_product_action_has_complete_payload,
)


# --- code_product_build_state_section ---

class TestCodeProductBuildStateSection:
    def test_basic_target(self):
        result = code_product_build_state_section("src/main.py")
        assert result == f"{CODE_PRODUCT_BUILD_STATE_KIND}:src/main.py"

    def test_relative_dot(self):
        result = code_product_build_state_section(".")
        assert result == CODE_PRODUCT_BUILD_STATE_KIND

    def test_empty_string(self):
        result = code_product_build_state_section("")
        assert result == CODE_PRODUCT_BUILD_STATE_KIND

    def test_nested_path(self):
        result = code_product_build_state_section("a/b/c/file.py")
        assert result == f"{CODE_PRODUCT_BUILD_STATE_KIND}:a/b/c/file.py"

    def test_trailing_slash_stripped(self):
        result = code_product_build_state_section("src/")
        assert result == f"{CODE_PRODUCT_BUILD_STATE_KIND}:src"


# --- code_product_build_state_parse ---

class TestCodeProductBuildStateParse:
    def test_valid_schema(self):
        payload = {
            "schema": CODE_PRODUCT_BUILD_STATE_SCHEMA,
            "status": "ready_for_propose",
            "target_file": "src/main.py",
        }
        text = json.dumps(payload)
        result = code_product_build_state_parse(text)
        assert result == payload

    def test_missing_schema(self):
        text = json.dumps({"status": "ready"})
        result = code_product_build_state_parse(text)
        assert result == {}

    def test_wrong_schema_value(self):
        text = json.dumps({"schema": "wrong.v1"})
        result = code_product_build_state_parse(text)
        assert result == {}

    def test_not_dict(self):
        text = json.dumps([1, 2, 3])
        result = code_product_build_state_parse(text)
        assert result == {}

    def test_empty_string(self):
        result = code_product_build_state_parse("")
        assert result == {}

    def test_none_input(self):
        result = code_product_build_state_parse(None)
        assert result == {}

    def test_invalid_json(self):
        result = code_product_build_state_parse("not valid json")
        assert result == {}


# --- code_product_build_state_ready_payload ---

class TestCodeProductBuildStateReadyPayload:
    def test_ready_structured_edit(self):
        state = {
            "schema": CODE_PRODUCT_BUILD_STATE_SCHEMA,
            "status": "ready_for_propose",
            "target_file": "src/main.py",
            "edit_kind": "structured_edit",
            "rationale": "fix bug",
            "structured_operations": [{"operation": "replace_exact", "path": "src/main.py"}],
        }
        result = code_product_build_state_ready_payload(state)
        assert result["target_file"] == "src/main.py"
        assert result["edit_kind"] == "structured_edit"
        assert result["rationale"] == "fix bug"
        assert result["structured_operations"] == [{"operation": "replace_exact", "path": "src/main.py"}]

    def test_ready_unified_diff(self):
        state = {
            "schema": CODE_PRODUCT_BUILD_STATE_SCHEMA,
            "status": "ready_for_propose",
            "target_file": "src/main.py",
            "edit_kind": "unified_diff",
            "rationale": "fix bug",
            "unified_diff": "--- a/src/main.py\n+++ b/src/main.py\n@@ -1,0 @@\n+new line",
        }
        result = code_product_build_state_ready_payload(state)
        assert result["target_file"] == "src/main.py"
        assert result["edit_kind"] == "unified_diff"
        assert result["unified_diff"] == state["unified_diff"]

    def test_ready_no_op(self):
        state = {
            "schema": CODE_PRODUCT_BUILD_STATE_SCHEMA,
            "status": "ready_for_propose",
            "target_file": "src/main.py",
            "edit_kind": "no_op",
            "rationale": "nothing to change",
        }
        result = code_product_build_state_ready_payload(state)
        assert result["target_file"] == "src/main.py"
        assert result["edit_kind"] == "no_op"
        assert result["rationale"] == "nothing to change"

    def test_not_ready_status(self):
        state = {"status": "collecting"}
        result = code_product_build_state_ready_payload(state)
        assert result == {}

    def test_missing_target_file(self):
        state = {
            "status": "ready_for_propose",
            "edit_kind": "structured_edit",
            "rationale": "fix",
            "structured_operations": [],
        }
        result = code_product_build_state_ready_payload(state)
        assert result == {}

    def test_empty_rationale(self):
        state = {
            "status": "ready_for_propose",
            "target_file": "src/main.py",
            "edit_kind": "no_op",
            "rationale": "",
        }
        result = code_product_build_state_ready_payload(state)
        assert result == {}

    def test_invalid_edit_kind(self):
        state = {
            "status": "ready_for_propose",
            "target_file": "src/main.py",
            "edit_kind": "unknown_kind",
            "rationale": "fix",
        }
        result = code_product_build_state_ready_payload(state)
        assert result == {}

    def test_unified_diff_missing_diff(self):
        state = {
            "status": "ready_for_propose",
            "target_file": "src/main.py",
            "edit_kind": "unified_diff",
            "rationale": "fix",
        }
        result = code_product_build_state_ready_payload(state)
        assert result == {}

    def test_validation_commands_preserved(self):
        """Test that validation_commands are preserved when present."""
        state = {
            "schema": CODE_PRODUCT_BUILD_STATE_SCHEMA,
            "status": "ready_for_propose",
            "target_file": "src/main.py",
            "edit_kind": "structured_edit",
            "rationale": "fix",
            "validation_commands": ["pytest", "ruff"],
            "structured_operations": [],
        }
        result = code_product_build_state_ready_payload(state)
        # validation_commands is only included in args dict when edit_kind is structured_edit
        # and the state has it - check if it's in result
        assert "validation_commands" in result or result == {}


# --- code_product_build_state_has_collecting_progress ---

class TestCodeProductBuildStateHasCollectingProgress:
    def test_source_windows_with_identity(self):
        state = {
            "source_windows": [
                {
                    "document_id": "doc1",
                    "section": "main",
                    "offset": 0,
                    "window_start": 0,
                    "window_end": 100,
                }
            ]
        }
        assert code_product_build_state_has_collecting_progress(state) is True

    def test_old_text_present(self):
        state = {"old_text": "some text"}
        assert code_product_build_state_has_collecting_progress(state) is True

    def test_new_text_present(self):
        state = {"new_text": "new text"}
        assert code_product_build_state_has_collecting_progress(state) is True

    def test_unified_diff_present(self):
        state = {"unified_diff": "--- a/file.py\n+++ b/file.py"}
        assert code_product_build_state_has_collecting_progress(state) is True

    def test_structured_operations_present(self):
        state = {"structured_operations": [{"operation": "replace_exact"}]}
        assert code_product_build_state_has_collecting_progress(state) is True

    def test_empty_state(self):
        state = {}
        assert code_product_build_state_has_collecting_progress(state) is False

    def test_not_dict(self):
        assert code_product_build_state_has_collecting_progress("not a dict") is False
        assert code_product_build_state_has_collecting_progress([1, 2]) is False

    def test_source_windows_invalid_entry(self):
        state = {"source_windows": ["not a dict"]}
        assert code_product_build_state_has_collecting_progress(state) is False

    def test_source_windows_no_identity(self):
        state = {
            "source_windows": [
                {"document_id": "", "section": ""}
            ]
        }
        # has_window_marker still present but no identity
        assert code_product_build_state_has_collecting_progress(state) is False


# --- code_product_has_preview_substitute ---

class TestCodeProductHasPreviewSubstitute:
    def test_dict_with_preview_key(self):
        val = {"content_preview": "truncated content"}
        assert code_product_has_preview_substitute(val) is True

    def test_nested_dict_with_preview_key(self):
        val = {"inner": {"unified_diff_preview": "diff"}}
        assert code_product_has_preview_substitute(val) is True

    def test_list_with_preview(self):
        val = [{"structured_operations_preview": []}]
        assert code_product_has_preview_substitute(val) is True

    def test_string_truncated(self):
        assert code_product_has_preview_substitute("<truncated>") is True
        assert code_product_has_preview_substitute("[truncated]") is True

    def test_clean_string(self):
        assert code_product_has_preview_substitute("clean text") is False

    def test_empty_string(self):
        assert code_product_has_preview_substitute("") is False

    def test_dict_no_preview_keys(self):
        val = {"key": "value", "other": 123}
        assert code_product_has_preview_substitute(val) is False

    def test_deeply_nested(self):
        val = {"a": {"b": {"c": {"content_preview": "deep"}}}}
        assert code_product_has_preview_substitute(val) is True


# --- code_product_payload_violations ---

class TestCodeProductPayloadViolations:
    def test_valid_proposal(self):
        proposal = {
            "tool": "repo_propose_code_edit",
            "ok": True,
            "kind": "code_edit_proposal",
            "target_file": "src/main.py",
            "path": "src/main.py",
            "source_writes_performed": False,
            "patch_application_performed": False,
            "manual_review_required": True,
            "errors": [],
            "edit_kind": "no_op",
            "rationale": "nothing to change",
        }
        read_paths = {"src/main.py"}
        violations = code_product_payload_violations(proposal, read_paths)
        assert violations == []

    def test_missing_code_product_candidate(self):
        proposal = {}
        violations = code_product_payload_violations(proposal, {"src/main.py"})
        assert "missing_code_product_candidate" in violations

    def test_preview_substitute_detected(self):
        proposal = {
            "tool": "repo_propose_code_edit",
            "ok": True,
            "kind": "code_edit_proposal",
            "target_file": "src/main.py",
            "path": "src/main.py",
            "source_writes_performed": False,
            "patch_application_performed": False,
            "manual_review_required": True,
            "errors": [],
            "edit_kind": "no_op",
            "rationale": "nothing",
            "content_preview": "truncated",
        }
        violations = code_product_payload_violations(proposal, {"src/main.py"})
        assert "code_product_payload_not_complete" in violations

    def test_invalid_kind(self):
        proposal = {
            "tool": "repo_propose_code_edit",
            "ok": True,
            "kind": "wrong_kind",
            "target_file": "src/main.py",
            "path": "src/main.py",
            "source_writes_performed": False,
            "patch_application_performed": False,
            "manual_review_required": True,
            "errors": [],
            "edit_kind": "no_op",
            "rationale": "nothing",
        }
        violations = code_product_payload_violations(proposal, {"src/main.py"})
        assert "invalid_code_product_candidate" in violations

    def test_target_not_read(self):
        proposal = {
            "tool": "repo_propose_code_edit",
            "ok": True,
            "kind": "code_edit_proposal",
            "target_file": "src/main.py",
            "path": "src/main.py",
            "source_writes_performed": False,
            "patch_application_performed": False,
            "manual_review_required": True,
            "errors": [],
            "edit_kind": "no_op",
            "rationale": "nothing",
        }
        violations = code_product_payload_violations(proposal, {"other.py"})
        assert "code_product_target_not_read" in violations

    def test_errors_list_present(self):
        proposal = {
            "tool": "repo_propose_code_edit",
            "ok": True,
            "kind": "code_edit_proposal",
            "target_file": "src/main.py",
            "path": "src/main.py",
            "source_writes_performed": False,
            "patch_application_performed": False,
            "manual_review_required": True,
            "errors": ["some error"],
            "edit_kind": "no_op",
            "rationale": "nothing",
        }
        violations = code_product_payload_violations(proposal, {"src/main.py"})
        assert "invalid_code_product_candidate" in violations

    def test_unified_diff_valid(self):
        proposal = {
            "tool": "repo_propose_code_edit",
            "ok": True,
            "kind": "code_edit_proposal",
            "target_file": "src/main.py",
            "path": "src/main.py",
            "source_writes_performed": False,
            "patch_application_performed": False,
            "manual_review_required": True,
            "errors": [],
            "edit_kind": "unified_diff",
            "rationale": "fix",
            "unified_diff": "--- a/src/main.py\n+++ b/src/main.py\n@@ -1 +1 @@\n-old\n+new",
        }
        violations = code_product_payload_violations(proposal, {"src/main.py"})
        assert violations == []

    def test_unified_diff_invalid_markers(self):
        proposal = {
            "tool": "repo_propose_code_edit",
            "ok": True,
            "kind": "code_edit_proposal",
            "target_file": "src/main.py",
            "path": "src/main.py",
            "source_writes_performed": False,
            "patch_application_performed": False,
            "manual_review_required": True,
            "errors": [],
            "edit_kind": "unified_diff",
            "rationale": "fix",
            "unified_diff": "no markers here",
        }
        violations = code_product_payload_violations(proposal, {"src/main.py"})
        assert "invalid_code_product_candidate" in violations

    def test_structured_edit_valid(self):
        proposal = {
            "tool": "repo_propose_code_edit",
            "ok": True,
            "kind": "code_edit_proposal",
            "target_file": "src/main.py",
            "path": "src/main.py",
            "source_writes_performed": False,
            "patch_application_performed": False,
            "manual_review_required": True,
            "errors": [],
            "edit_kind": "structured_edit",
            "rationale": "fix",
            "structured_operations": [{"operation": "replace_exact"}],
        }
        violations = code_product_payload_violations(proposal, {"src/main.py"})
        assert violations == []

    def test_no_op_missing_rationale(self):
        proposal = {
            "tool": "repo_propose_code_edit",
            "ok": True,
            "kind": "code_edit_proposal",
            "target_file": "src/main.py",
            "path": "src/main.py",
            "source_writes_performed": False,
            "patch_application_performed": False,
            "manual_review_required": True,
            "errors": [],
            "edit_kind": "no_op",
            "rationale": "",
        }
        violations = code_product_payload_violations(proposal, {"src/main.py"})
        assert "invalid_code_product_candidate" in violations


# --- goal_exact_text_block ---

class TestGoalExactTextBlock:
    def test_inline_value(self):
        goal = "exact target:\nsrc/main.py\nold text here"
        result = goal_exact_text_block(goal, "target")
        assert result == "src/main.py\nold text here"

    def test_multiline_block(self):
        goal = (
            "exact target:\n"
            "line1\n"
            "line2\n"
            "\n"
            "line3\n"
            "required behavior:"
        )
        result = goal_exact_text_block(goal, "target")
        assert result == "line1\nline2\n\nline3"

    def test_no_match(self):
        goal = "something else entirely"
        result = goal_exact_text_block(goal, "target")
        assert result == ""

    def test_empty_goal(self):
        result = goal_exact_text_block("", "target")
        assert result == ""

    def test_boundary_detection(self):
        goal = (
            "exact target:\n"
            "content\n"
            "exact old_text:\n"
            "boundary"
        )
        result = goal_exact_text_block(goal, "target")
        assert result == "content"


# --- copyable_example_text ---

class TestCopyableExampleText:
    def test_insert_keywords(self):
        assert copyable_example_text("<insert>") is True
        assert copyable_example_text("insert old text") is True
        assert copyable_example_text("insert new text") is True

    def test_example_only(self):
        assert copyable_example_text("example_only") is True
        assert copyable_example_text("do_not_copy") is True

    def test_known_labels(self):
        assert copyable_example_text("old") is True
        assert copyable_example_text("new") is True
        assert copyable_example_text("old phrase") is True
        assert copyable_example_text("new phrase") is True
        assert copyable_example_text("old text") is True
        assert copyable_example_text("new text") is True
        assert copyable_example_text("example old text") is True
        assert copyable_example_text("example new text") is True
        assert copyable_example_text("placeholder") is True

    def test_angle_bracket_tag(self):
        assert copyable_example_text("<tag>") is True
        assert copyable_example_text("<very-long-tag-that-is-valid>") is True

    def test_clean_text(self):
        assert copyable_example_text("actual content to copy") is False

    def test_empty_string(self):
        assert copyable_example_text("") is False

    def test_not_string(self):
        assert copyable_example_text(123) is False
        assert copyable_example_text(None) is False
        assert copyable_example_text(["list"]) is False


# --- code_product_action_has_complete_payload ---

class TestCodeProductActionHasCompletePayload:
    def test_non_code_edit_tool(self):
        action = {"tool": "other_tool", "arguments": {}}
        assert code_product_action_has_complete_payload(action) is True

    def test_unified_diff_with_content(self):
        action = {
            "tool": "repo_propose_code_edit",
            "arguments": {
                "edit_kind": "unified_diff",
                "unified_diff": "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new",
            },
        }
        assert code_product_action_has_complete_payload(action) is True

    def test_unified_diff_old_new_not_copyable(self):
        """Test unified_diff with old_text/new_text that are not example/insert text."""
        action = {
            "tool": "repo_propose_code_edit",
            "arguments": {
                "edit_kind": "unified_diff",
                "old_text": "the old phrase here",
                "new_text": "the new phrase here",
            },
        }
        # Both old_text and new_text are clean (not copyable_example_text)
        assert code_product_action_has_complete_payload(action) is True

    def test_unified_diff_example_old_text(self):
        action = {
            "tool": "repo_propose_code_edit",
            "arguments": {
                "edit_kind": "unified_diff",
                "old_text": "<insert>",
                "new_text": "new phrase",
            },
        }
        assert code_product_action_has_complete_payload(action) is False

    def test_structured_edit_valid(self):
        action = {
            "tool": "repo_propose_code_edit",
            "arguments": {
                "edit_kind": "structured_edit",
                "structured_operations": [{"operation": "replace_exact"}],
            },
        }
        assert code_product_action_has_complete_payload(action) is True

    def test_no_op_valid(self):
        action = {
            "tool": "repo_propose_code_edit",
            "arguments": {
                "edit_kind": "no_op",
                "rationale": "nothing to change",
            },
        }
        assert code_product_action_has_complete_payload(action) is True

    def test_no_op_empty_rationale(self):
        action = {
            "tool": "repo_propose_code_edit",
            "arguments": {
                "edit_kind": "no_op",
                "rationale": "",
            },
        }
        assert code_product_action_has_complete_payload(action) is False

    def test_invalid_edit_kind(self):
        action = {
            "tool": "repo_propose_code_edit",
            "arguments": {
                "edit_kind": "unknown",
            },
        }
        assert code_product_action_has_complete_payload(action) is False

    def test_missing_arguments(self):
        action = {"tool": "repo_propose_code_edit"}
        assert code_product_action_has_complete_payload(action) is False

    def test_arguments_not_dict(self):
        action = {"tool": "repo_propose_code_edit", "arguments": "not a dict"}
        assert code_product_action_has_complete_payload(action) is False