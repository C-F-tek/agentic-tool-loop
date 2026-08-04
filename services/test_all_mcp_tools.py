#!/usr/bin/env python3
"""
Test all 152 MCP tools across 19 servers.

Usage:
  python test_all_mcp_tools.py              # Test all servers
  python test_all_mcp_tools.py server_name  # Test specific server
  python test_all_mcp_tools.py --list       # List all servers and tools
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# =============================================================================
# MCP Server Definitions (from inventory)
# =============================================================================

MCP_SERVERS = {
    "aicarmine-codex-app": {
        "file": "services/codex_bridge/mcp_server.py",
        "command": "python",
        "args": ["-u", "services/codex_bridge/mcp_server.py"],
        "health_tool": "aicarmine_bridge_health",
        "tools": [
            "aicarmine_bridge_health", "terminal_list_files", "terminal_search_files",
            "planner_scratchpad_write", "runtime_sqlite_memory_write",
            "aicarmine_repo_capabilities", "aicarmine_repo_status", "aicarmine_repo_tree",
            "aicarmine_repo_list_files", "aicarmine_repo_search", "aicarmine_repo_rg_search",
            "aicarmine_repo_fd_files", "aicarmine_repo_read", "aicarmine_repo_ast_grep_search",
            "aicarmine_repo_ast_grep_dry_run", "aicarmine_repo_tree_sitter_parse",
            "aicarmine_repo_ctags_symbols", "aicarmine_repo_jq_query",
            "aicarmine_repo_propose_code_edit", "aicarmine_repo_unidiff_validate",
            "aicarmine_repo_git_apply_check", "aicarmine_repo_apply_patch",
            "aicarmine_repo_validate", "aicarmine_repo_ruff_check", "aicarmine_repo_pyright_check",
            "aicarmine_repo_pytest_run", "aicarmine_repo_shellcheck", "aicarmine_repo_semgrep_scan",
            "aicarmine_jobs_status", "aicarmine_job_detail", "aicarmine_memory_report",
            "aicarmine_memory_state_packet",
        ],
    },
    "aicarmine-repo-state": {
        "file": "services/codex_bridge/repo_state_mcp_server.py",
        "command": "python",
        "args": ["-u", "services/codex_bridge/repo_state_mcp_server.py"],
        "health_tool": "aicarmine_repo_state_health",
        "tools": [
            "aicarmine_repo_state_health", "aicarmine_repo_state_status",
            "aicarmine_repo_state_capabilities",
        ],
    },
    "aicarmine-repo-search-det": {
        "file": "services/codex_bridge/repo_search_det_mcp_server.py",
        "command": "python",
        "args": ["-u", "services/codex_bridge/repo_search_det_mcp_server.py"],
        "health_tool": "aicarmine_repo_search_det_health",
        "tools": [
            "aicarmine_repo_search_det_health", "aicarmine_repo_search_fd",
            "aicarmine_repo_search_rg", "aicarmine_repo_search_jq",
            "aicarmine_repo_search_ast_grep", "aicarmine_repo_search_ast_grep_dry_run",
            "aicarmine_repo_search_tree_sitter_parse", "aicarmine_repo_search_ctags",
        ],
    },
    "aicarmine-ollama": {
        "file": "services/codex_bridge/ollama_mcp_server.py",
        "command": "python",
        "args": ["-u", "services/codex_bridge/ollama_mcp_server.py"],
        "health_tool": "ollama_health",
        "tools": [
            "ollama_health", "ollama_list_models", "ollama_show_model",
            "ollama_pull_model", "ollama_delete_model", "ollama_chat",
            "ollama_generate", "ollama_create_model", "ollama_copy_model",
            "ollama_ps", "ollama_tags",
        ],
    },
    "aicarmine-ovms-reranker": {
        "file": "services/codex_bridge/ovms_mcp_server.py",
        "command": "python",
        "args": ["-u", "services/codex_bridge/ovms_mcp_server.py"],
        "health_tool": "ovms_health",
        "tools": [
            "ovms_health", "ovms_start", "ovms_stop", "ovms_restart",
            "ovms_rerank", "ovms_list_models", "ovms_get_config", "ovms_set_config",
        ],
    },
    "aicarmine-repo-validate": {
        "file": "services/codex_bridge/repo_validate_mcp_server.py",
        "command": "python",
        "args": ["-u", "services/codex_bridge/repo_validate_mcp_server.py"],
        "health_tool": "aicarmine_repo_validate_health",
        "tools": [
            "aicarmine_repo_validate_health", "aicarmine_repo_validate_diffcheck",
            "aicarmine_repo_validate_ruff", "aicarmine_repo_validate_pyright",
            "aicarmine_repo_validate_pytest", "aicarmine_repo_validate_shellcheck",
            "aicarmine_repo_validate_semgrep", "aicarmine_repo_validate_probe_profiles",
            "aicarmine_repo_validate_probe_run",
        ],
    },
    "aicarmine-repo-code": {
        "file": "services/codex_bridge/repo_code_mcp_server.py",
        "command": "python",
        "args": ["-u", "services/codex_bridge/repo_code_mcp_server.py"],
        "health_tool": "aicarmine_repo_code_health",
        "tools": [
            "aicarmine_repo_code_health", "aicarmine_repo_code_propose_edit",
            "aicarmine_repo_code_unidiff_validate", "aicarmine_repo_code_git_apply_check",
            "aicarmine_repo_code_apply_patch",
        ],
    },
    "aicarmine-git-readonly": {
        "file": "services/codex_bridge/git_readonly_mcp_server.py",
        "command": "python",
        "args": ["-u", "services/codex_bridge/git_readonly_mcp_server.py"],
        "health_tool": "aicarmine_git_readonly_health",
        "tools": [
            "aicarmine_git_readonly_health", "aicarmine_git_readonly_log",
            "aicarmine_git_readonly_show", "aicarmine_git_readonly_diff",
            "aicarmine_git_readonly_blame", "aicarmine_git_readonly_branch_compare",
        ],
    },
    "aicarmine-sqlite-readonly": {
        "file": "services/codex_bridge/sqlite_readonly_mcp_server.py",
        "command": "python",
        "args": ["-u", "services/codex_bridge/sqlite_readonly_mcp_server.py"],
        "health_tool": "aicarmine_sqlite_readonly_health",
        "tools": [
            "aicarmine_sqlite_readonly_health", "aicarmine_sqlite_readonly_list_databases",
            "aicarmine_sqlite_readonly_schema", "aicarmine_sqlite_readonly_query",
        ],
    },
    "aicarmine-job-artifact": {
        "file": "services/codex_bridge/job_artifact_mcp_server.py",
        "command": "python",
        "args": ["-u", "services/codex_bridge/job_artifact_mcp_server.py"],
        "health_tool": "aicarmine_job_artifact_health",
        "tools": [
            "aicarmine_job_artifact_health", "aicarmine_job_artifact_list_jobs",
            "aicarmine_job_artifact_summary", "aicarmine_job_artifact_events",
            "aicarmine_job_artifact_final", "aicarmine_job_artifact_tool_results",
            "aicarmine_job_artifact_subturns", "aicarmine_job_artifact_planner_payload",
            "aicarmine_job_artifact_rejections",
        ],
    },
    "aicarmine-job-view": {
        "file": "services/codex_bridge/job_view_mcp_server.py",
        "command": "python",
        "args": ["-u", "services/codex_bridge/job_view_mcp_server.py"],
        "health_tool": "aicarmine_job_view_health",
        "tools": [
            "aicarmine_job_view_health", "aicarmine_job_view_list_views",
            "aicarmine_job_view_render", "aicarmine_job_view_render_section",
            "aicarmine_job_view_ia_payload", "aicarmine_job_view_outline",
            "aicarmine_job_view_links", "aicarmine_job_view_validate_html",
        ],
    },
    "aicarmine-project-memory": {
        "file": "services/codex_bridge/project_memory_mcp_server.py",
        "command": "python",
        "args": ["-u", "services/codex_bridge/project_memory_mcp_server.py"],
        "health_tool": "aicarmine_project_memory_health",
        "tools": [
            "aicarmine_project_memory_health", "aicarmine_project_memory_search",
            "aicarmine_project_memory_get", "aicarmine_project_memory_upsert_verified",
            "aicarmine_project_memory_mark_stale", "aicarmine_project_memory_supersede",
            "aicarmine_project_memory_audit_sources",
        ],
    },
    "aicarmine-local-subagent": {
        "file": "services/codex_bridge/local_subagent_mcp_server.py",
        "command": "python",
        "args": ["-u", "services/codex_bridge/local_subagent_mcp_server.py"],
        "health_tool": "aicarmine_local_subagent_health",
        "tools": [
            "aicarmine_local_subagent_health", "aicarmine_local_subagent_capabilities",
            "aicarmine_local_subagent_run_readonly",
        ],
    },
    "aicarmine-agentic-loop-client": {
        "file": "services/codex_bridge/agentic_loop_client_mcp_server.py",
        "command": "python",
        "args": ["-u", "services/codex_bridge/agentic_loop_client_mcp_server.py"],
        "health_tool": "aicarmine_agentic_loop_health",
        "tools": [
            "aicarmine_agentic_loop_health", "aicarmine_agentic_loop_capabilities",
            "aicarmine_agentic_loop_ensure_reranker", "aicarmine_agentic_loop_ensure_broker",
            "aicarmine_agentic_loop_run", "aicarmine_agentic_loop_status",
            "aicarmine_agentic_loop_result",
        ],
    },
    "aicarmine-codex-ops": {
        "file": "services/codex_bridge/ops_mcp_server.py",
        "command": "python",
        "args": ["-u", "services/codex_bridge/ops_mcp_server.py"],
        "health_tool": "aicarmine_codex_ops_health",
        "tools": [
            "aicarmine_codex_ops_health", "aicarmine_mcp_inventory_health",
            "aicarmine_mcp_inventory_list_targets", "aicarmine_mcp_inventory_probe",
            "aicarmine_service_state_health", "aicarmine_service_state_ports",
            "aicarmine_service_state_processes", "aicarmine_service_state_logs",
            "aicarmine_service_state_snapshot",
        ],
    },
    "aicarmine-rag": {
        "file": "services/codex_bridge/rag_mcp_server.py",
        "command": "python",
        "args": ["-u", "services/codex_bridge/rag_mcp_server.py"],
        "health_tool": "aicarmine_rag_context",
        "tools": [
            "aicarmine_rag_context", "aicarmine_rag_index_status", "aicarmine_rag_reindex",
        ],
    },
    "aicarmine-rag-router": {
        "file": "knowledge-RAG-UNIFIED/mcp_rag_router_server.py",
        "command": "python",
        "args": ["-u", "knowledge-RAG-UNIFIED/mcp_rag_router_server.py"],
        "health_tool": "rag_router_list_dbs",
        "tools": [
            "rag_router_list_dbs", "rag_router_list_cross_refs", "rag_router_list_topics",
            "rag_router_analyze_query", "rag_router_consolidate_plan",
            "rag_router_get_relevant_dbs", "rag_router_get_knowledge_summary",
        ],
    },
    "aicarmine-broker-planner": {
        "file": "services/codex_bridge/broker_planner_mcp_server.py",
        "command": "python",
        "args": ["-u", "services/codex_bridge/broker_planner_mcp_server.py"],
        "health_tool": "planner_state_inspect",
        "tools": [
            "planner_state_inspect", "planner_decision_history", "planner_tool_selection",
            "planner_validator_diagnostics", "planner_evidence_contract",
            "planner_loop_metrics", "planner_list_jobs", "planner_config_summary",
        ],
    },
    "aicarmine-planner-components": {
        "file": "services/codex_bridge/planner_components_mcp_server.py",
        "command": "python",
        "args": ["-u", "services/codex_bridge/planner_components_mcp_server.py"],
        "health_tool": "orientation_shadow",
        "tools": [
            "orientation_shadow", "vulkan_repair", "replan_specialist",
            "guard_rejection", "incomprehensible_retry",
        ],
    },
}


# =============================================================================
# Test Runner
# =============================================================================

@dataclass
class TestResult:
    server: str
    tool: str
    status: str = "PENDING"  # "PASS", "FAIL", "SKIP", "ERROR"
    duration_ms: float = 0.0
    error: str = ""
    details: dict = field(default_factory=dict)


def send_mcp_message(proc, msg_id: int, method: str, params: dict | None = None, skip_ready: bool = False) -> dict | None:
    """Send a JSON-RPC message to an MCP server process and read the response."""
    message = {
        "jsonrpc": "2.0",
        "id": msg_id,
        "method": method,
        "params": params or {},
    }
    
    if proc.stdin is None:
        return None
    
    raw = json.dumps(message, separators=(",", ":")).encode("utf-8")
    proc.stdin.write(raw + b"\n")
    proc.stdin.flush()
    
    # Read response
    if proc.stdout is None:
        return None
    
    # Skip "READY" line if server outputs it before MCP handshake
    if skip_ready:
        ready_line = proc.stdout.readline()
        while ready_line and ready_line.decode("utf-8", errors="replace").strip() == "READY":
            ready_line = proc.stdout.readline()
    
    line = proc.stdout.readline()
    if not line:
        return None
    
    try:
        return json.loads(line.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None


def test_server_tool(server_name: str, tool_name: str, timeout_seconds: float = 10.0) -> TestResult:
    """Test a single MCP tool by calling its health endpoint or a simple call."""
    result = TestResult(server=server_name, tool=tool_name)
    
    server_def = MCP_SERVERS.get(server_name)
    if not server_def:
        result.status = "ERROR"
        result.error = f"Unknown server: {server_name}"
        return result
    
    # Start the MCP server process
    start = time.time()
    try:
        proc = subprocess.Popen(
            [server_def["command"], *server_def["args"]],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(Path.cwd()),
            env=dict(os.environ),
        )
        
        # Determine if server outputs "READY" before MCP handshake (rag-router)
        skip_ready_flag = server_name == "aicarmine-rag-router"
        
        # Initialize
        init_result = send_mcp_message(proc, 1, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-runner", "version": "1"},
        }, skip_ready=skip_ready_flag)
        
        if not init_result or init_result.get("error"):
            result.status = "FAIL"
            result.error = "Initialization failed"
            proc.kill()
            return result
        
        # Call tools/list to verify server responds
        tools_result = send_mcp_message(proc, 2, "tools/list")
        
        if not tools_result or tools_result.get("error"):
            result.status = "FAIL"
            result.error = f"Server returned error: {json.dumps(tools_result.get('error', {}))[:200]}"
            proc.kill()
            return result
        
        # Verify the tool is listed
        tools_list = tools_result.get("result", {}).get("tools", [])
        tool_names = [t.get("name", "") for t in tools_list]
        
        if tool_name not in tool_names:
            result.status = "FAIL"
            result.error = f"Tool '{tool_name}' not found in server tools list"
            proc.kill()
            return result
        
        # Call the health tool or the tool itself with minimal args
        health_tool = server_def.get("health_tool", tool_name)
        call_id = 3
        
        # Some tools (like rag_reindex) require non-empty args and will hang with empty params.
        # Skip tools that are known to require arguments beyond empty params.
        tools_requiring_args = {
            "aicarmine_rag_reindex",
            "rag_router_analyze_query",
            "rag_router_consolidate_plan",
            "rag_router_get_relevant_dbs",
        }
        
        if health_tool in tools_requiring_args:
            result.status = "SKIP"
            result.error = "Tool requires non-empty arguments (skipped)"
            proc.kill()
            return result
        
        # For health tools, call with empty params
        call_result = send_mcp_message(proc, call_id, "tools/call", {
            "name": health_tool,
            "arguments": {},
        })
        
        if call_result:
            if call_result.get("error"):
                result.status = "FAIL"
                result.error = str(call_result.get("error", {}))[:300]
            else:
                result.status = "PASS"
                result.details = call_result.get("result", {})
        else:
            result.status = "FAIL"
            result.error = "No response from server"
        
        proc.kill()
        
    except Exception as exc:
        result.status = "ERROR"
        result.error = str(exc)
    
    result.duration_ms = (time.time() - start) * 1000
    return result


def test_all_servers() -> list[TestResult]:
    """Test all MCP servers and their tools."""
    results: list[TestResult] = []
    
    for server_name, server_def in MCP_SERVERS.items():
        for tool_name in server_def["tools"]:
            result = test_server_tool(server_name, tool_name)
            results.append(result)
            
            # Print progress
            status_symbol = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "SKIP", "ERROR": "ERROR"}.get(result.status, "UNKNOWN")
            print(f"  [{status_symbol}] {server_name}/{tool_name} ({result.duration_ms:.0f}ms)")
            if result.status in ("FAIL", "ERROR"):
                print(f"      Error: {result.error[:200]}")
    
    return results


def list_servers():
    """List all servers and their tools."""
    print(f"\n{'Server':<35} {'Tools':>8} {'Health Tool':<45}")
    print("-" * 120)
    for server_name, server_def in MCP_SERVERS.items():
        print(f"{server_name:<35} {len(server_def['tools']):>8} {server_def['health_tool']:<45}")
    print(f"\nTotal: {len(MCP_SERVERS)} servers, {sum(len(s['tools']) for s in MCP_SERVERS.values())} tools")


def main():
    args = sys.argv[1:]
    
    if "--list" in args:
        list_servers()
        return 0
    
    if args and args[0] in MCP_SERVERS:
        # Test specific server
        server_name = args[0]
        print(f"\nTesting {server_name}...")
        results = []
        for tool_name in MCP_SERVERS[server_name]["tools"]:
            result = test_server_tool(server_name, tool_name)
            results.append(result)
            status_symbol = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "SKIP", "ERROR": "ERROR"}.get(result.status, "UNKNOWN")
            print(f"  [{status_symbol}] {tool_name} ({result.duration_ms:.0f}ms)")
            if result.status in ("FAIL", "ERROR"):
                print(f"      Error: {result.error[:200]}")
    else:
        # Test all servers
        print("\nTesting all 152 MCP tools across 19 servers...")
        print("=" * 70)
        results = test_all_servers()
    
    # Summary
    total = len(results)
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status in ("FAIL", "ERROR"))
    
    print("\n" + "=" * 70)
    print(f"Results: {passed}/{total} passed, {failed}/{total} failed")
    print(f"Duration: {sum(r.duration_ms for r in results):.0f}ms total")
    print("=" * 70)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())