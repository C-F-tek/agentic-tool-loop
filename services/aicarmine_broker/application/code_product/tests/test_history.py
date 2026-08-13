#!/usr/bin/env python3
"""Tests for services/aicarmine_broker/application/code_product/history.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[4]))

from aicarmine_broker.application.code_product.history import (
    _dict_or_empty,
    _list_or_empty,
    code_product_build_state_duplicate_write,
    code_product_build_state_from_result,
    latest_code_product_build_state,
    successful_code_edit_proposals,
    failed_code_edit_proposal_validation_row,
    code_product_build_state_read_action,
    code_product_source_windows_from_reads,
    code_product_build_state_write_action,
    code_product_build_state_propose_action,
    code_product_candidate_action,
    successful_window_signatures,
    successful_repo_read_window_ranges,
    code_product_payload_rejection_count,
    code_product_source_window_candidate,
    strip_duplicate_window_candidate,
    apply_duplicate_window_replan_contract,
    code_product_low_signal_target,
)


def test_dict_or_empty():
    """Test _dict_or_empty."""
    result = _dict_or_empty({"key": "value"})
    assert result == {"key": "value"}
    
    result = _dict_or_empty(None)
    assert result == {}
    
    result = _dict_or_empty("not a dict")
    assert result == {}
    print("✓ test_dict_or_empty")


def test_list_or_empty():
    """Test _list_or_empty."""
    result = _list_or_empty([1, 2, 3])
    assert result == [1, 2, 3]
    
    result = _list_or_empty(None)
    assert result == []
    
    result = _list_or_empty("not a list")
    assert result == []
    print("✓ test_list_or_empty")


def test_code_product_build_state_duplicate_write():
    """Test code_product_build_state_duplicate_write."""
    history: list[dict] = []
    
    # Test with empty history
    result = code_product_build_state_duplicate_write(history, target_file="src/file.py", text="content")
    assert result is False
    
    # Test with invalid target
    result = code_product_build_state_duplicate_write(history, target_file="", text="content")
    assert result is False
    
    result = code_product_build_state_duplicate_write(history, target_file=".", text="content")
    assert result is False
    print("✓ test_code_product_build_state_duplicate_write")


def test_code_product_build_state_from_result():
    """Test code_product_build_state_from_result."""
    # Test with non-dict result
    result = code_product_build_state_from_result("not a dict")
    assert result == {}
    
    # Test with ok=False
    result = code_product_build_state_from_result({"ok": False})
    assert result == {}
    
    # Test with wrong tool
    result = code_product_build_state_from_result({"ok": True, "tool": "wrong_tool"})
    assert result == {}
    
    # Test with wrong mode
    result = code_product_build_state_from_result({
        "ok": True,
        "tool": "planner_scratchpad_write",
        "mode": "wrong_mode"
    })
    assert result == {}
    
    # Test with valid planner_scratchpad_read result
    valid_result = {
        "ok": True,
        "tool": "planner_scratchpad_read",
        "mode": "code_product_build_state",
        "items": [
            {
                "text": '{"schema":"code_product_build_state","target_file":"src/file.py"}',
                "metadata": {"target_file": "src/file.py"},
            }
        ]
    }
    result = code_product_build_state_from_result(valid_result)
    assert isinstance(result, dict)
    print("✓ test_code_product_build_state_from_result")


def test_latest_code_product_build_state():
    """Test latest_code_product_build_state."""
    history: list[dict] = []
    
    # Test with empty history
    result = latest_code_product_build_state(history)
    assert result == {}
    
    # Test with invalid history
    result = latest_code_product_build_state("not a list")
    assert result == {}
    print("✓ test_latest_code_product_build_state")


def test_successful_code_edit_proposals():
    """Test successful_code_edit_proposals."""
    history: list[dict] = []
    
    # Test with empty history
    result = successful_code_edit_proposals(history)
    assert result == []
    
    # Test with non-list history
    result = successful_code_edit_proposals("not a list")
    assert result == []
    
    # Test with valid proposal
    history = [
        {
            "tool": "repo_propose_code_edit",
            "ok": True,
        }
    ]
    result = successful_code_edit_proposals(history)
    assert len(result) == 1
    
    # Test with failed proposal
    history = [
        {
            "tool": "repo_propose_code_edit",
            "ok": False,
        }
    ]
    result = successful_code_edit_proposals(history)
    assert len(result) == 0
    print("✓ test_successful_code_edit_proposals")


def test_failed_code_edit_proposal_validation_row():
    """Test failed_code_edit_proposal_validation_row."""
    # Test with non-dict input
    result = failed_code_edit_proposal_validation_row("not a dict")
    assert result == {}
    
    # Test with ok=True (should return empty)
    result = failed_code_edit_proposal_validation_row({"ok": True})
    assert result == {}
    
    # Test with valid failed proposal using tool_result format
    history_item = {
        "step": 5,
        "tool_result": {
            "tool": "repo_propose_code_edit",
            "ok": False,
            "errors": ["unified_diff_missing"],
        },
    }
    result = failed_code_edit_proposal_validation_row(history_item)
    assert isinstance(result, dict)
    assert "violations" in result
    assert "step" in result
    print("✓ test_failed_code_edit_proposal_validation_row")


def test_code_product_build_state_read_action():
    """Test code_product_build_state_read_action."""
    state = {
        "schema": "code_product_build_state",
        "target_file": "src/file.py",
        "status": "collecting_source",
    }
    
    result = code_product_build_state_read_action(state, "src/file.py")
    assert isinstance(result, dict)
    assert result["action"] == "tool"
    assert result["tool"] == "planner_scratchpad_read"
    print("✓ test_code_product_build_state_read_action")


def test_code_product_source_windows_from_reads():
    """Test code_product_source_windows_from_reads."""
    history: list[dict] = []
    
    # Test with empty history and invalid target
    result = code_product_source_windows_from_reads(
        history,
        "",
        same_tool_artifact_payload=lambda x: {},
        repo_read_item_full_content=lambda x: ("", {}),
    )
    assert result == []
    
    # Test with invalid target "."
    result = code_product_source_windows_from_reads(
        history,
        ".",
        same_tool_artifact_payload=lambda x: {},
        repo_read_item_full_content=lambda x: ("", {}),
    )
    assert result == []
    print("✓ test_code_product_source_windows_from_reads")


def test_code_product_build_state_write_action():
    """Test code_product_build_state_write_action."""
    # Test with invalid target
    result = code_product_build_state_write_action(
        "",
        same_tool_artifact_payload=lambda x: {},
        repo_read_item_full_content=lambda x: ("", {}),
    )
    assert result == {}
    
    result = code_product_build_state_write_action(
        ".",
        same_tool_artifact_payload=lambda x: {},
        repo_read_item_full_content=lambda x: ("", {}),
    )
    assert result == {}
    print("✓ test_code_product_build_state_write_action")


def test_code_product_build_state_propose_action():
    """Test code_product_build_state_propose_action."""
    # Test with state lacking ready_arguments
    state = {"schema": "code_product_build_state"}
    result = code_product_build_state_propose_action(state, [])
    assert result == {}
    
    # Test with valid ready_arguments
    state = {
        "ready_arguments": {
            "target_file": "src/file.py",
            "edit_kind": "unified_diff",
        }
    }
    result = code_product_build_state_propose_action(state, [])
    assert isinstance(result, dict)
    assert result["action"] == "tool"
    assert result["tool"] == "repo_propose_code_edit"
    print("✓ test_code_product_build_state_propose_action")


def test_code_product_candidate_action():
    """Test code_product_candidate_action."""
    # Test without goal (should return empty)
    result = code_product_candidate_action(
        target_file="src/file.py",
        latest_violations=["test_violation"],
        goal="",
    )
    assert result == {}
    
    # Test with valid goal containing exact old_text and exact new_text labels
    goal = """exact old_text:
line1
line2

exact new_text:
line1
line3"""
    result = code_product_candidate_action(
        target_file="src/file.py",
        latest_violations=["test_violation"],
        goal=goal,
    )
    assert isinstance(result, dict)
    assert result["action"] == "tool"
    assert result["tool"] == "repo_propose_code_edit"
    print("✓ test_code_product_candidate_action")


def test_successful_window_signatures():
    """Test successful_window_signatures."""
    history: list[dict] = []
    
    # Test with empty history
    result = successful_window_signatures(history, "repo_read")
    assert isinstance(result, set)
    
    # Test with non-list history
    result = successful_window_signatures("not a list", "repo_read")
    assert isinstance(result, set)
    print("✓ test_successful_window_signatures")


def test_successful_repo_read_window_ranges():
    """Test successful_repo_read_window_ranges."""
    history: list[dict] = []
    
    # Test with empty history
    result = successful_repo_read_window_ranges(history, "src/file.py")
    assert isinstance(result, list)
    
    # Test with non-list history
    result = successful_repo_read_window_ranges("not a list", "src/file.py")
    assert isinstance(result, list)
    print("✓ test_successful_repo_read_window_ranges")


def test_code_product_payload_rejection_count():
    """Test code_product_payload_rejection_count."""
    rejections: list[dict] = []
    
    # Test with empty list
    result = code_product_payload_rejection_count(rejections)
    assert result == 0
    
    # Test with non-list
    result = code_product_payload_rejection_count("not a list")
    assert result == 0
    
    # Test with valid rejection
    rejections = [
        {
            "violations": ["code_product_payload_not_complete"],
            "rejected_decision": {"tool": "repo_propose_code_edit", "arguments": {"target_file": "src/file.py"}},
        }
    ]
    result = code_product_payload_rejection_count(rejections, "src/file.py")
    assert result == 1
    print("✓ test_code_product_payload_rejection_count")


def test_code_product_source_window_candidate():
    """Test code_product_source_window_candidate."""
    # Test with invalid target
    result = code_product_source_window_candidate("", single_file_prompt_read_chars=8000)
    assert result == {}
    
    result = code_product_source_window_candidate(".", single_file_prompt_read_chars=8000)
    assert result == {}
    
    # Test with valid target
    result = code_product_source_window_candidate(
        "src/file.py",
        line_count=100,
        single_file_prompt_read_chars=8000,
    )
    assert isinstance(result, dict) or result == {}
    print("✓ test_code_product_source_window_candidate")


def test_strip_duplicate_window_candidate():
    """Test strip_duplicate_window_candidate."""
    from aicarmine_broker.application.prompt.window_signatures import repo_read_window_signature
    
    actions: list[dict] = []
    
    # Test with empty actions
    result = strip_duplicate_window_candidate(actions, tool="repo_read", signature="test_sig")
    assert result == []
    
    # Test with non-list actions
    result = strip_duplicate_window_candidate("not a list", tool="repo_read", signature="test_sig")
    assert result == []
    
    # Test with duplicate signatures using proper window signature format
    sig1 = repo_read_window_signature({"path": "src/file.py", "line": 10, "before": 0, "after": 50})
    sig2 = repo_read_window_signature({"path": "src/file.py", "line": 10, "before": 0, "after": 50})
    sig3 = repo_read_window_signature({"path": "src/file.py", "line": 100, "before": 0, "after": 50})
    
    actions = [
        {"tool": "repo_read", "arguments": {"path": "src/file.py", "line": 10, "before": 0, "after": 50}},
        {"tool": "repo_read", "arguments": {"path": "src/file.py", "line": 10, "before": 0, "after": 50}},
        {"tool": "repo_read", "arguments": {"path": "src/file.py", "line": 100, "before": 0, "after": 50}},
    ]
    result = strip_duplicate_window_candidate(actions, tool="repo_read", signature=sig1)
    # Should keep only the non-duplicate action (sig3)
    assert len(result) == 1
    print("✓ test_strip_duplicate_window_candidate")


def test_apply_duplicate_window_replan_contract():
    """Test apply_duplicate_window_replan_contract."""
    contract: dict = {}
    
    # Test with minimal inputs
    result = apply_duplicate_window_replan_contract(
        contract,
        violation="test_violation",
        tool="repo_read",
        args={},
        history=[],
        planner_scratchpad_next_window_action_from_history=lambda args, history: {},
        same_tool_artifact_payload=lambda x: {},
        repo_read_item_full_content=lambda x: ("", {}),
        single_file_prompt_read_chars=8000,
    )
    assert isinstance(result, dict)
    print("✓ test_apply_duplicate_window_replan_contract")


def test_code_product_low_signal_target():
    """Test code_product_low_signal_target."""
    # Test with __init__.py
    result = code_product_low_signal_target("src/__init__.py", {})
    assert result is True
    
    # Test with __main__.py
    result = code_product_low_signal_target("src/__main__.py", {})
    assert result is True
    
    # Test with verified_content_reads with low line_count
    contract = {
        "verified_content_reads": [
            {"path": "src/file.py", "line_count": 10},
        ]
    }
    result = code_product_low_signal_target("src/file.py", contract)
    assert result is True
    
    # Test with verified_content_reads with high line_count
    contract = {
        "verified_content_reads": [
            {"path": "src/file.py", "line_count": 50},
        ]
    }
    result = code_product_low_signal_target("src/file.py", contract)
    assert result is False
    print("✓ test_code_product_low_signal_target")


if __name__ == "__main__":
    tests = [
        test_dict_or_empty,
        test_list_or_empty,
        test_code_product_build_state_duplicate_write,
        test_code_product_build_state_from_result,
        test_latest_code_product_build_state,
        test_successful_code_edit_proposals,
        test_failed_code_edit_proposal_validation_row,
        test_code_product_build_state_read_action,
        test_code_product_source_windows_from_reads,
        test_code_product_build_state_write_action,
        test_code_product_build_state_propose_action,
        test_code_product_candidate_action,
        test_successful_window_signatures,
        test_successful_repo_read_window_ranges,
        test_code_product_payload_rejection_count,
        test_code_product_source_window_candidate,
        test_strip_duplicate_window_candidate,
        test_apply_duplicate_window_replan_contract,
        test_code_product_low_signal_target,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: EXCEPTION: {e}")
            failed += 1
    
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print(f"{'='*50}")
    
    sys.exit(0 if failed == 0 else 1)