# services/mcp_server_registry - MCP Server Inventory and Routing
#
# This module provides the canonical MCP server inventory and routing table.
# It consolidates the information from cline_mcp_servers.json into code-based
# models for tool discovery and routing.
#
# All MCP server interactions must use this registry instead of reading
# cline_mcp_servers.json directly or hardcoding server names.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class McpTool:
    """Represents a single MCP tool."""
    name: str
    description: str = ""
    server_name: str = ""
    input_schema: dict = field(default_factory=dict)


@dataclass
class McpServer:
    """Represents an MCP server with its tools."""
    name: str
    category: str = ""
    tools: list[McpTool] = field(default_factory=list)
    base_url: Optional[str] = None
    description: str = ""


class McpServerRegistry:
    """MCP Server Registry.
    
    Canonical inventory of all MCP servers and their tools.
    Provides routing from tool name to server name.
    """
    
    def __init__(self):
        self._servers: dict[str, McpServer] = {}
        self._tool_to_server: dict[str, str] = {}
        self._category_servers: dict[str, list[str]] = {}
        self._build_registry()
    
    def _build_registry(self):
        """Build the complete registry from defined servers."""
        # Core Infrastructure
        codex_app = McpServer(
            name="aicarmine-codex-app",
            category="core_infrastructure",
            description="Master facade: terminal ops, repo CRUD, memory writes, validation"
        )
        codex_app.tools = [
            McpTool(name="aicarmine_bridge_health", server_name="aicarmine-codex-app"),
            McpTool(name="terminal_list_files", server_name="aicarmine-codex-app"),
            McpTool(name="terminal_search_files", server_name="aicarmine-codex-app"),
            McpTool(name="planner_scratchpad_write", server_name="aicarmine-codex-app"),
            McpTool(name="runtime_sqlite_memory_write", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_capabilities", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_status", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_tree", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_list_files", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_search", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_rg_search", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_fd_files", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_read", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_ast_grep_search", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_ast_grep_dry_run", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_tree_sitter_parse", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_ctags_symbols", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_jq_query", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_propose_code_edit", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_unidiff_validate", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_git_apply_check", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_apply_patch", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_validate", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_ruff_check", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_pyright_check", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_pytest_run", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_shellcheck", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_repo_semgrep_scan", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_jobs_status", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_job_detail", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_memory_report", server_name="aicarmine-codex-app"),
            McpTool(name="aicarmine_memory_state_packet", server_name="aicarmine-codex-app"),
        ]
        self._servers[codex_app.name] = codex_app
        
        codex_ops = McpServer(
            name="aicarmine-codex-ops",
            category="core_infrastructure",
            description="Inventory, service state, ports, processes, logs, snapshot"
        )
        codex_ops.tools = [
            McpTool(name="codex_ops_inventory", server_name="aicarmine-codex-ops"),
            McpTool(name="codex_ops_service_state", server_name="aicarmine-codex-ops"),
            McpTool(name="codex_ops_ports", server_name="aicarmine-codex-ops"),
            McpTool(name="codex_ops_processes", server_name="aicarmine-codex-ops"),
            McpTool(name="codex_ops_logs", server_name="aicarmine-codex-ops"),
            McpTool(name="codex_ops_snapshot", server_name="aicarmine-codex-ops"),
            McpTool(name="codex_ops_health", server_name="aicarmine-codex-ops"),
            McpTool(name="codex_ops_status", server_name="aicarmine-codex-ops"),
            McpTool(name="codex_ops_list", server_name="aicarmine-codex-ops"),
        ]
        self._servers[codex_ops.name] = codex_ops
        
        # Repository Operations
        repo_state = McpServer(
            name="aicarmine-repo-state",
            category="repository_operations",
            description="Branch, commit, status, capabilities"
        )
        repo_state.tools = [
            McpTool(name="repo_state_branch", server_name="aicarmine-repo-state"),
            McpTool(name="repo_state_commit", server_name="aicarmine-repo-state"),
            McpTool(name="repo_state_status", server_name="aicarmine-repo-state"),
        ]
        self._servers[repo_state.name] = repo_state
        
        repo_search_det = McpServer(
            name="aicarmine-repo-search-det",
            category="repository_operations",
            description="fd, ripgrep, ast-grep, tree-sitter, ctags, jq"
        )
        repo_search_det.tools = [
            McpTool(name="repo_search_fd", server_name="aicarmine-repo-search-det"),
            McpTool(name="repo_search_rg", server_name="aicarmine-repo-search-det"),
            McpTool(name="repo_search_ast_grep", server_name="aicarmine-repo-search-det"),
            McpTool(name="repo_search_tree_sitter", server_name="aicarmine-repo-search-det"),
            McpTool(name="repo_search_ctags", server_name="aicarmine-repo-search-det"),
            McpTool(name="repo_search_jq", server_name="aicarmine-repo-search-det"),
            McpTool(name="repo_search_list", server_name="aicarmine-repo-search-det"),
            McpTool(name="repo_search_status", server_name="aicarmine-repo-search-det"),
        ]
        self._servers[repo_search_det.name] = repo_search_det
        
        repo_code = McpServer(
            name="aicarmine-repo-code",
            category="repository_operations",
            description="structured_edit, unified_diff, patch apply"
        )
        repo_code.tools = [
            McpTool(name="repo_code_structured_edit", server_name="aicarmine-repo-code"),
            McpTool(name="repo_code_unified_diff", server_name="aicarmine-repo-code"),
            McpTool(name="repo_code_patch_apply", server_name="aicarmine-repo-code"),
            McpTool(name="repo_code_list", server_name="aicarmine-repo-code"),
            McpTool(name="repo_code_status", server_name="aicarmine-repo-code"),
        ]
        self._servers[repo_code.name] = repo_code
        
        repo_validate = McpServer(
            name="aicarmine-repo-validate",
            category="repository_operations",
            description="ruff, pyright, semgrep, probes"
        )
        repo_validate.tools = [
            McpTool(name="repo_validate_ruff", server_name="aicarmine-repo-validate"),
            McpTool(name="repo_validate_pyright", server_name="aicarmine-repo-validate"),
            McpTool(name="repo_validate_pytest", server_name="aicarmine-repo-validate"),
            McpTool(name="repo_validate_shellcheck", server_name="aicarmine-repo-validate"),
            McpTool(name="repo_validate_semgrep", server_name="aicarmine-repo-validate"),
            McpTool(name="repo_validate_probes", server_name="aicarmine-repo-validate"),
            McpTool(name="repo_validate_list", server_name="aicarmine-repo-validate"),
            McpTool(name="repo_validate_status", server_name="aicarmine-repo-validate"),
            McpTool(name="repo_validate_health", server_name="aicarmine-repo-validate"),
        ]
        self._servers[repo_validate.name] = repo_validate
        
        git_readonly = McpServer(
            name="aicarmine-git-readonly",
            category="repository_operations",
            description="log, show, diff, blame, branch-compare"
        )
        git_readonly.tools = [
            McpTool(name="git_log", server_name="aicarmine-git-readonly"),
            McpTool(name="git_show", server_name="aicarmine-git-readonly"),
            McpTool(name="git_diff", server_name="aicarmine-git-readonly"),
            McpTool(name="git_blame", server_name="aicarmine-git-readonly"),
            McpTool(name="git_branch_compare", server_name="aicarmine-git-readonly"),
            McpTool(name="git_status", server_name="aicarmine-git-readonly"),
        ]
        self._servers[git_readonly.name] = git_readonly
        
        # Runtime & Jobs
        job_artifact = McpServer(
            name="aicarmine-job-artifact",
            category="runtime_jobs",
            description="Job events, final output, tool results, planner payloads"
        )
        job_artifact.tools = [
            McpTool(name="job_artifact_events", server_name="aicarmine-job-artifact"),
            McpTool(name="job_artifact_final", server_name="aicarmine-job-artifact"),
            McpTool(name="job_artifact_tool_results", server_name="aicarmine-job-artifact"),
            McpTool(name="job_artifact_planner_payloads", server_name="aicarmine-job-artifact"),
            McpTool(name="job_artifact_list", server_name="aicarmine-job-artifact"),
            McpTool(name="job_artifact_detail", server_name="aicarmine-job-artifact"),
            McpTool(name="job_artifact_health", server_name="aicarmine-job-artifact"),
            McpTool(name="job_artifact_status", server_name="aicarmine-job-artifact"),
            McpTool(name="job_artifact_search", server_name="aicarmine-job-artifact"),
        ]
        self._servers[job_artifact.name] = job_artifact
        
        job_view = McpServer(
            name="aicarmine-job-view",
            category="runtime_jobs",
            description="HTML dashboard, events, final JSON, IA view"
        )
        job_view.tools = [
            McpTool(name="job_view_html", server_name="aicarmine-job-view"),
            McpTool(name="job_view_events", server_name="aicarmine-job-view"),
            McpTool(name="job_view_final_json", server_name="aicarmine-job-view"),
            McpTool(name="job_view_ia_view", server_name="aicarmine-job-view"),
            McpTool(name="job_view_list", server_name="aicarmine-job-view"),
            McpTool(name="job_view_detail", server_name="aicarmine-job-view"),
            McpTool(name="job_view_health", server_name="aicarmine-job-view"),
            McpTool(name="job_view_status", server_name="aicarmine-job-view"),
        ]
        self._servers[job_view.name] = job_view
        
        agentic_loop_client = McpServer(
            name="aicarmine-agentic-loop-client",
            category="runtime_jobs",
            description="Agentic loop run, status, result, broker/reranker ensure"
        )
        agentic_loop_client.tools = [
            McpTool(name="agentic_loop_run", server_name="aicarmine-agentic-loop-client"),
            McpTool(name="agentic_loop_status", server_name="aicarmine-agentic-loop-client"),
            McpTool(name="agentic_loop_result", server_name="aicarmine-agentic-loop-client"),
            McpTool(name="agentic_loop_broker_ensure", server_name="aicarmine-agentic-loop-client"),
            McpTool(name="agentic_loop_reranker_ensure", server_name="aicarmine-agentic-loop-client"),
            McpTool(name="agentic_loop_health", server_name="aicarmine-agentic-loop-client"),
            McpTool(name="agentic_loop_list", server_name="aicarmine-agentic-loop-client"),
        ]
        self._servers[agentic_loop_client.name] = agentic_loop_client
        
        local_subagent = McpServer(
            name="aicarmine-local-subagent",
            category="runtime_jobs",
            description="Read-only bounded agentic tasks via dedicated port"
        )
        local_subagent.tools = [
            McpTool(name="subagent_run_readonly", server_name="aicarmine-local-subagent"),
            McpTool(name="subagent_status", server_name="aicarmine-local-subagent"),
            McpTool(name="subagent_health", server_name="aicarmine-local-subagent"),
        ]
        self._servers[local_subagent.name] = local_subagent
        
        broker_planner = McpServer(
            name="aicarmine-broker-planner",
            category="runtime_jobs",
            description="Planner state, decision history, validator diagnostics"
        )
        broker_planner.tools = [
            McpTool(name="planner_state", server_name="aicarmine-broker-planner"),
            McpTool(name="planner_decisions", server_name="aicarmine-broker-planner"),
            McpTool(name="planner_diagnostics", server_name="aicarmine-broker-planner"),
            McpTool(name="planner_metrics", server_name="aicarmine-broker-planner"),
            McpTool(name="planner_list", server_name="aicarmine-broker-planner"),
            McpTool(name="planner_detail", server_name="aicarmine-broker-planner"),
            McpTool(name="planner_health", server_name="aicarmine-broker-planner"),
            McpTool(name="planner_status", server_name="aicarmine-broker-planner"),
        ]
        self._servers[broker_planner.name] = broker_planner
        
        planner_components = McpServer(
            name="aicarmine-planner-components",
            category="runtime_jobs",
            description="Orientation shadow, vulkan repair, replan, guard rejection"
        )
        planner_components.tools = [
            McpTool(name="planner_orientation_shadow", server_name="aicarmine-planner-components"),
            McpTool(name="planner_vulkan_repair", server_name="aicarmine-planner-components"),
            McpTool(name="planner_replan", server_name="aicarmine-planner-components"),
            McpTool(name="planner_guard_rejection", server_name="aicarmine-planner-components"),
            McpTool(name="planner_list", server_name="aicarmine-planner-components"),
        ]
        self._servers[planner_components.name] = planner_components
        
        # Data & Memory
        project_memory = McpServer(
            name="aicarmine-project-memory",
            category="data_memory",
            description="Search, upsert, mark-stale, supersede, audit sources"
        )
        project_memory.tools = [
            McpTool(name="memory_search", server_name="aicarmine-project-memory"),
            McpTool(name="memory_upsert", server_name="aicarmine-project-memory"),
            McpTool(name="memory_mark_stale", server_name="aicarmine-project-memory"),
            McpTool(name="memory_supersede", server_name="aicarmine-project-memory"),
            McpTool(name="memory_audit", server_name="aicarmine-project-memory"),
            McpTool(name="memory_list", server_name="aicarmine-project-memory"),
            McpTool(name="memory_health", server_name="aicarmine-project-memory"),
        ]
        self._servers[project_memory.name] = project_memory
        
        sqlite_readonly = McpServer(
            name="aicarmine-sqlite-readonly",
            category="data_memory",
            description="List databases, schema, SELECT queries"
        )
        sqlite_readonly.tools = [
            McpTool(name="sqlite_list_databases", server_name="aicarmine-sqlite-readonly"),
            McpTool(name="sqlite_schema", server_name="aicarmine-sqlite-readonly"),
            McpTool(name="sqlite_query", server_name="aicarmine-sqlite-readonly"),
            McpTool(name="sqlite_health", server_name="aicarmine-sqlite-readonly"),
        ]
        self._servers[sqlite_readonly.name] = sqlite_readonly
        
        rag = McpServer(
            name="aicarmine-rag",
            category="data_memory",
            description="RAG context search, index status, reindex"
        )
        rag.tools = [
            McpTool(name="rag_context_search", server_name="aicarmine-rag"),
            McpTool(name="rag_index_status", server_name="aicarmine-rag"),
            McpTool(name="rag_reindex", server_name="aicarmine-rag"),
        ]
        self._servers[rag.name] = rag
        
        rag_router = McpServer(
            name="aicarmine-rag-router",
            category="data_memory",
            description="Cross-DB query planning, topics, consolidation"
        )
        rag_router.tools = [
            McpTool(name="rag_router_analyze_query", server_name="aicarmine-rag-router"),
            McpTool(name="rag_router_topics", server_name="aicarmine-rag-router"),
            McpTool(name="rag_router_consolidate", server_name="aicarmine-rag-router"),
            McpTool(name="rag_router_list", server_name="aicarmine-rag-router"),
            McpTool(name="rag_router_detail", server_name="aicarmine-rag-router"),
            McpTool(name="rag_router_health", server_name="aicarmine-rag-router"),
            McpTool(name="rag_router_status", server_name="aicarmine-rag-router"),
        ]
        self._servers[rag_router.name] = rag_router
        
        # Model & Inference
        ollama = McpServer(
            name="aicarmine-ollama",
            category="model_inference",
            description="Model list, show, chat, generate, create, copy"
        )
        ollama.tools = [
            McpTool(name="ollama_list", server_name="aicarmine-ollama"),
            McpTool(name="ollama_show", server_name="aicarmine-ollama"),
            McpTool(name="ollama_chat", server_name="aicarmine-ollama"),
            McpTool(name="ollama_generate", server_name="aicarmine-ollama"),
            McpTool(name="ollama_create", server_name="aicarmine-ollama"),
            McpTool(name="ollama_copy", server_name="aicarmine-ollama"),
            McpTool(name="ollama_delete", server_name="aicarmine-ollama"),
            McpTool(name="ollama_pull", server_name="aicarmine-ollama"),
            McpTool(name="ollama_push", server_name="aicarmine-ollama"),
            McpTool(name="ollama_version", server_name="aicarmine-ollama"),
            McpTool(name="ollama_tags", server_name="aicarmine-ollama"),
            McpTool(name="ollama_health", server_name="aicarmine-ollama"),
            McpTool(name="ollama_status", server_name="aicarmine-ollama"),
        ]
        self._servers[ollama.name] = ollama
        
        ovms_reranker = McpServer(
            name="aicarmine-ovms-reranker",
            category="model_inference",
            description="Rerank, model list, config, start/stop"
        )
        ovms_reranker.tools = [
            McpTool(name="ovms_rerank", server_name="aicarmine-ovms-reranker"),
            McpTool(name="ovms_model_list", server_name="aicarmine-ovms-reranker"),
            McpTool(name="ovms_config", server_name="aicarmine-ovms-reranker"),
            McpTool(name="ovms_start", server_name="aicarmine-ovms-reranker"),
            McpTool(name="ovms_stop", server_name="aicarmine-ovms-reranker"),
            McpTool(name="ovms_list", server_name="aicarmine-ovms-reranker"),
            McpTool(name="ovms_detail", server_name="aicarmine-ovms-reranker"),
            McpTool(name="ovms_health", server_name="aicarmine-ovms-reranker"),
        ]
        self._servers[ovms_reranker.name] = ovms_reranker
        
        # Build tool-to-server mapping
        for server_name, server in self._servers.items():
            self._tool_to_server.update({t.name: server_name for t in server.tools})
            
            # Build category mapping
            if server.category not in self._category_servers:
                self._category_servers[server.category] = []
            self._category_servers[server.category].append(server.name)
    
    def get_server(self, server_name: str) -> Optional[McpServer]:
        """Get MCP server by name."""
        return self._servers.get(server_name)
    
    def get_server_tools(self, server_name: str) -> list[McpTool]:
        """Get all tools for a given server."""
        server = self._servers.get(server_name)
        return server.tools if server else []
    
    def get_tool_server(self, tool_name: str) -> Optional[str]:
        """Get the server name that owns a given tool."""
        return self._tool_to_server.get(tool_name)
    
    def route_tool_call(self, tool_name: str) -> dict:
        """Route a tool call to the correct MCP server.
        
        Returns a dict with 'server_name' and 'tool_name' keys.
        Raises KeyError if tool is not found.
        """
        server_name = self.get_tool_server(tool_name)
        if not server_name:
            raise KeyError(f"Tool '{tool_name}' not found in any MCP server")
        return {"server_name": server_name, "tool_name": tool_name}
    
    def get_all_servers(self) -> dict[str, McpServer]:
        """Get all registered servers."""
        return dict(self._servers)
    
    def get_servers_by_category(self, category: str) -> list[str]:
        """Get all server names in a given category."""
        return self._category_servers.get(category, [])
    
    def get_all_categories(self) -> list[str]:
        """Get all registered categories."""
        return list(self._category_servers.keys())
    
    def get_total_tools(self) -> int:
        """Get total number of tools across all servers."""
        return sum(len(s.tools) for s in self._servers.values())
    
    def get_total_servers(self) -> int:
        """Get total number of registered servers."""
        return len(self._servers)


# Module-level singleton registry
_registry: Optional[McpServerRegistry] = None

def get_registry() -> McpServerRegistry:
    """Get the global MCP server registry singleton."""
    global _registry
    if _registry is None:
        _registry = McpServerRegistry()
    return _registry


def route_tool_call(tool_name: str) -> dict:
    """Convenience function to route a tool call."""
    return get_registry().route_tool_call(tool_name)


def get_server_tools(server_name: str) -> list[McpTool]:
    """Convenience function to get server tools."""
    return get_registry().get_server_tools(server_name)


def get_tool_server(tool_name: str) -> Optional[str]:
    """Convenience function to get tool's owning server."""
    return get_registry().get_tool_server(tool_name)