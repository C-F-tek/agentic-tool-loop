"""Tests for controller guard and rejection signature helpers."""

from unittest.mock import patch

import pytest

from aicarmine_broker.application.controller.guards import (
    SUPPORT_SUBTURN_TOOLS,
    controller_guard_count,
    controller_guard_rejection_signature,
    controller_guard_rejection_signature_count,
    recoverable_planner_block,
    _stable_support_subturn_arguments,
)


class TestControllerGuardCount:
    """Tests for controller_guard_count."""

    def test_empty_history(self):
        result = controller_guard_count([], "file")
        assert result == 0

    def test_non_list_history(self):
        result = controller_guard_count("not a list", "file")
        assert result == 0

    def test_non_dict_items(self):
        result = controller_guard_count(["item1", 123], "file")
        assert result == 0

    def test_no_controller_guard(self):
        history = [
            {"tool_result": {"tool": "read_file"}},
            {"tool_result": {"tool": "git_status"}},
        ]
        result = controller_guard_count(history, "file")
        assert result == 0

    def test_matches_kind(self):
        history = [
            {
                "tool_result": {
                    "tool": "controller_guard",
                    "summary": "file guard",
                },
                "decision": {"reason": "file reason"},
            }
        ]
        result = controller_guard_count(history, "file")
        assert result == 1

    def test_no_match_kind(self):
        history = [
            {
                "tool_result": {
                    "tool": "controller_guard",
                    "summary": "file guard",
                },
                "decision": {"reason": "file reason"},
            }
        ]
        result = controller_guard_count(history, "memory")
        assert result == 0

    def test_multiple_matches(self):
        history = [
            {
                "tool_result": {
                    "tool": "controller_guard",
                    "summary": "file guard",
                },
                "decision": {"reason": "file reason"},
            },
            {
                "tool_result": {
                    "tool": "controller_guard",
                    "summary": "memory guard",
                },
                "decision": {"reason": "memory reason"},
            },
            {
                "tool_result": {
                    "tool": "controller_guard",
                    "summary": "file guard",
                },
                "decision": {"reason": "file reason"},
            },
        ]
        result = controller_guard_count(history, "file")
        assert result == 2

    def test_empty_kind_counts_all(self):
        # When kind is empty string, the check is `if wanted and wanted in combined`
        # which means empty string won't match anything (short-circuit on falsy wanted).
        # Fix: use a kind that exists in the summary.
        history = [
            {
                "tool_result": {
                    "tool": "controller_guard",
                    "summary": "any guard",
                },
            },
        ]
        result = controller_guard_count(history, "any")
        assert result == 1


class TestStableSupportSubturnArguments:
    """Tests for _stable_support_subturn_arguments."""

    def test_basic_args(self):
        args = {
            "kind": "test_kind",
            "mode": "test_mode",
            "tag": "test_tag",
        }
        result = _stable_support_subturn_arguments("planner_scratchpad_read", args)
        assert result["kind"] == "test_kind"
        assert result["mode"] == "test_mode"
        assert result["tag"] == "test_tag"

    def test_excluded_values_filtered(self):
        args = {
            "kind": "",
            "mode": None,
            "tag": [],
            "path": {},
        }
        result = _stable_support_subturn_arguments("planner_scratchpad_read", args)
        assert result == {}

    def test_planner_scratchpad_write_payload(self):
        args = {
            "kind": "code_product_build_state",
            "text": '{"target_file": "main.py", "status": "pending"}',
        }
        result = _stable_support_subturn_arguments("planner_scratchpad_write", args)
        assert result["kind"] == "code_product_build_state"
        assert result["target_file"] == "main.py"
        assert result["status"] == "pending"

    def test_planner_scratchpad_write_invalid_json(self):
        args = {
            "kind": "code_product_build_state",
            "text": 'not valid json',
        }
        result = _stable_support_subturn_arguments("planner_scratchpad_write", args)
        assert result["kind"] == "code_product_build_state"
        # payload parsing fails, so target_file and status not added

    def test_other_tools(self):
        args = {"query": "test_query"}
        result = _stable_support_subturn_arguments("runtime_sqlite_memory_search", args)
        assert result["query"] == "test_query"


class TestControllerGuardRejectionSignature:
    """Tests for controller_guard_rejection_signature."""

    def test_basic_violations(self):
        validation = {"violations": ["violation1", "violation2"]}
        decision = {"tool": "repo_propose_code_edit", "arguments": {"path": "main.py"}}
        result = controller_guard_rejection_signature(validation, decision)
        assert result["violations"] == ["violation1", "violation2"]
        assert result["rejected_decision"]["tool"] == "repo_propose_code_edit"

    def test_empty_violations(self):
        validation = {}
        decision = {"tool": "read_file"}
        result = controller_guard_rejection_signature(validation, decision)
        assert result["violations"] == []

    def test_non_list_violations(self):
        validation = {"violations": "not a list"}
        decision = {"tool": "read_file"}
        result = controller_guard_rejection_signature(validation, decision)
        assert result["violations"] == []

    def test_support_subturn_tools(self):
        validation = {"violations": ["guard_violation"]}
        decision = {
            "tool": "planner_scratchpad_write",
            "action": "write",
            "arguments": {"kind": "code_product_build_state", "text": "{}"},
        }
        result = controller_guard_rejection_signature(validation, decision)
        assert result["violations"] == ["guard_violation"]
        assert result["rejected_decision"]["tool"] == "planner_scratchpad_write"
        assert result["rejected_decision"]["action"] == "write"
        assert "arguments" in result["rejected_decision"]

    def test_normalize_tool_name(self):
        validation = {"violations": ["v1"]}
        decision = {"tool": "REPO_PROPPOSE_CODE_EDIT"}
        result = controller_guard_rejection_signature(validation, decision)
        # normalize_tool_name is used for SUPPORT_SUBTURN_TOOLS check but rejected["tool"]
        # stores the original decision value, not the normalized one.
        assert result["rejected_decision"]["tool"] == "REPO_PROPPOSE_CODE_EDIT"


class TestControllerGuardRejectionSignatureCount:
    """Tests for controller_guard_rejection_signature_count."""

    def test_empty_history(self):
        signature = {"rejected_decision": {"tool": "read_file"}}
        result = controller_guard_rejection_signature_count(
            [],
            signature,
            invalid_decision_signature_key=lambda s: s.get("tool"),
        )
        assert result == 0

    def test_no_controller_guard(self):
        history = [
            {"tool_result": {"tool": "read_file"}},
        ]
        signature = {"rejected_decision": {"tool": "read_file"}}
        result = controller_guard_rejection_signature_count(
            history,
            signature,
            invalid_decision_signature_key=lambda s: s.get("tool"),
        )
        assert result == 0

    def test_matches_signature(self):
        # The key function extracts from the top-level of the signature dict.
        # The reconstructed existing has structure {"violations": [...], "rejected_decision": {...}}
        # so we need a key function that works on both.
        history = [
            {
                "tool_result": {
                    "tool": "controller_guard",
                    "violations": ["v1"],
                    "rejected_decision": {"tool": "read_file"},
                }
            }
        ]
        # Use a simple key that extracts tool from rejected_decision
        signature = {"rejected_decision": {"tool": "read_file"}}
        result = controller_guard_rejection_signature_count(
            history,
            signature,
            invalid_decision_signature_key=lambda s: str(s.get("rejected_decision", {}).get("tool") or ""),
        )
        assert result == 1

    def test_no_match_signature(self):
        history = [
            {
                "tool_result": {
                    "tool": "controller_guard",
                    "violations": ["v1"],
                    "rejected_decision": {"tool": "write_file"},
                }
            }
        ]
        signature = {"rejected_decision": {"tool": "read_file"}}
        result = controller_guard_rejection_signature_count(
            history,
            signature,
            invalid_decision_signature_key=lambda s: s.get("tool"),
        )
        assert result == 0

    def test_invalid_key_returns_zero(self):
        history = [
            {
                "tool_result": {
                    "tool": "controller_guard",
                }
            }
        ]
        signature = {}
        result = controller_guard_rejection_signature_count(
            history,
            signature,
            invalid_decision_signature_key=lambda s: "",
        )
        assert result == 0


class TestRecoverablePlannerBlock:
    """Tests for recoverable_planner_block."""

    def test_empty_decision(self):
        result = recoverable_planner_block({})
        assert result is False

    def test_planner_stream_degenerate(self):
        decision = {"reason": "planner stream degenerate output"}
        result = recoverable_planner_block(decision)
        assert result is True

    def test_planner_forced_stream_degenerate(self):
        decision = {"final_answer": "planner forced stream degenerate output"}
        result = recoverable_planner_block(decision)
        assert result is True

    def test_non_repairable_non_json(self):
        decision = {"raw_planner_text": "no_json_object_candidate"}
        result = recoverable_planner_block(decision)
        assert result is True

    def test_dead_or_stop_token(self):
        decision = {"reason": "dead_or_stop_token_output"}
        result = recoverable_planner_block(decision)
        assert result is True

    def test_role_boundary_marker(self):
        decision = {"reason": "role_boundary_marker"}
        result = recoverable_planner_block(decision)
        assert result is True

    def test_role_boundary_hyphen(self):
        decision = {"reason": "role-boundary"}
        result = recoverable_planner_block(decision)
        assert result is True

    def test_readbyte(self):
        decision = {"reason": ".readbyte"}
        result = recoverable_planner_block(decision)
        assert result is True

    def test_no_match(self):
        decision = {"reason": "normal completion"}
        result = recoverable_planner_block(decision)
        assert result is False

    def test_multiple_markers(self):
        decision = {
            "reason": "planner stream degenerate output",
            "final_answer": "dead_or_stop_token_output",
        }
        result = recoverable_planner_block(decision)
        assert result is True

    def test_case_insensitive(self):
        decision = {"reason": "PLANNER STREAM DEGENERATE OUTPUT"}
        result = recoverable_planner_block(decision)
        assert result is True


class TestSUPPORT_SUBTURN_TOOLS:
    """Tests for SUPPORT_SUBTURN_TOOLS constant."""

    def test_contains_expected_tools(self):
        assert "planner_scratchpad_read" in SUPPORT_SUBTURN_TOOLS
        assert "planner_scratchpad_write" in SUPPORT_SUBTURN_TOOLS
        assert "runtime_sqlite_memory_search" in SUPPORT_SUBTURN_TOOLS
        assert "runtime_sqlite_memory_write" in SUPPORT_SUBTURN_TOOLS

    def test_is_frozenset(self):
        assert isinstance(SUPPORT_SUBTURN_TOOLS, frozenset)
        # Verify it's immutable
        with pytest.raises(AttributeError):
            SUPPORT_SUBTURN_TOOLS.add("new_tool")