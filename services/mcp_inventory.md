# MCP Server Inventory

Generated: 2026-08-04

## Summary

- **Total Servers**: 19
- **Total Tools**: 152

## Server Details

### aicarmine-codex-app
**File**: `services/codex_bridge/mcp_server.py`
**Tools**: 32

| # | Tool Name | Description |
|---|-----------|-------------|
| 1 | aicarmine_bridge_health | Local MCP health. No HTTP call and no agentic loop. |
| 2 | terminal_list_files | Direct terminal-style file listing through in-process dispatcher. Read-only. |
| 3 | terminal_search_files | Direct terminal-style file search through in-process dispatcher. Read-only. |
| 4 | planner_scratchpad_write | Write planner scratchpad memory through direct dispatcher. No agentic loop. |
| 5 | runtime_sqlite_memory_write | Write runtime SQLite memory through direct dispatcher. No agentic loop. |
| 6 | aicarmine_repo_capabilities | Direct repo capability map through in-process dispatcher. Read-only. |
| 7 | aicarmine_repo_status | Direct git/repository status through in-process dispatcher. Read-only. |
| 8 | aicarmine_repo_tree | Direct bounded repository tree listing. Read-only. |
| 9 | aicarmine_repo_list_files | Direct file listing under a repo path. Read-only. |
| 10 | aicarmine_repo_search | Direct broker-managed repository search. Read-only. |
| 11 | aicarmine_repo_rg_search | Direct ripgrep-style repository search wrapper. Read-only. |
| 12 | aicarmine_repo_fd_files | Direct fd-style file discovery wrapper. Read-only. |
| 13 | aicarmine_repo_read | Direct read of one or more repo-relative files. Read-only. |
| 14 | aicarmine_repo_ast_grep_search | Direct ast-grep search where available. Read-only. |
| 15 | aicarmine_repo_ast_grep_dry_run | Direct ast-grep dry-run. Read-only. |
| 16 | aicarmine_repo_tree_sitter_parse | Direct tree-sitter parse helper where available. Read-only. |
| 17 | aicarmine_repo_ctags_symbols | Direct ctags symbol extraction where available. Read-only. |
| 18 | aicarmine_repo_jq_query | Direct jq query helper for JSON files. Read-only. |
| 19 | aicarmine_repo_propose_code_edit | Report-only code edit proposal helper. Does not write files. |
| 20 | aicarmine_repo_unidiff_validate | Validate a unified diff without applying it. |
| 21 | aicarmine_repo_git_apply_check | Run git-apply style patch check through the repo tool wrapper. |
| 22 | aicarmine_repo_apply_patch | Apply exact old_text/new_text patch. Only exposed write tool. |
| 23 | aicarmine_repo_validate | Run broker-defined validation. No free-form command input. |
| 24 | aicarmine_repo_ruff_check | Run repo ruff check wrapper. |
| 25 | aicarmine_repo_pyright_check | Run repo pyright check wrapper. |
| 26 | aicarmine_repo_pytest_run | Run repo pytest wrapper with bounded args from the tool implementation. |
| 27 | aicarmine_repo_shellcheck | Run shellcheck wrapper where available. |
| 28 | aicarmine_repo_semgrep_scan | Run semgrep scan wrapper where available. |
| 29 | aicarmine_jobs_status | Read local agent-job artifacts from filesystem. No HTTP call. |
| 30 | aicarmine_job_detail | Read a local agent-job artifact directory by id. No HTTP call. |
| 31 | aicarmine_memory_report | Read operational/persistent memory SQLite records. Read-only. |
| 32 | aicarmine_memory_state_packet | Build compact context packet from read-only local memory records. |

### aicarmine-repo-state
**File**: `services/codex_bridge/repo_state_mcp_server.py`
**Tools**: 3

| # | Tool Name | Description |
|---|-----------|-------------|
| 1 | aicarmine_repo_state_health | Report Python executable, cwd, repo root, branch, commit, and no-loop guarantees. |
| 2 | aicarmine_repo_state_status | Run deterministic read-only repo_status against the configured repo root. |
| 3 | aicarmine_repo_state_capabilities | Run deterministic read-only repo_capabilities against the configured repo root. |

### aicarmine-repo-search-det
**File**: `services/codex_bridge/repo_search_det_mcp_server.py`
**Tools**: 8

| # | Tool Name | Description |
|---|-----------|-------------|
| 1 | aicarmine_repo_search_det_health | Report Python executable, cwd, repo root, branch, commit, and no-loop guarantees. |
| 2 | aicarmine_repo_search_fd | Find files with fd inside the configured repo root. |
| 3 | aicarmine_repo_search_rg | Search file contents with ripgrep JSON output inside the configured repo root. |
| 4 | aicarmine_repo_search_jq | Run jq against json_text or a repo JSON file. |
| 5 | aicarmine_repo_search_ast_grep | Run ast-grep search inside the configured repo root. |
| 6 | aicarmine_repo_search_ast_grep_dry_run | Run ast-grep rewrite dry-run without writing source files. |
| 7 | aicarmine_repo_search_tree_sitter_parse | Parse a Python file with tree-sitter and return syntax anchors. |
| 8 | aicarmine_repo_search_ctags | List symbols with universal-ctags JSON output. |

### aicarmine-ollama
**File**: `services/codex_bridge/ollama_mcp_server.py`
**Tools**: 11

| # | Tool Name | Description |
|---|-----------|-------------|
| 1 | ollama_health | Check Ollama service health |
| 2 | ollama_list_models | List available models |
| 3 | ollama_show_model | Show model details |
| 4 | ollama_pull_model | Pull a model from registry |
| 5 | ollama_delete_model | Delete a model |
| 6 | ollama_chat | Chat with a model |
| 7 | ollama_generate | Generate text from a model |
| 8 | ollama_create_model | Create a new model |
| 9 | ollama_copy_model | Copy a model |
| 10 | ollama_ps | List running models |
| 11 | ollama_tags | List model tags |

### aicarmine-ovms-reranker
**File**: `services/codex_bridge/ovms_mcp_server.py`
**Tools**: 8

| # | Tool Name | Description |
|---|-----------|-------------|
| 1 | ovms_health | Check OVMS service health |
| 2 | ovms_start | Start OVMS service |
| 3 | ovms_stop | Stop OVMS service |
| 4 | ovms_restart | Restart OVMS service |
| 5 | ovms_rerank | Perform reranking using OVMS |
| 6 | ovms_list_models | List available models |
| 7 | ovms_get_config | Get OVMS configuration |
| 8 | ovms_set_config | Set OVMS configuration |

### aicarmine-repo-validate
**File**: `services/codex_bridge/repo_validate_mcp_server.py`
**Tools**: 9

| # | Tool Name | Description |
|---|-----------|-------------|
| 1 | aicarmine_repo_validate_health | Report Python executable, cwd, repo root, branch, commit, available tools, and no-loop guarantees. |
| 2 | aicarmine_repo_validate_diffcheck | Run repo_validate default git diff --check validation. |
| 3 | aicarmine_repo_validate_ruff | Run ruff check with JSON diagnostics. |
| 4 | aicarmine_repo_validate_pyright | Run pyright with JSON diagnostics. |
| 5 | aicarmine_repo_validate_pytest | Run pytest on selected paths only when explicitly requested by the user. |
| 6 | aicarmine_repo_validate_shellcheck | Run shellcheck JSON diagnostics on selected files. |
| 7 | aicarmine_repo_validate_semgrep | Run semgrep JSON diagnostics with a pattern or config. |
| 8 | aicarmine_repo_validate_probe_profiles | List static read-only probe profiles and report optional Hypothesis availability. Does not execute arbitrary Python. |
| 9 | aicarmine_repo_validate_probe_run | Run a reviewed read-only probe profile with deterministic cases, Hypothesis-generated cases, or both. No network calls or source writes are permitted by the profile. |

### aicarmine-repo-code
**File**: `services/codex_bridge/repo_code_mcp_server.py`
**Tools**: 5

| # | Tool Name | Description |
|---|-----------|-------------|
| 1 | aicarmine_repo_code_health | Report repo-code incubator MCP health and no-loop guarantees. |
| 2 | aicarmine_repo_code_propose_edit | Build a report-only code edit proposal. Prefer multi-file structured_edit edits; use unified_diff only when already valid. Does not write source files. |
| 3 | aicarmine_repo_code_unidiff_validate | Validate unified diff structure without applying it. |
| 4 | aicarmine_repo_code_git_apply_check | Run git apply --check on a unified diff without applying it. |
| 5 | aicarmine_repo_code_apply_patch | Apply either an exact old_text/new_text patch or a validated unified diff/change-set in the incubator MCP. Requires allow_source_write=true. |

### aicarmine-git-readonly
**File**: `services/codex_bridge/git_readonly_mcp_server.py`
**Tools**: 6

| # | Tool Name | Description |
|---|-----------|-------------|
| 1 | aicarmine_git_readonly_health | Report Git read-only MCP health and allowed diagnostic commands. |
| 2 | aicarmine_git_readonly_log | Read recent commits with a fixed structured format. |
| 3 | aicarmine_git_readonly_show | Read one commit with stat and optional patch. |
| 4 | aicarmine_git_readonly_diff | Read a bounded git diff for worktree, staged, or revision range. |
| 5 | aicarmine_git_readonly_blame | Read line blame for a repo file and bounded line range. |
| 6 | aicarmine_git_readonly_branch_compare | Compare a local branch with a remote tracking ref without fetching. |

### aicarmine-sqlite-readonly
**File**: `services/codex_bridge/sqlite_readonly_mcp_server.py`
**Tools**: 4

| # | Tool Name | Description |
|---|-----------|-------------|
| 1 | aicarmine_sqlite_readonly_health | Report SQLite read-only MCP health, aliases, allowlist and safety guarantees. |
| 2 | aicarmine_sqlite_readonly_list_databases | List allowlisted SQLite databases under known repo state and job artifact roots. |
| 3 | aicarmine_sqlite_readonly_schema | Read table/view schema from an allowlisted SQLite database. |
| 4 | aicarmine_sqlite_readonly_query | Run one bounded SELECT/WITH query against an allowlisted SQLite database. |

### aicarmine-job-artifact
**File**: `services/codex_bridge/job_artifact_mcp_server.py`
**Tools**: 9

| # | Tool Name | Description |
|---|-----------|-------------|
| 1 | aicarmine_job_artifact_health | Report job artifact MCP health and read-only filesystem roots. |
| 2 | aicarmine_job_artifact_list_jobs | List persisted agent jobs from allowlisted local artifact roots. |
| 3 | aicarmine_job_artifact_summary | Summarize one persisted agent job without calling broker HTTP. |
| 4 | aicarmine_job_artifact_events | Read filtered/tail events from a job events.ndjson file. |
| 5 | aicarmine_job_artifact_final | Read final.json and final.md for a persisted agent job. |
| 6 | aicarmine_job_artifact_tool_results | List or read job tool-result artifacts from tool-results/. |
| 7 | aicarmine_job_artifact_subturns | Read support-subturn events and tool-result artifacts from a persisted job without broker HTTP. |
| 8 | aicarmine_job_artifact_planner_payload | Read a planner-prompts step payload for a persisted agent job. |
| 9 | aicarmine_job_artifact_rejections | Extract planner/controller rejection events from a job event log. |

### aicarmine-job-view
**File**: `services/codex_bridge/job_view_mcp_server.py`
**Tools**: 8

| # | Tool Name | Description |
|---|-----------|-------------|
| 1 | aicarmine_job_view_health | Report job-view MCP health, render sources and read-only local renderer guarantees. |
| 2 | aicarmine_job_view_list_views | List available local job HTML views and section renderers. |
| 3 | aicarmine_job_view_render | Render one existing agent job HTML view locally without broker HTTP. |
| 4 | aicarmine_job_view_render_section | Render one existing lazy/section HTML fragment locally without broker HTTP. |
| 5 | aicarmine_job_view_ia_payload | Read the IA live control view payload directly from local job files. |
| 6 | aicarmine_job_view_outline | Render a job view and return an HTML outline instead of the full document. |
| 7 | aicarmine_job_view_links | Render a job view and extract links and lazy section URLs. |
| 8 | aicarmine_job_view_validate_html | Render a job view and run bounded structural/safety checks on the HTML. |

### aicarmine-project-memory
**File**: `services/codex_bridge/project_memory_mcp_server.py`
**Tools**: 7

| # | Tool Name | Description |
|---|-----------|-------------|
| 1 | aicarmine_project_memory_health | Report project-local memory MCP health, DB path and write guardrails. |
| 2 | aicarmine_project_memory_search | Search project-local persistent memory records. Read-only. |
| 3 | aicarmine_project_memory_get | Read one project-local memory record by record_id or active scope/key identity. |
| 4 | aicarmine_project_memory_upsert_verified | Write or re-verify one memory record only with explicit source evidence. |
| 5 | aicarmine_project_memory_mark_stale | Mark a memory record stale with explicit evidence for the invalidation. |
| 6 | aicarmine_project_memory_supersede | Supersede a memory record by inserting a new verified record and linking the old one. |
| 7 | aicarmine_project_memory_audit_sources | Audit source references for project-local memory records. Read-only. |

### aicarmine-local-subagent
**File**: `services/codex_bridge/local_subagent_mcp_server.py`
**Tools**: 3

| # | Tool Name | Description |
|---|-----------|-------------|
| 1 | aicarmine_local_subagent_health | Report local subagent facade health and dedicated agentic-loop root/port policy. |
| 2 | aicarmine_local_subagent_capabilities | Describe the local subagent facade over the dedicated Codex agentic loop. |
| 3 | aicarmine_local_subagent_run_readonly | Run one bounded read-only local subagent task through the dedicated Codex agentic loop. |

### aicarmine-agentic-loop-client
**File**: `services/codex_bridge/agentic_loop_client_mcp_server.py`
**Tools**: 7

| # | Tool Name | Description |
|---|-----------|-------------|
| 1 | aicarmine_agentic_loop_health | Report explicit dedicated agentic-loop client health; broker probe is opt-in. |
| 2 | aicarmine_agentic_loop_capabilities | Describe the explicit Codex-to-dedicated-broker client and confirmation contract. |
| 3 | aicarmine_agentic_loop_ensure_reranker | Ensure the local OVMS/BGE reranker is ready on 127.0.0.1:3550; starts the repo-local provider script only with explicit confirmation and only when the configured port is free. |
| 4 | aicarmine_agentic_loop_ensure_broker | Ensure a dedicated broker instance is running with AICARMINE_LAB_REPO equal to the Codex MCP repo root; starts it only with explicit confirmation when the port is free. |
| 5 | aicarmine_agentic_loop_run | Start a canonical broker agentic-loop job on the dedicated Codex port and return a compact Codex-safe terminal summary when available. |
| 6 | aicarmine_agentic_loop_status | Fetch compact status for a dedicated broker agentic-loop job through the canonical router. |
| 7 | aicarmine_agentic_loop_result | Fetch compact terminal result for a dedicated broker agentic-loop job through the canonical router. |

### aicarmine-codex-ops
**File**: `services/codex_bridge/ops_mcp_server.py`
**Tools**: 9

| # | Tool Name | Description |
|---|-----------|-------------|
| 1 | aicarmine_codex_ops_health | Report Codex ops MCP health and no-loop/no-HTTP guarantees. |
| 2 | aicarmine_mcp_inventory_health | Report known local MCP servers available for inventory probing over stdio. |
| 3 | aicarmine_mcp_inventory_list_targets | List the static allowlist of local MCP servers available for inventory probing. |
| 4 | aicarmine_mcp_inventory_probe | Run read-only stdio initialize/list/optional-health inventory probes against local MCP servers. |
| 5 | aicarmine_service_state_health | Report service-state read-only scope and defaults. |
| 6 | aicarmine_service_state_ports | Read local listening sockets without calling HTTP health endpoints. |
| 7 | aicarmine_service_state_processes | Read matching local process command lines with CIM/PowerShell. |
| 8 | aicarmine_service_state_logs | Read tails of repo-local log files only. |
| 9 | aicarmine_service_state_snapshot | Return one read-only snapshot of ports, process command lines and repo-local log tails. |

### aicarmine-rag
**File**: `services/codex_bridge/rag_mcp_server.py`
**Tools**: 3

| # | Tool Name | Description |
|---|-----------|-------------|
| 1 | aicarmine_rag_context | Search the Codex RAG SQLite/FTS5 index and optionally rerank candidates with the local BGE reranker. |
| 2 | aicarmine_rag_index_status | Inspect the Codex RAG index, DB metadata, Git/.gitignore candidate surface, and reranker readiness. |
| 3 | aicarmine_rag_reindex | Update the Codex RAG SQLite index. Default mode is delta over Git candidates: tracked plus untracked files not excluded by .gitignore. |

### aicarmine-rag-router
**File**: `knowledge-RAG-UNIFIED/mcp_rag_router_server.py`
**Tools**: 7

| # | Tool Name | Description |
|---|-----------|-------------|
| 1 | rag_router_list_dbs | List all available RAG databases with metadata |
| 2 | rag_router_list_cross_refs | List cross-references between RAG databases |
| 3 | rag_router_list_topics | List topic categories and their database mappings |
| 4 | rag_router_analyze_query | Analyze a query and return relevant topics and suggested databases with confidence scores |
| 5 | rag_router_consolidate_plan | Create a consolidated query plan across relevant databases |
| 6 | rag_router_get_relevant_dbs | Get all databases relevant to a specific topic |
| 7 | rag_router_get_knowledge_summary | Get a comprehensive summary of all knowledge bases, their topics, and capabilities |

### aicarmine-broker-planner
**File**: `services/codex_bridge/broker_planner_mcp_server.py`
**Tools**: 8

| # | Tool Name | Description |
|---|-----------|-------------|
| 1 | planner_state_inspect | Inspect planner state |
| 2 | planner_decision_history | Get decision history |
| 3 | planner_tool_selection | Inspect tool selection |
| 4 | planner_validator_diagnostics | Get validator diagnostics |
| 5 | planner_evidence_contract | Inspect evidence contract |
| 6 | planner_loop_metrics | Get loop metrics |
| 7 | planner_list_jobs | List planner jobs |
| 8 | planner_config_summary | Get config summary |

### aicarmine-planner-components
**File**: `services/codex_bridge/planner_components_mcp_server.py`
**Tools**: 5

| # | Tool Name | Description |
|---|-----------|-------------|
| 1 | orientation_shadow | Test orientation shadow component - initial orientation evaluation |
| 2 | vulkan_repair | Test vulkan_repair component - planner decision repair |
| 3 | replan_specialist | Test replan_specialist component - replan specialist for validation rejection |
| 4 | guard_rejection | Test guard_rejection component - guard rejection signatures |
| 5 | incomprehensible_retry | Test incomprehensible_retry component - retry for incomprehensible planner output |
