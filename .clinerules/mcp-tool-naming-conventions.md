---
name: mcp-tool-naming-conventions
description: 'Authoritative MCP tool naming conventions for all connected servers. Always use the full prefixed tool name — never strip the server prefix.'
metadata:
  version: 1.0.0
  created: 2026-06-27
---

# MCP Tool Naming Conventions — Authoritative Reference

## Rule: Never Strip the Server Prefix

When calling any MCP tool via `use_mcp_tool`, the `tool_name` parameter MUST always include the full prefixed name as listed below. Do NOT assume that short names (e.g., `estimate_breakage_risk`) work — they will fail with `unknown_tool`.

## Mandatory Pre-call Protocol

Before using ANY MCP tool for the first time in a task:

1. Call the server's `*_health` tool to discover available tools
2. OR use `mcp_batch_execute` with `aicarmine_code_dep_graph` → `aicarmine_code_dep_health` to get the full tool list
3. Never guess tool names from documentation alone — the actual surface may differ

## Server Tool Name Reference Table

| MCP Server | Prefix Pattern | Example Correct Names | Common Wrong Names |
|------------|---------------|----------------------|-------------------|
| `aicarmine_code_dep_graph` | `aicarmine_code_*` | `aicarmine_code_dep_health`, `aicarmine_code_estimate_breakage_risk`, `aicarmine_code_find_callers` | `health`, `estimate_breakage_risk`, `find_callers` |
| `aicarmine_repo_code` | `aicarmine_repo_*` | `aicarmine_repo_code_health`, `aicarmine_repo_code_propose_edit`, `aicarmine_repo_code_apply_patch` | `propose_edit`, `apply_patch`, `health` |
| `aicarmine_wily` | `wily_*` | `wily_health`, `wily_report`, `wily_rank`, `ast_complexity_report`, `ast_file_metrics`, `ast_top_functions` | `complexity_report`, `file_metrics`, `top_functions` |
| `aicarmine_refactor` | `refactor_*` | `refactor_rename_symbol`, `refactor_rename_symbol_rope`, `refactor_add_parameter`, `refactor_extract_function`, `refactor_rename_project`, `refactor_rename_project_bowler`, `git_list_tracked_files`, `refactor_health` | `rename_symbol`, `health` |
| `aicarmine_rag` | `aicarmine_rag_*` | `aicarmine_rag_health`, `aicarmine_rag_context`, `aicarmine_rag_index_status`, `aicarmine_rag_reindex` | `context`, `health`, `index_status` |
| `aicarmine_repo_state` | `aicarmine_repo_state_*` | `aicarmine_repo_state_health`, `aicarmine_repo_state_status`, `aicarmine_repo_state_capabilities` | `status`, `capabilities`, `health` |
| `aicarmine_git_readonly` | `aicarmine_git_*` | `aicarmine_git_readonly_health`, `aicarmine_git_readonly_diff`, `aicarmine_git_readonly_show` | `diff`, `show`, `log` |
| `aicarmine_sqlite_readonly` | `aicarmine_sqlite_*` | `aicarmine_sqlite_readonly_health`, `aicarmine_sqlite_readonly_query`, `aicarmine_sqlite_readonly_schema` | `query`, `schema`, `list_databases` |
| `aicarmine_project_memory` | `aicarmine_project_*` | `aicarmine_project_memory_health`, `aicarmine_project_memory_search`, `aicarmine_project_memory_upsert_verified` | `search`, `get`, `upsert_verified` |
| `aicarmine_test_discovery` | `aicarmine_test_*` | `aicarmine_test_discovery_health`, `aicarmine_test_find_uncovered`, `aicarmine_test_generate_scaffold` | `discover_patterns`, `find_uncovered`, `generate_scaffold` |
| `aicarmine_ollama_subagent` | `aicarmine_ollama_*` | `aicarmine_ollama_subagent_health`, `aicarmine_ollama_subagent_generate`, `aicarmine_ollama_subagent_list_models` | `generate`, `generate_stream`, `list_models` |
| `aicarmine_index_bridge` | `aicarmine_index_*` | `aicarmine_index_bridge_health`, `aicarmine_index_bridge_query`, `aicarmine_index_bridge_persist` | `query`, `persist`, `get_memory` |
| `aicarmine_job_artifact` | `aicarmine_job_*` | `aicarmine_job_artifact_health`, `aicarmine_job_artifact_events`, `aicarmine_job_artifact_final` | `events`, `final`, `tool_results` |
| `aicarmine_mcp_batch_proxy` | `mcp_batch_*` | `mcp_batch_health`, `mcp_batch_list_servers`, `mcp_batch_execute` | (none — these are already short) |
| `aicarmine_codex_ops` | `aicarmine_*_ops_*` or `aicarmine_*_health` | `aicarmine_codex_ops_health`, `aicarmine_service_state_snapshot`, `aicarmine_service_state_processes` | `snapshot`, `processes`, `ports` |

## Critical Lessons Learned

### Mistake 1: Wrong Tool Name Prefix
- **Error:** Used `estimate_breakage_risk` instead of `aicarmine_code_estimate_breakage_risk`
- **Server:** `aicarmine_code_dep_graph`
- **Result:** `unknown_tool` error
- **Fix:** Always use full prefixed name from `*_health` response

### Mistake 2: Import Error in Shared Module
- **Error:** `from repo_mcp_common import _parse_mcp_messages, _frame` — functions don't exist there
- **File:** `services/codex_bridge/mcp_batch_proxy_server.py` line 226
- **Result:** `ImportError: cannot import name '_parse_mcp_messages' from 'repo_mcp_common'`
- **Fix:** Changed to `from ops_mcp_server import _parse_mcp_messages, _frame`

### Mistake 3: Compression Hiding Errors
- **Error:** Used `compress=true` which wrapped error responses in `__compressed__:...` prefix
- **Result:** Made it harder to see actual tool failure
- **Fix:** Use `compress=false` when debugging MCP tool calls

## Verification Checklist Before Tool Call

1. [ ] Have I called the server's `*_health` tool at least once?
2. [ ] Does the tool name match EXACTLY what was returned from `*_health`?
3. [ ] Am I using the full prefixed name (not a shortened version)?
4. [ ] Is the server_name parameter correct for this tool?
5. [ ] Are the arguments structured as a JSON object (not shell-built)?

## Recovery Protocol

If a tool call fails with `unknown_tool`:

1. **DO NOT** retry with the same name
2. **DO** call the server's `*_health` tool to get the actual tool list
3. **DO** verify the exact tool name matches
4. **DO** check if the prefix pattern is required (most AICarmine servers require full prefix)