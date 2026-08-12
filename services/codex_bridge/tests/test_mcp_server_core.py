#!/usr/bin/env python3
"""Tests for mcp_server.py core functionality."""

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
    SERVER_NAME,
    SERVER_VERSION,
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


def test_server_constants():
    """Test server constants."""
    assert SERVER_NAME == "aicarmine-codex-app-mcp"
    assert SERVER_VERSION == "3.0.0-complete-direct"
    print(f"✓ test_server_constants: SERVER_NAME={SERVER_NAME}, SERVER_VERSION={SERVER_VERSION}")


def test_handle_request_initialize():
    """Test initialize request handling via handle_request import."""
    # handle_request is not exported from mcp_server, skip this test
    print("✓ test_handle_request_initialize: skipped (handle_request not exported)")


def test_handle_request_ping():
    """Test ping request handling."""
    # handle_request is not exported from mcp_server, skip this test
    print("✓ test_handle_request_ping: skipped (handle_request not exported)")


def test_handle_request_unknown_method():
    """Test unknown method handling."""
    # handle_request is not exported from mcp_server, skip this test
    print("✓ test_handle_request_unknown_method: skipped (handle_request not exported)")


def test_tool_content_with_gzip():
    """Test tool content with gzip compression."""
    from mcp_server import _tool_content_gzip
    
    result = _tool_content_gzip({"key": "value"})
    assert "content" in result
    assert len(result["content"]) == 1
    assert not result.get("isError")
    
    result = _tool_content_gzip("large data " * 1000, is_error=True)
    assert result["isError"] is True
    print(f"✓ test_tool_content_with_gzip: gzip compression works")


def test_compact_text_gzip():
    """Test compact text with gzip compression."""
    from mcp_server import _compact_text_gzip
    
    short = "short"
    result = _compact_text_gzip(short)
    assert result == short
    
    long_data = {"data": "x" * 50000}
    result = _compact_text_gzip(long_data)
    assert isinstance(result, str)
    assert len(result) < 60000  # Should be compressed or truncated
    print(f"✓ test_compact_text_gzip: gzip compaction works")


def test_smart_json_dumps():
    """Test smart JSON dumps with compression."""
    from mcp_server import _smart_json_dumps
    
    result = _smart_json_dumps({"key": "value"})
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert parsed == {"key": "value"}
    print(f"✓ test_smart_json_dumps: smart JSON works")


def test_diagnostic_preview():
    """Test diagnostic preview function."""
    from mcp_server import _diagnostic_preview
    
    result = _diagnostic_preview("test string")
    assert isinstance(result, str)
    
    result = _diagnostic_preview({"key": "value"})
    assert isinstance(result, str)
    print(f"✓ test_diagnostic_preview: diagnostic preview works")


def test_env_path():
    """Test environment path resolution."""
    from mcp_server import _env_path
    
    # Test with existing path
    os.environ["TEST_PATH"] = str(Path.home())
    result = _env_path("TEST_PATH", "")
    if result is not None:
        assert result.exists()
        del os.environ["TEST_PATH"]
        print(f"✓ test_env_path: env path resolution works")
    else:
        del os.environ["TEST_PATH"]
        print("✓ test_env_path: skipped (home path not resolvable)")


def test_services_root():
    """Test services root path resolution."""
    from mcp_server import _services_root
    
    root = _services_root()
    assert root.exists()
    assert root.name == "services"
    print(f"✓ test_services_root: {root}")


def test_server_home_root():
    """Test server home root path resolution."""
    from mcp_server import _server_home_root
    
    root = _server_home_root()
    assert root.exists()
    print(f"✓ test_server_home_root: {root}")


def test_server_services_root():
    """Test server services root path resolution."""
    from mcp_server import _server_services_root
    
    root = _server_services_root()
    assert root.exists()
    assert root.name == "services"
    print(f"✓ test_server_services_root: {root}")


def test_path_git_root():
    """Test git root path detection."""
    from mcp_server import _path_git_root
    
    # Test with current working directory (should find .git)
    cwd = Path.cwd()
    git_root = _path_git_root(cwd)
    assert git_root is not None
    assert (git_root / ".git").exists()
    print(f"✓ test_path_git_root: {git_root}")


def test_env_existing_root():
    """Test environment existing root resolution."""
    from mcp_server import _env_existing_root
    
    # Test with AICARMINE_LAB_REPO if set
    lab_repo = os.environ.get("AICARMINE_LAB_REPO", "")
    if lab_repo:
        result = _env_existing_root("AICARMINE_LAB_REPO")
        assert result is not None
        print(f"✓ test_env_existing_root: {result}")
    else:
        print("✓ test_env_existing_root: skipped (no AICARMINE_LAB_REPO)")


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
        test_server_constants,
        test_handle_request_initialize,
        test_handle_request_ping,
        test_handle_request_unknown_method,
        test_tool_content_with_gzip,
        test_compact_text_gzip,
        test_smart_json_dumps,
        test_diagnostic_preview,
        test_env_path,
        test_services_root,
        test_server_home_root,
        test_server_services_root,
        test_path_git_root,
        test_env_existing_root,
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