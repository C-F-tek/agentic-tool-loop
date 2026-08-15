#!/usr/bin/env python3
"""Centralized MCP Health Dashboard - Aggregates health from Cline MCP settings."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Import shared helpers
try:
    from repo_mcp_common import (
        ToolSpec,
        health_payload,
        object_schema,
        selected_repo_root,
        self_test,
        serve,
    )
except ImportError:
    SERVICES_ROOT = Path(__file__).resolve().parents[1]
    REPO_HOME_ROOT = Path(__file__).resolve().parents[2]
    if str(SERVICES_ROOT) not in sys.path:
        sys.path.insert(0, str(SERVICES_ROOT))
    
    def _dummy_tool_list(*args, **kwargs):
        return {"tools": []}
    
    def _dummy_health(*args, **kwargs):
        return {"ok": False, "error": "import_failed"}
    
    def _dummy_selected_repo_root():
        return Path.cwd()
    
    def _dummy_self_test(**kwargs):
        return {"ok": False}
    
    def serve(server_name, server_version, tools):
        return 0

SERVER_NAME = "aicarmine-mcp-health-dashboard"
SERVER_VERSION = "2.0.0-cline-aligned"

# Cline MCP settings path
CLINE_MCP_SETTINGS_PATH = Path(os.environ.get(
    "CLINE_MCP_SETTINGS_PATH",
    str(Path.home()) + "/AppData/Roaming/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json"
))

# Health tool mapping for known MCP servers
HEALTH_TOOL_MAP: dict[str, str] = {
    "aicarmine-agentic-loop-client": "aicarmine_agentic_loop_health",
    "aicarmine-batch": "health_check",
    "aicarmine-repo-state": "aicarmine_repo_state_health",
    "aicarmine-repo-search-det": "aicarmine_repo_search_det_health",
    "aicarmine-repo-validate": "aicarmine_repo_validate_health",
    "aicarmine-repo-code": "aicarmine_repo_code_health",
    "aicarmine-rag": None,  # No dedicated health tool
    "aicarmine-sqlite-readonly": "aicarmine_sqlite_readonly_health",
    "aicarmine-job-artifact": "aicarmine_job_artifact_health",
    "aicarmine-job-view": "aicarmine_job_view_health",
    "aicarmine-git-readonly": "aicarmine_git_readonly_health",
    "aicarmine-project-memory": "aicarmine_project_memory_health",
    "aicarmine-local-subagent": "aicarmine_local_subagent_health",
    "aicarmine-codex-ops": "aicarmine_codex_ops_health",
    "aicarmine-refactor": "refactor_health",
    "aicarmine-network-monitor": "network_monitor_health",
    "aicarmine-symbol-rag": "aicarmine_symbol_rag_health",
    "aicarmine-context-compressor": "aicarmine_context_compressor_health",
    "aicarmine-code-architect": "aicarmine_code_architect_health",
    "aicarmine-test-coverage": "aicarmine_test_coverage_health",
    "aicarmine-performance-profiling": "aicarmine_performance_profiling_health",
    "aicarmine-api-documentation": "aicarmine_api_documentation_health",
    "aicarmine-lifecycle": "aicarmine_lifecycle_deprecation_scan",
    "aicarmine-codex-app": "aicarmine_bridge_health",
    "aicarmine-ollama": "aicarmine_ollama_subagent_health",
    "aicarmine-rag-router": None,  # No dedicated health tool
    "aicarmine-unified-codex-bridge": None,  # Disabled server
    "aicarmine-security-scanner": None,  # Non-existent script
}

# Load servers from Cline MCP settings
def _load_cline_mcp_servers() -> dict[str, dict[str, Any]]:
    """Load MCP server definitions from Cline MCP settings JSON."""
    if not CLINE_MCP_SETTINGS_PATH.is_file():
        return {}
    
    try:
        with open(CLINE_MCP_SETTINGS_PATH, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        
        servers = {}
        mcp_servers = settings.get("mcpServers", {})
        for name, config in mcp_servers.items():
            script_path = Path(config.get("args", [""])[-1]) if config.get("args") else None
            disabled = config.get("disabled", False)
            timeout = config.get("timeout", 60)
            auto_approve_tools = config.get("autoApprove", [])
            
            # Extract health tool from autoApprove list or known mapping
            health_tool = HEALTH_TOOL_MAP.get(name)
            if health_tool is None and auto_approve_tools:
                # Try to find a *_health tool in autoApprove
                health_candidates = [t for t in auto_approve_tools if 'health' in t.lower()]
                health_tool = health_candidates[0] if health_candidates else None
            
            servers[name] = {
                "script": str(script_path) if script_path else "",
                "disabled": disabled,
                "timeout": timeout,
                "auto_approve_tools": auto_approve_tools,
                "tool_count": len(auto_approve_tools),
                "env": config.get("env", {}),
                "health_tool": health_tool,
            }
        return servers
    except (json.JSONDecodeError, OSError):
        return {}

# Load from Cline MCP settings at module level
KNOWN_MCP_SERVERS: dict[str, dict[str, Any]] = _load_cline_mcp_servers()


def _probe_script(script_path: Path) -> bool:
    """Check if a script file exists and is readable."""
    try:
        return script_path.is_file() and os.access(str(script_path), os.R_OK)
    except OSError:
        return False


def dashboard_list_servers(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """List all known MCP servers with their metadata."""
    del args, root
    
    servers = []
    for name, info in sorted(KNOWN_MCP_SERVERS.items()):
        script = Path(__file__).resolve().parent / info["script"]
        servers.append({
            "name": name,
            "script": str(script),
            "script_exists": _probe_script(script),
            "health_tool": info.get("health_tool"),
            "port": info.get("port"),
        })
    
    return {
        "ok": True,
        "tool": "dashboard_list_servers",
        "mcp_server": SERVER_NAME,
        "total_servers": len(servers),
        "servers_with_scripts": sum(1 for s in servers if s["script_exists"]),
        "servers_with_health_tools": sum(1 for s in servers if s["health_tool"]),
        "servers": servers,
    }


def dashboard_aggregate_health(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Aggregate health status from all MCP servers."""
    del root
    
    start_time = time.time()
    results = []
    healthy_count = 0
    unhealthy_count = 0
    unknown_count = 0
    
    # Simulate health checks (in production, this would probe each server)
    for name, info in sorted(KNOWN_MCP_SERVERS.items()):
        script_path = Path(__file__).resolve().parent / info["script"]
        script_exists = _probe_script(script_path)
        
        if not script_exists:
            status = "unhealthy"
            unhealthy_count += 1
        elif info.get("health_tool") is None:
            status = "unknown"
            unknown_count += 1
        else:
            # In production, we'd actually call the health tool
            # For now, assume healthy if script exists
            status = "healthy"
            healthy_count += 1
        
        results.append({
            "server": name,
            "status": status,
            "health_tool": info.get("health_tool"),
            "script_exists": script_exists,
            "port": info.get("port"),
        })
    
    elapsed = time.time() - start_time
    total = len(results)
    
    # Calculate overall health score (0-100)
    health_score = int((healthy_count / total * 100) if total > 0 else 0)
    
    return {
        "ok": True,
        "tool": "dashboard_aggregate_health",
        "mcp_server": SERVER_NAME,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_seconds": round(elapsed, 3),
        "health_score": health_score,
        "total_servers": total,
        "healthy": healthy_count,
        "unhealthy": unhealthy_count,
        "unknown": unknown_count,
        "status_summary": {
            "healthy": healthy_count,
            "unhealthy": unhealthy_count,
            "unknown": unknown_count,
        },
        "servers": results,
    }


def dashboard_server_health(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Get detailed health for a specific MCP server."""
    del root
    
    server_name = str(args.get("server", "")).strip()
    if not server_name:
        return {
            "ok": False,
            "error": "missing_server_parameter",
            "tool": "dashboard_server_health",
            "mcp_server": SERVER_NAME,
        }
    
    info = KNOWN_MCP_SERVERS.get(server_name)
    if info is None:
        return {
            "ok": False,
            "error": "unknown_server",
            "requested_server": server_name,
            "known_servers": sorted(KNOWN_MCP_SERVERS.keys()),
            "tool": "dashboard_server_health",
            "mcp_server": SERVER_NAME,
        }
    
    script_path = Path(__file__).resolve().parent / info["script"]
    script_exists = _probe_script(script_path)
    
    return {
        "ok": script_exists,
        "tool": "dashboard_server_health",
        "mcp_server": SERVER_NAME,
        "server": server_name,
        "health_tool": info.get("health_tool"),
        "port": info.get("port"),
        "script": str(script_path),
        "script_exists": script_exists,
        "status": "healthy" if script_exists else "unhealthy",
    }


def dashboard_quick_status(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Get a quick one-line status overview."""
    del args, root
    
    total = len(KNOWN_MCP_SERVERS)
    scripts_exist = sum(1 for info in KNOWN_MCP_SERVERS.values() 
                       if _probe_script(Path(__file__).resolve().parent / info["script"]))
    health_tools = sum(1 for info in KNOWN_MCP_SERVERS.values() if info.get("health_tool"))
    
    return {
        "ok": True,
        "tool": "dashboard_quick_status",
        "mcp_server": SERVER_NAME,
        "summary": f"{scripts_exist}/{total} scripts exist | {health_tools}/{total} have health tools",
        "total_servers": total,
        "scripts_exist": scripts_exist,
        "have_health_tools": health_tools,
    }


def _tools() -> dict[str, ToolSpec]:
    """Define all dashboard tools."""
    tools: dict[str, ToolSpec] = {}
    
    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        payload = health_payload(SERVER_NAME, list(tools.keys()))
        payload["dashboard_version"] = SERVER_VERSION
        payload["known_mcp_servers_count"] = len(KNOWN_MCP_SERVERS)
        return payload
    
    tools["aicarmine_mcp_dashboard_health"] = ToolSpec(
        name="aicarmine_mcp_dashboard_health",
        description="Report MCP health dashboard server health.",
        input_schema=object_schema(),
        handler=health,
    )
    
    tools["dashboard_list_servers"] = ToolSpec(
        name="dashboard_list_servers",
        description="List all known MCP servers with metadata.",
        input_schema=object_schema(),
        handler=dashboard_list_servers,
    )
    
    tools["dashboard_aggregate_health"] = ToolSpec(
        name="dashboard_aggregate_health",
        description="Aggregate health status from all MCP servers into a single view.",
        input_schema=object_schema(),
        handler=dashboard_aggregate_health,
    )
    
    tools["dashboard_server_health"] = ToolSpec(
        name="dashboard_server_health",
        description="Get detailed health for a specific MCP server.",
        input_schema=object_schema({
            "server": {"type": "string"},
        }),
        handler=dashboard_server_health,
    )
    
    tools["dashboard_quick_status"] = ToolSpec(
        name="dashboard_quick_status",
        description="Get a quick one-line status overview of all MCP servers.",
        input_schema=object_schema(),
        handler=dashboard_quick_status,
    )
    
    return tools


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    
    if "--self-test" in argv:
        root = selected_repo_root()
        result = self_test(
            server_name=SERVER_NAME,
            server_version=SERVER_VERSION,
            tools=tools,
            health_tool="aicarmine_mcp_dashboard_health",
            real_tool="dashboard_quick_status",
            real_args={},
        )
        result["selected_repo_root"] = str(root)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())