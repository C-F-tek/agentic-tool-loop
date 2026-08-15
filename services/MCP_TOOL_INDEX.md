# MCP Tool Index

**Last updated:** 2026-08-15  
**Purpose:** Central reference for all available MCP servers and tools in the agentic-tool-loop project.

---

## Quick Navigation

| Need | Primary MCP Server | Key Tools |
|------|-------------------|-----------|
| Repository inspection | `aicarmine-codex-app` | `repo_tree`, `repo_read`, `repo_status`, `repo_list_files` |
| File/content search | `aicarmine-repo-search-det` | `search_fd`, `search_rg`, `search_jq` |
| Code validation | `aicarmine-repo-validate` | `ruff`, `pyright`, `diffcheck`, `semgrep` |
| Code editing | `aicarmine-repo-code` | `propose_edit`, `apply_patch`, `unidiff_validate` |
| Git operations | `aicarmine-git-readonly` | `log`, `show`, `diff`, `blame` |
| Project memory | `aicarmine-project-memory` | `search`, `upsert_verified`, `supersede` |
| SQLite queries | `aicarmine-sqlite-readonly` | `query`, `schema`, `list_databases` |
| Semantic search | `aicarmine-rag` | `context`, `reindex` |
| RAG routing | `aicarmine-rag-router` | `analyze_query`, `consolidate_plan` |
| Job inspection | `aicarmine-job-artifact` | `events`, `final`, `tool_results` |
| Job HTML views | `aicarmine-job-view` | `render`, `ia_payload` |
| Context compression | `aicarmine-context-compressor` | `summarize`, `build_toc`, `compress_module` |
| Architecture analysis | `aicarmine-code-architect` | `analysis`, `metrics`, `patterns` |
| Agentic loop | `aicarmine-agentic-loop-client` | `run`, `status`, `result` |
| Subagent execution | `aicarmine-local-subagent` | `run_readonly` |
| LLM generation | `aicarmine-ollama` | `generate`, `generate_stream` |
| Refactoring | `aicarmine-refactor` | `extract_function`, `rename_symbol` |
| Test coverage | `aicarmine-test-coverage` | `file_coverage`, `module_coverage` |
| Performance profiling | `aicarmine-performance-profiling` | `hotspots`, `complexity` |
| API documentation | `aicarmine-api-documentation` | `signatures`, `classes` |
| Lifecycle management | `aicarmine-lifecycle` | `deprecation_scan`, `tech_debt_ledger` |
| Network monitoring | `aicarmine-network-monitor` | `capture_start`, `threat_list` |
| Symbol RAG | `aicarmine-symbol-rag` | `build`, `search` |
| Service state | `aicarmine-codex-ops` | `snapshot`, `processes`, `logs` |

---

## Server Details

### 1. aicarmine-codex-app
**Path:** `services/codex_bridge/mcp_server.py`  
**Transport:** stdio  
**Category:** Repository operations + Memory  

#### Tools
| Tool Name | Read/Write | Purpose |
|-----------|------------|---------|
| `aicarmine_bridge_health` | Read | MCP health check |
| `terminal_list_files` | Read | Direct file listing |
| `terminal_search_files` | Read | Direct file search |
| `planner_scratchpad_write` | Write | Planner scratchpad memory |
| `runtime_sqlite_memory_write` | Write | Runtime SQLite memory |
| `aicarmine_repo_capabilities` | Read | Repo capability map |
| `aicarmine_repo_status` | Read | Git/repository status |
| `aicarmine_repo_tree` | Read | Bounded repository tree |
| `aicarmine_repo_list_files` | Read | File listing under path |
| `aicarmine_repo_search` | Read | Broker-managed repository search |
| `aicarmine_repo_rg_search` | Read | Ripgrep-style search |
| `aicarmine_repo_fd_files` | Read | FD-style file discovery |
| `aicarmine_repo_read` | Read | Read one or more files |
| `aicarmine_repo_ast_grep_search` | Read | AST-grep search |
| `aicarmine_repo_ast_grep_dry_run` | Read | AST-grep dry-run |
| `aicarmine_repo_tree_sitter_parse` | Read | Tree-sitter parse |
| `aicarmine_repo_ctags_symbols` | Read | Ctags symbol extraction |
| `aicarmine_repo_jq_query` | Read | JSON jq query |
| `aicarmine_repo_propose_code_edit` | Report-only | Code edit proposal (report) |
| `aicarmine_repo_unidiff_validate` | Validate | Unified diff validation |
| `aicarmine_repo_git_apply_check` | Check | Git apply patch check |
| `aicarmine_repo_apply_patch` | Write | Apply old_text/new_text patch |
| `aicarmine_repo_validate` | Validate | Broker-defined validation |
| `aicarmine_repo_ruff_check` | Validate | Ruff check |
| `aicarmine_repo_pyright_check` | Validate | Pyright check |
| `aicarmine_repo_pytest_run` | Execute | Pytest runner |
| `aicarmine_repo_shellcheck` | Validate | Shellcheck |
| `aicarmine_repo_semgrep_scan` | Validate | Semgrep scan |
| `aicarmine_jobs_status` | Read | Agent job artifacts |
| `aicarmine_job_detail` | Read | Job artifact detail |
| `aicarmine_memory_report` | Read | Operational/persistent memory |

---

### 2. aicarmine-repo-search-det
**Path:** `services/codex_bridge/repo_search_det_mcp_server.py`  
**Transport:** stdio  
**Category:** Deterministic search  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `aicarmine_repo_search_fd_health` | Health check |
| `aicarmine_repo_search_fd` | Find files with fd |
| `aicarmine_repo_search_rg` | Search contents with ripgrep (JSON output) |
| `aicarmine_repo_search_jq` | Run jq against JSON |
| `aicarmine_repo_search_ast_grep` | AST-grep search |
| `aicarmine_repo_search_ast_grep_dry_run` | AST-grep rewrite dry-run |
| `aicarmine_repo_search_tree_sitter_parse` | Parse with tree-sitter |
| `aicarmine_repo_search_ctags` | Universal-ctags JSON symbols |

---

### 3. aicarmine-repo-validate
**Path:** `services/codex_bridge/repo_validate_mcp_server.py`  
**Transport:** stdio  
**Category:** Code validation  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `aicarmine_repo_validate_health` | Health check |
| `aicarmine_repo_validate_diffcheck` | git diff --check |
| `aicarmine_repo_validate_ruff` | Ruff check with JSON diagnostics |
| `aicarmine_repo_validate_pyright` | Pyright with JSON diagnostics |
| `aicarmine_repo_validate_pytest` | Pytest on selected paths |
| `aicarmine_repo_validate_shellcheck` | Shellcheck JSON diagnostics |
| `aicarmine_repo_validate_semgrep` | Semgrep JSON diagnostics |
| `aicarmine_repo_validate_probe_profiles` | List probe profiles |
| `aicarmine_repo_validate_probe_run` | Run probe profile |

---

### 4. aicarmine-repo-code
**Path:** `services/codex_bridge/repo_code_mcp_server.py`  
**Transport:** stdio  
**Category:** Code editing (report-only + guarded write)  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `aicarmine_repo_code_health` | Health check |
| `aicarmine_repo_code_propose_edit` | Report-only code edit proposal |
| `aicarmine_repo_code_unidiff_validate` | Validate unified diff |
| `aicarmine_repo_code_git_apply_check` | Git apply --check |
| `aicarmine_repo_code_apply_patch` | Apply patch (requires allow_source_write=true) |

---

### 5. aicarmine-git-readonly
**Path:** `services/codex_bridge/git_readonly_mcp_server.py`  
**Transport:** stdio  
**Category:** Git read-only operations  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `aicarmine_git_readonly_health` | Health check |
| `aicarmine_git_readonly_log` | Recent commits (structured format) |
| `aicarmine_git_readonly_show` | One commit with stat/patch |
| `aicarmine_git_readonly_diff` | Bounded git diff |
| `aicarmine_git_readonly_blame` | Line blame for repo file |
| `aicarmine_git_readonly_branch_compare` | Branch comparison |

---

### 6. aicarmine-project-memory
**Path:** `services/codex_bridge/project_memory_mcp_server.py`  
**Transport:** stdio  
**Category:** Project-local persistent memory  

#### Tools
| Tool Name | Read/Write | Purpose |
|-----------|------------|---------|
| `aicarmine_project_memory_health` | Read | Health check |
| `aicarmine_project_memory_search` | Read | Search memory records |
| `aicarmine_project_memory_get` | Read | Get memory record by ID |
| `aicarmine_project_memory_upsert_verified` | Write | Write/re-verify memory record |
| `aicarmine_project_memory_mark_stale` | Write | Mark record stale |
| `aicarmine_project_memory_supersede` | Write | Supersede record |
| `aicarmine_project_memory_audit_sources` | Read | Audit source references |

---

### 7. aicarmine-sqlite-readonly
**Path:** `services/codex_bridge/sqlite_readonly_mcp_server.py`  
**Transport:** stdio  
**Category:** SQLite read-only queries  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `aicarmine_sqlite_readonly_health` | Health check |
| `aicarmine_sqlite_readonly_list_databases` | List allowlisted databases |
| `aicarmine_sqlite_readonly_schema` | Read table/view schema |
| `aicarmine_sqlite_readonly_query` | Run bounded SELECT query |

---

### 8. aicarmine-rag
**Path:** `services/codex_bridge/rag_mcp_server.py`  
**Transport:** stdio  
**Category:** RAG indexing and semantic search  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `aicarmine_rag_context` | Search RAG index + optional rerank |
| `aicarmine_rag_index_status` | Inspect RAG index status |
| `aicarmine_rag_reindex` | Update RAG SQLite index |

---

### 9. aicarmine-rag-router
**Path:** `services/codex_bridge/rag_router_mcp_server.py`  
**Transport:** stdio  
**Category:** Multi-database RAG routing  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `rag_router_list_dbs` | List available RAG databases |
| `rag_router_list_cross_refs` | List cross-references |
| `rag_router_list_topics` | List topic categories |
| `rag_router_analyze_query` | Analyze query + suggest databases |
| `rag_router_consolidate_plan` | Create consolidated query plan |
| `rag_router_get_relevant_dbs` | Get relevant DBs for topic |
| `rag_router_get_knowledge_summary` | Comprehensive summary |

---

### 10. aicarmine-job-artifact
**Path:** `services/codex_bridge/job_artifact_mcp_server.py`  
**Transport:** stdio  
**Category:** Job artifact inspection  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `aicarmine_job_artifact_health` | Health check |
| `aicarmine_job_artifact_list_jobs` | List persisted agent jobs |
| `aicarmine_job_artifact_summary` | Summarize one job |
| `aicarmine_job_artifact_events` | Read filtered events |
| `aicarmine_job_artifact_final` | Read final.json and final.md |
| `aicarmine_job_artifact_tool_results` | List/read tool-result artifacts |
| `aicarmine_job_artifact_subturns` | Read support-subturn events |
| `aicarmine_job_artifact_planner_payload` | Read planner prompts |
| `aicarmine_job_artifact_rejections` | Extract rejection events |

---

### 11. aicarmine-job-view
**Path:** `services/codex_bridge/job_view_mcp_server.py`  
**Transport:** stdio  
**Category:** Job HTML view rendering  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `aicarmine_job_view_health` | Health check |
| `aicarmine_job_view_list_views` | List available views |
| `aicarmine_job_view_render` | Render one job HTML view |
| `aicarmine_job_view_render_section` | Render section fragment |
| `aicarmine_job_view_ia_payload` | Read IA live control payload |
| `aicarmine_job_view_outline` | Render HTML outline |
| `aicarmine_job_view_links` | Extract links and sections |
| `aicarmine_job_view_validate_html` | Structural/safety checks |

---

### 12. aicarmine-codex-ops
**Path:** `services/codex_bridge/ops_mcp_server.py`  
**Transport:** stdio  
**Category:** Operations and service state  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `aicarmine_codex_ops_health` | Health check |
| `aicarmine_mcp_inventory_health` | MCP server inventory health |
| `aicarmine_mcp_inventory_list_targets` | List MCP server targets |
| `aicarmine_mcp_inventory_probe` | Stdio initialize/list probes |
| `aicarmine_service_state_health` | Service scope report |
| `aicarmine_service_state_ports` | Read listening sockets |
| `aicarmine_service_state_processes` | Process command lines |
| `aicarmine_service_state_logs` | Log file tails |
| `aicarmine_service_state_snapshot` | Combined snapshot |

---

### 13. aicarmine-local-subagent
**Path:** `services/codex_bridge/local_subagent_mcp_server.py`  
**Transport:** stdio  
**Category:** Local subagent execution  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `aicarmine_local_subagent_health` | Health check |
| `aicarmine_local_subagent_capabilities` | Capabilities description |
| `aicarmine_local_subagent_run_readonly` | Bounded read-only task |

---

### 14. aicarmine-agentic-loop-client
**Path:** `services/codex_bridge/agentic_loop_client_mcp_server.py`  
**Transport:** stdio  
**Category:** Agentic loop client (broker control)  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `aicarmine_agentic_loop_health` | Health check |
| `aicarmine_agentic_loop_capabilities` | Capabilities description |
| `aicarmine_agentic_loop_ensure_reranker` | Ensure BGE reranker ready |
| `aicarmine_agentic_loop_ensure_broker` | Ensure dedicated broker running |
| `aicarmine_agentic_loop_run` | Start agentic-loop job |
| `aicarmine_agentic_loop_status` | Fetch job status |
| `aicarmine_agentic_loop_result` | Fetch job terminal result |

---

### 15. aicarmine-ollama
**Path:** `services/codex_bridge/ollama_subagent_mcp_server.py`  
**Transport:** stdio  
**Category:** Ollama LLM generation  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `aicarmine_ollama_subagent_health` | Health check |
| `aicarmine_ollama_subagent_generate` | Generate text via Ollama |
| `aicarmine_ollama_subagent_generate_stream` | Stream generation |
| `aicarmine_ollama_subagent_list_models` | List available models |

---

### 16. aicarmine-batch
**Path:** `services/codex_bridge/mcp_batch_proxy_server.py`  
**Transport:** stdio  
**Category:** Batch MCP operations  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `batch_execute` | Execute batch of MCP tool calls |
| `health_check` | Batch server health |
| `mcp_batch_health` | MCP batch health |
| `mcp_batch_list_servers` | List available MCP servers |
| `mcp_batch_execute` | MCP batch operation |

---

### 17. aicarmine-repo-state
**Path:** `services/codex_bridge/repo_state_mcp_server.py`  
**Transport:** stdio  
**Category:** Repository state inspection  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `aicarmine_repo_state_health` | Health report |
| `aicarmine_repo_state_status` | Deterministic repo status |
| `aicarmine_repo_state_capabilities` | Deterministic capabilities |

---

### 18. aicarmine-refactor
**Path:** `services/codex_bridge/refactor_mcp_server.py`  
**Transport:** stdio  
**Category:** Code refactoring  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `git_list_tracked_files` | List tracked files |
| `refactor_add_parameter` | Add function parameter |
| `refactor_extract_function` | Extract code into function |
| `refactor_health` | Health check |
| `refactor_rename_project` | Rename project references |
| `refactor_rename_project_bowler` | Rename using bowler |
| `refactor_rename_symbol` | Rename symbol |
| `refactor_rename_symbol_rope` | Rename using rope |

---

### 19. aicarmine-network-monitor
**Path:** `services/codex_bridge/network_monitor_mcp_server.py`  
**Transport:** stdio  
**Category:** Network monitoring  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `network_monitor_health` | Health check |
| `network_list_interfaces` | List network interfaces |
| `network_capture_start` | Start packet capture |
| `network_capture_stop` | Stop packet capture |
| `network_capture_status` | Get capture status |
| `network_threat_list` | List threats |
| `network_threat_get` | Get threat details |
| `network_firewall_block` | Add firewall block rule |
| `network_firewall_unblock` | Remove firewall block rule |
| `network_firewall_list_rules` | List firewall rules |
| `network_firewall_remove_rule` | Remove firewall rule |

---

### 20. aicarmine-symbol-rag
**Path:** `services/codex_bridge/symbol_rag_mcp_server.py`  
**Transport:** stdio  
**Category:** Symbol-level RAG  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `aicarmine_symbol_rag_health` | Health check |
| `aicarmine_symbol_rag_build` | Build symbol RAG index |
| `aicarmine_symbol_rag_search` | Search symbol RAG index |
| `aicarmine_symbol_rag_status` | Get symbol RAG status |

---

### 21. aicarmine-context-compressor
**Path:** `services/codex_bridge/context_compressor_mcp_server.py`  
**Transport:** stdio  
**Category:** Context window compression  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `aicarmine_context_compressor_health` | Health check |
| `aicarmine_context_compressor_summarize` | Summarize large file |
| `aicarmine_context_compressor_build_toc` | Build table of contents |
| `aicarmine_context_compressor_get_budget` | Get context budget allocation |
| `aicarmine_context_compressor_compress_module` | Compress module directory |
| `aicarmine_context_compressor_get_context_usage` | Track token usage |

---

### 22. aicarmine-code-architect
**Path:** `services/codex_bridge/code_architect_mcp_server.py`  
**Transport:** stdio  
**Category:** Architecture analysis  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `aicarmine_code_architect_health` | Health check |
| `aicarmine_code_architect_dependency_graph` | Build dependency graph |
| `aicarmine_code_architect_analysis` | Analyze architecture patterns |
| `aicarmine_code_architect_metrics` | Coupling and cohesion metrics |
| `aicarmine_code_architect_patterns` | Detect design patterns |
| `aicarmine_code_architect_module_boundaries` | Suggest module boundaries |
| `aicarmine_code_architect_complexity` | Cyclomatic complexity analysis |

---

### 23. aicarmine-test-coverage
**Path:** `services/codex_bridge/test_coverage_mcp_server.py`  
**Transport:** stdio  
**Category:** Test coverage analysis  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `aicarmine_test_coverage_health` | Health check |
| `aicarmine_test_coverage_file` | Coverage for specific file |
| `aicarmine_test_coverage_module` | Coverage for module |
| `aicarmine_test_coverage_gaps` | Uncovered code regions |
| `aicarmine_test_coverage_pytest_report` | pytest-style report |
| `aicarmine_test_coverage_summary` | Overall coverage summary |

---

### 24. aicarmine-performance-profiling
**Path:** `services/codex_bridge/performance_profiling_mcp_server.py`  
**Transport:** stdio  
**Category:** Performance profiling  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `aicarmine_performance_profiling_health` | Health check |
| `aicarmine_performance_profiling_complexity` | Algorithmic complexity |
| `aicarmine_performance_profiling_hotspots` | Memory hotspots |
| `aicarmine_performance_profiling_patterns` | Execution patterns |
| `aicarmine_performance_profiling_benchmarks` | Benchmark suggestions |
| `aicarmine_performance_profiling_summary` | Overall performance summary |

---

### 25. aicarmine-api-documentation
**Path:** `services/codex_bridge/api_documentation_mcp_server.py`  
**Transport:** stdio  
**Category:** API documentation generation  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `aicarmine_api_documentation_health` | Health check |
| `aicarmine_api_documentation_signatures` | Function signature docs |
| `aicarmine_api_documentation_classes` | Class documentation |
| `aicarmine_api_documentation_modules` | Module-level docs |
| `aicarmine_api_documentation_readme_suggestions` | README suggestions |
| `aicarmine_api_documentation_quality` | Documentation quality score |

---

### 26. aicarmine-lifecycle
**Path:** `services/codex_bridge/lifecycle_mcp_server.py`  
**Transport:** stdio  
**Category:** Lifecycle management  

#### Tools
| Tool Name | Purpose |
|-----------|---------|
| `aicarmine_lifecycle_deprecation_scan` | Deprecated API scan |
| `aicarmine_lifecycle_dependency_matrix` | Dependency compatibility matrix |
| `aicarmine_lifecycle_tech_debt_ledger` | Technical debt ledger |
| `aicarmine_lifecycle_migration_plan` | Version migration plan |

---

## Tool Selection Guide

### Repository Work
```
Need to see what's in the repo?
  → aicarmine_repo_status (quick overview)
  → aicarmine_repo_tree (file structure)
  → aicarmine_repo_list_files (full file listing)

Need to find specific content?
  → aicarmine_repo_search (general search)
  → aicarmine_repo_rg_search (ripgrep-style)
  → aicarmine_repo_fd_files (file discovery)
  → aicarmine_repo_ast_grep_search (AST-based)

Need to read files?
  → aicarmine_repo_read (direct read)
```

### Code Modification
```
Need to propose changes?
  → aicarmine_repo_code_propose_edit (report-only proposal)
  → aicarmine_repo_unidiff_validate (validate diff before apply)

Need to apply changes?
  → aicarmine_repo_apply_patch (old_text/new_text)
  → aicarmine_repo_git_apply_check (verify first)
```

### Validation
```
Need to validate code quality?
  → aicarmine_repo_validate_ruff (Python linting)
  → aicarmine_repo_validate_pyright (type checking)
  → aicarmine_repo_validate_semgrep (security patterns)

Need to run tests?
  → aicarmine_repo_validate_pytest (pytest execution)
```

### Memory Operations
```
Need project memory?
  → aicarmine_project_memory_search (find records)
  → aicarmine_project_memory_get (read specific record)
  → aicarmine_project_memory_upsert_verified (write with evidence)

Need SQLite queries?
  → aicarmine_sqlite_readonly_query (bounded SELECT)
```

### Agentic Loop Control
```
Need to start a job?
  → aicarmine_agentic_loop_run (start agentic loop)
  → aicarmine_agentic_loop_status (check status)
  → aicarmine_agentic_loop_result (get result)

Need subagent analysis?
  → aicarmine_local_subagent_run_readonly (bounded read-only task)
```

---

## Cross-References

| Document | Location | Purpose |
|----------|----------|---------|
| AGENTS.md | Root | Operating rules and precedence |
| README.md | Root | Project index and flow map |
| FLOW_STRUCTURE.md | services/ | Architectural flow structure |
| MODULE_REFERENCE.md (per service) | services/*/ | Module-level technical reference |
| DEEP_DIVE documents | services/aicarmine_broker/application/* | Component-specific deep dives |
| CONTRACT documents | services/aicarmine_broker/application/* | Behavioral contracts |
| .clinerules/ | Root | Skill definitions |

---

## Notes

- All MCP servers use stdio transport unless otherwise noted
- Write tools require explicit confirmation (`confirm_*` parameters)
- Read-only tools are safe for analysis tasks
- Tool schemas may evolve; always verify current surface via `tools/list`