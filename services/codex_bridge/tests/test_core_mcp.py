#!/usr/bin/env python3
"""Tests for core MCP server modules."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Add codex_bridge to path
sys.path.insert(0, str(Path(__file__).parents[1]))

from mcp_server import (
    _json_dumps,
    _compact_text,
    _ok,
    _err,
    _safe_int,
    _safe_float,
    _tool_content,
    _tool_content_plain,
    _codex_selected_project_root,
    _sync_broker_import_root,
)

# Import git helpers from repo_mcp_common
from repo_mcp_common import run_git, git_info


def test_json_dumps():
    """Test JSON serialization."""
    result = _json_dumps({"key": "value"})
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert parsed == {"key": "value"}
    
    result = _json_dumps([1, 2, 3])
    parsed = json.loads(result)
    assert parsed == [1, 2, 3]
    print(f"✓ test_json_dumps: valid JSON output")


def test_compact_text():
    """Test text compaction."""
    short = "short text"
    result = _compact_text(short)
    assert result == short
    
    long_text = "x" * 50000
    result = _compact_text(long_text)
    assert len(result) < 50000
    assert "...[truncated by aicarmine_codex_app_mcp]" in result
    print(f"✓ test_compact_text: short preserved, long truncated")


def test_ok():
    """Test OK response builder."""
    result = _ok(1, {"status": "ok"})
    assert result["jsonrpc"] == "2.0"
    assert result["id"] == 1
    assert result["result"] == {"status": "ok"}
    print(f"✓ test_ok: correct response structure")


def test_err():
    """Test error response builder."""
    result = _err(2, -32601, "method_not_found", {"method": "test"})
    assert result["jsonrpc"] == "2.0"
    assert result["id"] == 2
    assert "error" in result
    assert result["error"]["code"] == -32601
    assert result["error"]["message"] == "method_not_found"
    print(f"✓ test_err: correct error response structure")


def test_safe_int():
    """Test safe integer conversion."""
    assert _safe_int("42", 0) == 42
    assert _safe_int("invalid", 10) == 10
    assert _safe_int(None, 5) == 5
    assert _safe_int(100, 0, low=0, high=50) == 50
    assert _safe_int(-10, 0, low=0, high=100) == 0
    print(f"✓ test_safe_int: correct conversions and bounds")


def test_safe_float():
    """Test safe float conversion."""
    assert _safe_float("3.14", 0.0) == 3.14
    assert _safe_float("invalid", 2.5) == 2.5
    assert _safe_float(None, 1.0) == 1.0
    print(f"✓ test_safe_float: correct conversions and defaults")


def test_tool_content():
    """Test tool content wrapper."""
    result = _tool_content({"key": "value"})
    assert "content" in result
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "text"
    assert not result.get("isError")
    
    result = _tool_content("error msg", is_error=True)
    assert result["isError"] is True
    print(f"✓ test_tool_content: correct content wrapper")


def test_tool_content_plain():
    """Test plain tool content wrapper."""
    result = _tool_content_plain("plain text")
    assert "content" in result
    assert result["content"][0]["text"] == "plain text"
    print(f"✓ test_tool_content_plain: correct plain content")


def test_selected_repo_root():
    """Test repo root selection."""
    root = _codex_selected_project_root()
    assert root.exists()
    print(f"✓ test_selected_repo_root: {root}")


def test_git_info():
    """Test git info extraction."""
    root = _codex_selected_project_root()
    info = git_info(root)
    
    assert "git_root" in info
    assert "branch" in info
    assert "commit" in info
    assert isinstance(info, dict)
    print(f"✓ test_git_info: branch={info.get('branch')}, commit={info.get('commit')}")


def test_repo_root_sync():
    """Test broker import root sync."""
    result = _sync_broker_import_root()
    assert result == _codex_selected_project_root()
    assert os.environ.get("AICARMINE_CODEX_MCP_REPO_ROOT") == str(result)
    assert os.environ.get("AICARMINE_LAB_REPO") == str(result)
    print(f"✓ test_repo_root_sync: environment updated correctly")


def test_run_git():
    """Test git command execution."""
    root = _codex_selected_project_root()
    code, stdout, stderr = run_git(root, "version")
    
    assert code >= 0
    assert "git" in stdout.lower() or "version" in stdout.lower() or code == 0
    print(f"✓ test_run_git: git version={stdout.strip()[:50]}")


if __name__ == "__main__":
    tests = [
        test_json_dumps,
        test_compact_text,
        test_ok,
        test_err,
        test_safe_int,
        test_safe_float,
        test_tool_content,
        test_tool_content_plain,
        test_selected_repo_root,
        test_git_info,
        test_repo_root_sync,
        test_run_git,
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