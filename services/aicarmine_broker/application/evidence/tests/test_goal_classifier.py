#!/usr/bin/env python3
"""Tests for services/aicarmine_broker/application/evidence/goal_classifier.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from aicarmine_broker.application.evidence.goal_classifier import (
    semantic_goal_text,
    semantic_goal_low,
    goal_is_tool_envelope,
    input_error_goal,
    has_any,
    goal_operational_intent_text,
    goal_has_negative_write_constraints,
    _positive_code_product_marker,
    goal_report_only_code_product_marker,
)


def test_semantic_goal_text():
    """Test semantic_goal_text."""
    result = semantic_goal_text("modify /src/file.py")
    assert isinstance(result, str)
    print("✓ test_semantic_goal_text")


def test_semantic_goal_low():
    """Test semantic_goal_low."""
    result = semantic_goal_low("Modify /SRC/File.Py")
    assert isinstance(result, str)
    assert result == result.lower()
    print("✓ test_semantic_goal_low")


def test_goal_is_tool_envelope():
    """Test goal_is_tool_envelope."""
    result = goal_is_tool_envelope("run repo_read on file.py")
    assert isinstance(result, bool)
    
    result = goal_is_tool_envelope("analyze the codebase")
    assert isinstance(result, bool)
    print("✓ test_goal_is_tool_envelope")


def test_input_error_goal():
    """Test input_error_goal."""
    result = input_error_goal("")
    assert isinstance(result, bool)
    
    result = input_error_goal("valid goal")
    assert isinstance(result, bool)
    print("✓ test_input_error_goal")


def test_has_any():
    """Test has_any."""
    result = has_any("hello world", ("world",))
    assert result is True
    
    result = has_any("hello world", ("goodbye",))
    assert result is False
    print("✓ test_has_any")


def test_goal_operational_intent_text():
    """Test goal_operational_intent_text."""
    result = goal_operational_intent_text("write code to file.py")
    assert isinstance(result, str)
    print("✓ test_goal_operational_intent_text")


def test_goal_has_negative_write_constraints():
    """Test goal_has_negative_write_constraints."""
    result = goal_has_negative_write_constraints("read only analysis")
    assert isinstance(result, bool)
    print("✓ test_goal_has_negative_write_constraints")


def test_positive_code_product_marker():
    """Test _positive_code_product_marker."""
    result = _positive_code_product_marker("produce code product")
    assert isinstance(result, bool)
    print("✓ test_positive_code_product_marker")


def test_goal_report_only_code_product_marker():
    """Test goal_report_only_code_product_marker."""
    result = goal_report_only_code_product_marker("generate report only")
    assert isinstance(result, bool)
    print("✓ test_goal_report_only_code_product_marker")


if __name__ == "__main__":
    tests = [
        test_semantic_goal_text,
        test_semantic_goal_low,
        test_goal_is_tool_envelope,
        test_input_error_goal,
        test_has_any,
        test_goal_operational_intent_text,
        test_goal_has_negative_write_constraints,
        test_positive_code_product_marker,
        test_goal_report_only_code_product_marker,
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