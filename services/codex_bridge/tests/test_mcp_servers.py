#!/usr/bin/env python3
"""Tests for aicarmine MCP servers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add codex_bridge to path
sys.path.insert(0, str(Path(__file__).parents[1]))

from test_coverage_mcp_server import _tools as test_coverage_tools
from test_coverage_mcp_server import SERVER_NAME as TEST_COVERAGE_SERVER
from performance_profiling_mcp_server import _tools as perf_tools
from performance_profiling_mcp_server import SERVER_NAME as PERF_SERVER
from api_documentation_mcp_server import _tools as doc_tools
from api_documentation_mcp_server import SERVER_NAME as DOC_SERVER


def run_tool(server_name: str, tool_name: str, args: dict) -> dict:
    """Run a tool and return result."""
    from repo_mcp_common import selected_repo_root
    
    if server_name == TEST_COVERAGE_SERVER:
        tools = test_coverage_tools()
    elif server_name == PERF_SERVER:
        tools = perf_tools()
    elif server_name == DOC_SERVER:
        tools = doc_tools()
    else:
        return {"ok": False, "error": f"unknown_server: {server_name}"}
    
    spec = tools.get(tool_name)
    if spec is None:
        return {"ok": False, "error": f"unknown_tool: {tool_name}"}
    
    root = selected_repo_root()
    try:
        result = spec.handler(args, root)
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


def test_test_coverage_file():
    """Test test coverage file analysis."""
    result = run_tool(
        TEST_COVERAGE_SERVER,
        "aicarmine_test_coverage_file",
        {"path": "services/codex_bridge/repo_mcp_common.py"}
    )
    
    assert result.get("ok") is True, f"Expected ok=True, got {result}"
    assert result.get("file") == "services/codex_bridge/repo_mcp_common.py"
    assert result.get("total_lines") > 0
    assert result.get("executable_lines") > 0
    print(f"✓ test_test_coverage_file: lines={result.get('total_lines')}, executable={result.get('executable_lines')}")


def test_test_coverage_module():
    """Test test coverage module analysis."""
    result = run_tool(
        TEST_COVERAGE_SERVER,
        "aicarmine_test_coverage_module",
        {"path": "services/codex_bridge"}
    )
    
    assert result.get("ok") is True, f"Expected ok=True, got {result}"
    assert result.get("total_files") > 0
    assert result.get("overall_line_coverage") >= 0
    assert result.get("overall_function_coverage") >= 0
    print(f"✓ test_test_coverage_module: files={result.get('total_files')}, line_cov={result.get('overall_line_coverage')}%")


def test_test_coverage_gaps():
    """Test test coverage gaps identification."""
    result = run_tool(
        TEST_COVERAGE_SERVER,
        "aicarmine_test_coverage_gaps",
        {"path": "services/codex_bridge"}
    )
    
    assert result.get("ok") is True, f"Expected ok=True, got {result}"
    assert result.get("total_gaps") >= 0
    assert result.get("files_with_gaps") >= 0
    print(f"✓ test_test_coverage_gaps: gaps={result.get('total_gaps')}, files_with_gaps={result.get('files_with_gaps')}")


def test_test_coverage_pytest_report():
    """Test pytest report generation."""
    result = run_tool(
        TEST_COVERAGE_SERVER,
        "aicarmine_test_coverage_pytest_report",
        {"path": "services/codex_bridge"}
    )
    
    assert result.get("ok") is True, f"Expected ok=True, got {result}"
    assert result.get("total_source_files") > 0
    assert result.get("total_test_functions") >= 0
    print(f"✓ test_test_coverage_pytest_report: sources={result.get('total_source_files')}, tests={result.get('total_test_functions')}")


def test_test_coverage_summary():
    """Test coverage summary generation."""
    result = run_tool(
        TEST_COVERAGE_SERVER,
        "aicarmine_test_coverage_summary",
        {"path": "services/codex_bridge"}
    )
    
    assert result.get("ok") is True, f"Expected ok=True, got {result}"
    assert result.get("total_lines") > 0
    assert result.get("executable_lines") > 0
    assert result.get("line_coverage_pct") >= 0
    assert result.get("function_coverage_pct") >= 0
    print(f"✓ test_test_coverage_summary: lines={result.get('total_lines')}, line_cov={result.get('line_coverage_pct')}%")


def test_perf_complexity():
    """Test performance complexity analysis."""
    result = run_tool(
        PERF_SERVER,
        "aicarmine_performance_profiling_complexity",
        {"path": "services/codex_bridge"}
    )
    
    assert result.get("ok") is True, f"Expected ok=True, got {result}"
    assert result.get("total_functions") > 0
    dist = result.get("complexity_distribution", {})
    assert sum(dist.values()) == result.get("total_functions")
    print(f"✓ test_perf_complexity: functions={result.get('total_functions')}, dist={dist}")


def test_perf_hotspots():
    """Test performance hotspots identification."""
    result = run_tool(
        PERF_SERVER,
        "aicarmine_performance_profiling_hotspots",
        {"path": "services/codex_bridge"}
    )
    
    assert result.get("ok") is True, f"Expected ok=True, got {result}"
    assert result.get("total_hotspots") >= 0
    risk = result.get("risk_summary", {})
    assert risk.get("high") >= 0
    assert risk.get("medium") >= 0
    assert risk.get("low") >= 0
    print(f"✓ test_perf_hotspots: hotspots={result.get('total_hotspots')}, risks={risk}")


def test_perf_patterns():
    """Test execution patterns analysis."""
    result = run_tool(
        PERF_SERVER,
        "aicarmine_performance_profiling_patterns",
        {"path": "services/codex_bridge"}
    )
    
    assert result.get("ok") is True, f"Expected ok=True, got {result}"
    assert result.get("patterns_found") is not None
    assert result.get("efficiency_score") >= 0
    print(f"✓ test_perf_patterns: patterns={result.get('total_patterns')}, score={result.get('efficiency_score')}")


def test_perf_benchmarks():
    """Test benchmark suggestions generation."""
    result = run_tool(
        PERF_SERVER,
        "aicarmine_performance_profiling_benchmarks",
        {"path": "services/codex_bridge"}
    )
    
    assert result.get("ok") is True, f"Expected ok=True, got {result}"
    assert result.get("total_suggestions") >= 0
    print(f"✓ test_perf_benchmarks: suggestions={result.get('total_suggestions')}")


def test_perf_summary():
    """Test performance summary generation."""
    result = run_tool(
        PERF_SERVER,
        "aicarmine_performance_profiling_summary",
        {"path": "services/codex_bridge"}
    )
    
    assert result.get("ok") is True, f"Expected ok=True, got {result}"
    assert result.get("total_functions") > 0
    assert result.get("efficiency_score") >= 0
    rating = result.get("rating")
    assert rating in ("excellent", "good", "needs_improvement")
    print(f"✓ test_perf_summary: functions={result.get('total_functions')}, score={result.get('efficiency_score')}, rating={rating}")


def test_doc_signatures():
    """Test function signature documentation generation."""
    result = run_tool(
        DOC_SERVER,
        "aicarmine_api_documentation_signatures",
        {"path": "services/codex_bridge/repo_mcp_common.py"}
    )
    
    assert result.get("ok") is True, f"Expected ok=True, got {result}"
    assert result.get("total_functions") > 0
    assert result.get("total_parameters") >= 0
    print(f"✓ test_doc_signatures: functions={result.get('total_functions')}, params={result.get('total_parameters')}")


def test_doc_classes():
    """Test class documentation generation."""
    result = run_tool(
        DOC_SERVER,
        "aicarmine_api_documentation_classes",
        {"path": "services/codex_bridge"}
    )
    
    assert result.get("ok") is True, f"Expected ok=True, got {result}"
    assert result.get("total_classes") >= 0
    assert result.get("documented_classes") >= 0
    print(f"✓ test_doc_classes: classes={result.get('total_classes')}, documented={result.get('documented_classes')}")


def test_doc_modules():
    """Test module-level documentation generation."""
    result = run_tool(
        DOC_SERVER,
        "aicarmine_api_documentation_modules",
        {"path": "services/codex_bridge"}
    )
    
    assert result.get("ok") is True, f"Expected ok=True, got {result}"
    assert result.get("total_modules") > 0
    assert result.get("documented_modules") >= 0
    print(f"✓ test_doc_modules: modules={result.get('total_modules')}, documented={result.get('documented_modules')}")


def test_doc_readme_suggestions():
    """Test README/documentation suggestions generation."""
    result = run_tool(
        DOC_SERVER,
        "aicarmine_api_documentation_readme_suggestions",
        {"path": "services/codex_bridge"}
    )
    
    assert result.get("ok") is True, f"Expected ok=True, got {result}"
    assert result.get("total_suggestions") >= 0
    priority = result.get("priority_summary", {})
    assert priority.get("high") >= 0
    assert priority.get("medium") >= 0
    assert priority.get("low") >= 0
    print(f"✓ test_doc_readme_suggestions: suggestions={result.get('total_suggestions')}, priorities={priority}")


def test_doc_quality():
    """Test documentation quality score calculation."""
    result = run_tool(
        DOC_SERVER,
        "aicarmine_api_documentation_quality",
        {"path": "services/codex_bridge"}
    )
    
    assert result.get("ok") is True, f"Expected ok=True, got {result}"
    assert result.get("score") >= 0
    assert result.get("function_coverage") >= 0
    assert result.get("class_coverage") >= 0
    assert result.get("module_coverage") >= 0
    rating = result.get("rating")
    assert rating in ("excellent", "good", "needs_improvement")
    print(f"✓ test_doc_quality: score={result.get('score')}, rating={rating}")


if __name__ == "__main__":
    tests = [
        test_test_coverage_file,
        test_test_coverage_module,
        test_test_coverage_gaps,
        test_test_coverage_pytest_report,
        test_test_coverage_summary,
        test_perf_complexity,
        test_perf_hotspots,
        test_perf_patterns,
        test_perf_benchmarks,
        test_perf_summary,
        test_doc_signatures,
        test_doc_classes,
        test_doc_modules,
        test_doc_readme_suggestions,
        test_doc_quality,
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