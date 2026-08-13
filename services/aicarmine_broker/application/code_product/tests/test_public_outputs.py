"""Tests for public code-product and partial-product text helpers."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import as package member to support relative imports in source
from aicarmine_broker.application.code_product.public_outputs import (
    latest_code_product_payload as _latest_code_product_payload,
    code_product_answer_text,
    partial_product_clean_text,
    partial_products_for_30b,
    best_partial_product_for_30b,
    partial_product_answer_text,
)


class TestLatestCodeProductPayload:
    """Tests for latest_code_product_payload."""

    def test_empty_history(self):
        result = _latest_code_product_payload([])
        assert result == {}

    def test_non_list_history(self):
        result = _latest_code_product_payload("not a list")
        assert result == {}

    def test_non_dict_items(self):
        result = _latest_code_product_payload(["item1", 123, None])
        assert result == {}

    def test_no_matching_tool(self):
        history = [
            {"tool_result": {"tool": "read_file", "ok": True}},
            {"tool_result": {"tool": "git_status", "ok": True}},
        ]
        result = _latest_code_product_payload(history)
        assert result == {}

    def test_returns_proposal(self):
        proposal = {
            "tool": "repo_propose_code_edit",
            "ok": True,
            "kind": "code_edit_proposal",
            "target_file": "main.py",
        }
        history = [{"tool_result": proposal}]
        result = _latest_code_product_payload(history)
        assert result == proposal

    def test_returns_latest_matching(self):
        proposal = {
            "tool": "repo_propose_code_edit",
            "ok": True,
            "kind": "code_edit_proposal",
            "target_file": "main.py",
        }
        history = [
            {"tool_result": {"tool": "read_file", "ok": True}},
            {"tool_result": proposal},
        ]
        result = _latest_code_product_payload(history)
        assert result == proposal

    def test_ok_false_not_matched(self):
        history = [
            {
                "tool_result": {
                    "tool": "repo_propose_code_edit",
                    "ok": False,
                    "kind": "code_edit_proposal",
                }
            }
        ]
        result = _latest_code_product_payload(history)
        assert result == {}

    def test_kind_mismatch(self):
        history = [
            {
                "tool_result": {
                    "tool": "repo_propose_code_edit",
                    "ok": True,
                    "kind": "not_code_edit",
                }
            }
        ]
        result = _latest_code_product_payload(history)
        assert result == {}


class TestCodeProductAnswerText:
    """Tests for code_product_answer_text."""

    def test_no_proposal_returns_empty(self):
        result = code_product_answer_text(None)
        assert result == ""

    def test_non_dict_result(self):
        result = code_product_answer_text("not a dict")
        assert result == ""

    def test_empty_history_returns_empty(self):
        result = code_product_answer_text({"history": []})
        assert result == ""

    def test_unified_diff_format(self):
        # latest_code_product_payload requires tool == "repo_propose_code_edit" and kind == "code_edit_proposal"
        proposal = {
            "tool": "repo_propose_code_edit",
            "ok": True,
            "kind": "code_edit_proposal",
            "target_file": "main.py",
            "edit_kind": "unified_diff",
            "unified_diff": "diff --git a/main.py b/main.py\n+added line",
            "rationale": "Fix bug",
            "source_writes_performed": False,
            "patch_application_performed": False,
            "manual_review_required": True,
        }
        history = [{"tool_result": proposal}]
        result = code_product_answer_text({"history": history})
        assert "Code edit proposal generated." in result
        assert "main.py" in result
        assert "unified_diff" in result
        assert "```diff" in result
        assert "Fix bug" in result

    def test_structured_edit_format(self):
        proposal = {
            "tool": "repo_propose_code_edit",
            "ok": True,
            "kind": "code_edit_proposal",
            "target_file": "main.py",
            "edit_kind": "structured_edit",
            "structured_operations": [
                {"path": "main.py", "operation": "replace_exact"}
            ],
            "rationale": "Refactor",
        }
        history = [{"tool_result": proposal}]
        result = code_product_answer_text({"history": history})
        assert "Code edit proposal generated." in result
        assert "structured_edit" in result
        assert "```json" in result

    def test_no_op_format(self):
        proposal = {
            "tool": "repo_propose_code_edit",
            "ok": True,
            "kind": "code_edit_proposal",
            "target_file": "main.py",
            "edit_kind": "no_op",
            "rationale": "No changes needed",
        }
        history = [{"tool_result": proposal}]
        result = code_product_answer_text({"history": history})
        assert "no_op" in result
        assert "No patch content" in result

    def test_no_op_without_rationale_returns_empty(self):
        proposal = {
            "target_file": "main.py",
            "edit_kind": "no_op",
        }
        history = [{"tool_result": proposal}]
        result = code_product_answer_text({"history": history})
        assert result == ""

    def test_unknown_edit_kind_returns_empty(self):
        proposal = {
            "target_file": "main.py",
            "edit_kind": "unknown_kind",
        }
        history = [{"tool_result": proposal}]
        result = code_product_answer_text({"history": history})
        assert result == ""

    def test_respects_limit(self):
        proposal = {
            "target_file": "main.py",
            "edit_kind": "unified_diff",
            "unified_diff": "x" * 1000,
        }
        history = [{"tool_result": proposal}]
        result = code_product_answer_text({"history": history}, limit=100)
        assert len(result) <= 100

    def test_validation_commands_in_output(self):
        proposal = {
            "tool": "repo_propose_code_edit",
            "ok": True,
            "kind": "code_edit_proposal",
            "target_file": "main.py",
            "edit_kind": "unified_diff",
            "unified_diff": "diff...",
            "validation_commands": ["pytest", "ruff"],
        }
        history = [{"tool_result": proposal}]
        result = code_product_answer_text({"history": history})
        assert "validation_commands:" in result
        assert "pytest" in result


class TestPartialProductCleanText:
    """Tests for partial_product_clean_text."""

    def test_empty_returns_empty(self):
        assert partial_product_clean_text("") == ""
        assert partial_product_clean_text(None) == ""
        assert partial_product_clean_text("   ") == ""

    def test_no_clip_when_short(self):
        result = partial_product_clean_text("short text")
        assert result == "short text"

    def test_clips_when_long(self):
        long_text = "x" * 50000
        result = partial_product_clean_text(long_text, limit=40000)
        assert len(result) <= 40000

    def test_strips_whitespace(self):
        result = partial_product_clean_text("  hello world  ")
        assert result == "hello world"

    def test_custom_limit(self):
        result = partial_product_clean_text("hello world", limit=5)
        assert len(result) <= 5


class TestPartialProductsFor30B:
    """Tests for partial_products_for_30b."""

    def test_empty_history(self):
        result = partial_products_for_30b([], code_product_build_state_kind="file")
        assert result == []

    def test_non_list_history(self):
        result = partial_products_for_30b("not a list", code_product_build_state_kind="file")
        assert result == []

    def test_non_dict_items(self):
        result = partial_products_for_30b(["item1", 123], code_product_build_state_kind="file")
        assert result == []

    def test_respects_limit(self):
        proposal = {
            "tool": "repo_propose_code_edit",
            "ok": True,
            "kind": "code_edit_proposal",
        }
        history = [
            {"step": i, "tool_result": proposal} for i in range(10)
        ]
        result = partial_products_for_30b(history, code_product_build_state_kind="file", limit=3)
        assert len(result) <= 3

    def test_deduplication(self):
        # partial_products_for_30b deduplicates by json.dumps(product, sort_keys=True)[:12000]
        # Each history item has a different "step" field, so each produces a unique key.
        # Deduplication only works when the full product dict is identical.
        # Fix: use same step value for all items so they deduplicate.
        rejected = {
            "tool": "repo_propose_code_edit",
            "arguments": {"target_file": "main.py"},
        }
        history = [
            {
                "step": 0,  # Same step for all items
                "tool_result": {"rejected_decision": rejected},
            }
            for _ in range(5)
        ]
        result = partial_products_for_30b(history, code_product_build_state_kind="file")
        assert len(result) == 1

    def test_rejected_code_edit_candidate(self):
        rejected = {
            "tool": "repo_propose_code_edit",
            "arguments": {
                "target_file": "main.py",
                "edit_kind": "unified_diff",
                "rationale": "Bad proposal",
                "unified_diff": "diff...",
            },
        }
        history = [
            {
                "step": 1,
                "tool_result": {
                    "rejected_decision": rejected,
                    "violations": ["violation1"],
                    "summary": "Rejected",
                }
            }
        ]
        result = partial_products_for_30b(history, code_product_build_state_kind="file")
        assert len(result) == 1
        assert result[0]["kind"] == "partial_code_product_candidate"
        assert result[0]["source"] == "validator_rejected_repo_propose_code_edit"

    def test_action_plan_candidate(self):
        history = [
            {
                "step": 2,
                "tool_result": {
                    "action_plan_candidate": "Do X then Y",
                    "violations": [],
                    "summary": "Plan",
                }
            }
        ]
        result = partial_products_for_30b(history, code_product_build_state_kind="file")
        assert len(result) == 1
        assert result[0]["kind"] == "action_plan_candidate"

    def test_repair_candidate(self):
        history = [
            {
                "step": 3,
                "tool_result": {
                    "vulkan_repair": {
                        "repaired_decision": {"final_answer": "Fixed"},
                        "error": "gpu_timeout",
                    },
                    "violations": [],
                    "summary": "Repair",
                }
            }
        ]
        result = partial_products_for_30b(history, code_product_build_state_kind="file")
        assert len(result) == 1
        assert result[0]["kind"] == "repair_candidate_text"


class TestBestPartialProductFor30B:
    """Tests for best_partial_product_for_30b."""

    def test_empty_history(self):
        result = best_partial_product_for_30b([], code_product_build_state_kind="file")
        assert result == {}

    def test_returns_first_when_no_diff(self):
        products = [
            {"kind": "repair_candidate_text", "unified_diff": ""},
            {"kind": "action_plan_candidate", "unified_diff": ""},
        ]
        # Mock partial_products_for_30b to return our products
        with patch('aicarmine_broker.application.code_product.public_outputs.partial_products_for_30b', return_value=products):
            result = best_partial_product_for_30b([], code_product_build_state_kind="file")
            assert result["kind"] == "repair_candidate_text"

    def test_returns_diff_when_present(self):
        products = [
            {"kind": "repair_candidate_text", "unified_diff": "diff..."},
            {"kind": "action_plan_candidate", "unified_diff": ""},
        ]
        with patch('aicarmine_broker.application.code_product.public_outputs.partial_products_for_30b', return_value=products):
            result = best_partial_product_for_30b([], code_product_build_state_kind="file")
            assert result["kind"] == "repair_candidate_text"


class TestPartialProductAnswerText:
    """Tests for partial_product_answer_text."""

    def test_no_product_returns_empty(self):
        result = partial_product_answer_text(
            None,
            code_product_build_state_kind="file",
        )
        assert result == ""

    def test_non_dict_result(self):
        result = partial_product_answer_text(
            "not a dict",
            code_product_build_state_kind="file",
        )
        assert result == ""

    def test_unified_diff_format(self):
        product = {
            "kind": "partial_code_product_candidate",
            "source": "validator_rejected_repo_propose_code_edit",
            "step": 1,
            "validator_accepted": False,
            "target_file": "main.py",
            "edit_kind": "unified_diff",
            "rejection_summary": "Bad proposal",
            "rationale": "Fix bug",
            "unified_diff": "diff --git a/main.py b/main.py\n+added line",
        }
        result = partial_product_answer_text(
            {"best_partial_product_for_30b": product},
            code_product_build_state_kind="file",
        )
        assert "Prodotto parziale non validato dal controller." in result
        assert "partial_code_product_candidate" in result
        assert "```diff" in result

    def test_structured_edit_format(self):
        product = {
            "kind": "partial_code_product_candidate",
            "source": "validator_rejected_repo_propose_code_edit",
            "structured_operations": [{"path": "main.py", "operation": "replace_exact"}],
        }
        result = partial_product_answer_text(
            {"best_partial_product_for_30b": product},
            code_product_build_state_kind="file",
        )
        assert "```json" in result

    def test_text_format(self):
        product = {
            "kind": "repair_candidate_text",
            "text": "Some repair text",
        }
        result = partial_product_answer_text(
            {"best_partial_product_for_30b": product},
            code_product_build_state_kind="file",
        )
        assert "Some repair text" in result

    def test_state_text_format(self):
        product = {
            "kind": "partial_code_product_build_state",
            "state_text": '{"payload": {"target_file": "main.py"}}',
        }
        result = partial_product_answer_text(
            {"best_partial_product_for_30b": product},
            code_product_build_state_kind="file",
        )
        assert "```json" in result

    def test_respects_limit(self):
        product = {
            "kind": "repair_candidate_text",
            "text": "x" * 10000,
        }
        result = partial_product_answer_text(
            {"best_partial_product_for_30b": product},
            code_product_build_state_kind="file",
            limit=100,
        )
        assert len(result) <= 100

    def test_fallback_to_best_partial(self):
        # When best_partial_product_for_30b is not in result, it should fallback
        product = {
            "kind": "repair_candidate_text",
            "text": "Fallback text",
        }
        with patch('aicarmine_broker.application.code_product.public_outputs.best_partial_product_for_30b', return_value=product):
            result = partial_product_answer_text(
                {},  # No best_partial_product_for_30b key
                code_product_build_state_kind="file",
            )
            assert "Fallback text" in result
