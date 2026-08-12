#!/usr/bin/env python3
"""Tests for services/aicarmine_broker/application/evidence/coverage_scorer.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from aicarmine_broker.application.evidence.coverage_scorer import (
    _clamp_score,
    _verified_paths,
    score_evidence_coverage,
)


def test_clamp_score():
    """Test _clamp_score."""
    result = _clamp_score(0.5)
    assert isinstance(result, float)
    
    result = _clamp_score(-1.0)
    assert result >= 0.0
    
    result = _clamp_score(1.5)
    assert result <= 1.0
    print("✓ test_clamp_score")


def test_verified_paths():
    """Test _verified_paths."""
    contract = {
        "verified_content_reads": [
            {"path": "/src/file.py"},
            {"path": "/tests/test_file.py"},
        ]
    }
    result = _verified_paths(contract)
    assert isinstance(result, set)
    assert len(result) == 2
    
    contract = {}
    result = _verified_paths(contract)
    assert result == set()
    print("✓ test_verified_paths")


def test_score_evidence_coverage():
    """Test score_evidence_coverage."""
    # Test generic coverage with verified paths
    contract = {
        "verified_content_reads": [
            {"path": "/src/file.py"},
        ]
    }
    result = score_evidence_coverage(contract)
    assert isinstance(result, dict)
    assert "coverage_score" in result
    assert "weaknesses" in result
    assert "reason" in result
    
    # Test code product coverage - score should be >= 0.9 when all conditions met
    contract = {
        "code_product_contract": {
            "required": True,
            "candidate_target_file": "/src/file.py",
            "latest_payload_complete": True,
            "build_state_status": True,
        },
        "verified_content_reads": [
            {"path": "/src/file.py"},
        ]
    }
    result = score_evidence_coverage(contract)
    assert isinstance(result, dict)
    # With target read (0.3) + build state (0.2) + payload complete (0.5) = 1.0
    assert result["coverage_score"] >= 0.9
    print("✓ test_score_evidence_coverage")


if __name__ == "__main__":
    tests = [
        test_clamp_score,
        test_verified_paths,
        test_score_evidence_coverage,
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