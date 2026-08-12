#!/usr/bin/env python3
"""Tests for services/aicarmine_broker/application/evidence/execution_digest.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from aicarmine_broker.application.evidence.execution_digest import (
    repo_read_content_views,
    execution_evidence_digest_text,
)


def test_repo_read_content_views():
    """Test repo_read_content_views."""
    history = [
        {
            "tool": "repo_read",
            "result": {
                "path": "/src/file.py",
                "content": "def hello(): pass",
            }
        }
    ]
    # Function signature: repo_read_content_views(history, repo_read_item_full_content=...)
    result = repo_read_content_views(history, repo_read_item_full_content=lambda x: x.get("content") if isinstance(x, dict) else "")
    assert isinstance(result, list)
    print("✓ test_repo_read_content_views")


def test_execution_evidence_digest_text():
    """Test execution_evidence_digest_text."""
    result = {}
    # Function signature: execution_evidence_digest_text(result, limit=..., repo_read_item_full_content=..., extract_key_lines=...)
    output = execution_evidence_digest_text(
        result, 
        limit=12000,
        repo_read_item_full_content=lambda x: x.get("content") if isinstance(x, dict) else "",
        extract_key_lines=lambda content: [line for line in content.split("\n") if line.strip()] if isinstance(content, str) else []
    )
    assert isinstance(output, str)
    print("✓ test_execution_evidence_digest_text")


if __name__ == "__main__":
    tests = [
        test_repo_read_content_views,
        test_execution_evidence_digest_text,
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