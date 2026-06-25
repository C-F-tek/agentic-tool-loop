# MCP Operational Summary & Complete Tool Inventory

**Date:** 2026-06-25  
**Repository:** c:/Users/carmi/AI (agentic-tool-loop)  
**Status:** Test/Debug phase — not production  
**Last Updated:** 2026-06-25T13:45Z — Deep scan of all MCP server source files completed

---

## 1. Source-of-Truth: Actual Tool Names from Server Source Files

Extracted via `Select-String -Pattern 'tools\["[^"]+"\]' *.py` across all MCP servers in `services/codex_bridge/`.

### 1.1 Complete Tool Inventory by Server (24 servers, 87 tools)

#### agentic_loop_client (7 tools)
| # | Tool Name |
|---|-----------|
| 1 | `aicarmine_agentic_loop_health` |
| 2 | `aicarmine_agentic_loop_capabilities` |
| 3 | `aicarmine_agentic_loop_ensure_reranker` |
| 4 | `aicarmine_agentic_loop_ensure_broker` |
| 5 | `aicarmine_agentic_loop_run` |
| 6 | `aicarmine_agentic_loop_status` |
| 7 | `aicarmine_agentic_loop_result` |

#### code_dep_graph (7 tools)
| # | Tool Name |
|---|-----------|
| 1 | `aicarmine_code_dep_health` |
| 2 | `aicarmine_code_build_dep_graph` |
| 3 | `aicarmine_code_find_import_chains` |
| 4 | `aicarmine_code_detect_circular_deps` |
| 5 | `aicarmine_code_find_callers` |
| 6 | `aicarmine_code_find_dependents` |
| 7 | `aicarmine_code_estimate_breakage_risk` |

#### enhanced_analysis (4 tools)
| # | Tool Name |
|---|-----------|
| 1 | `aicarmine_enhanced_health` |
| 2 | `aicarmine_code_summarize_module` |
| 3 | `aicarmine_code_api_surface` |
| 4 | `aicarmine_config_validator` |

#### git_readonly (6 tools)
| # | Tool Name |
|---|-----------|
| 1 | `aicarmine_git_readonly_health` |
| 2 | `aicarmine_git_readonly_log` |
| 3 | `aicarmine_git_readonly_show` |
| 4 | `aicarmine_git_readonly_diff` |
| 5 | `aicarmine_git_readonly_blame` |
| 6 | `aicarmine_git_readonly_branch_compare` |

#### index_bridge (5 tools)
| # | Tool Name |
|---|-----------|
| 1 | `aicarmine_index_bridge_health` |
| 2 | `aicarmine_index_bridge_build` |
| 3 | `aicarmine_index_bridge_query` |
| 4 | `aicarmine_index_bridge_persist` |
| 5 | `aicarmine_index_bridge_get_memory` |

#### job_artifact (9 tools)
| # | Tool Name |
|---|-----------|
| 1 | `aicarmine_job_artifact_health` |
| 2 | `aicarmine_job_artifact_list_jobs` |
| 3 | `aicarmine_job_artifact_summary` |
| 4 | `aicarmine_job_artifact_events` |
| 5 | `aicarmine_job_artifact_final` |
| 6 | `aicarmine_job_artifact_tool_results` |
| 7 | `aicarmine_job_artifact_subturns` |
| 8 | `aicarmine_job_artifact_planner_payload` |
| 9 | `aicarmine_job_artifact_rejections` |

#### job_view (8 tools)
| # | Tool Name |
|---|-----------|
| 1 | `aicarmine_job_view_health` |
| 2 | `aicarmine_job_view_list_views` |
| 3 | `aicarmine_job_view_render` |
| 4 | `aicarmine_job_view_render_section` |
| 5 | `aicarmine_job_view_ia_payload` |
| 6 | `aicarmine_job_view_outline` |
| 7 | `aicarmine_job_view_links` |
| 8 | `aicarmine_job_view_validate_html` |

#### local_subagent (3 tools)
| # | Tool Name |
|---|-----------|
| 1 | `aicarmine_local_subagent_health` |
| 2 | `aicarmine_local_subagent_capabilities` |
| 3 | `aicarmine_local_subagent_run_readonly` |

#### ollama_subagent (4 tools)
| # | Tool Name |
|---|-----------|
| 1 | `aicarmine_ollama_subagent_health` |
| 2 | `aicarmine_ollama_subagent_generate` |
| 3 | `aicarmine_ollama_subagent_generate_stream` |
| 4 | `aicarmine_ollama_subagent_list_models` |

#### project_memory (7 tools)
| # | Tool Name |
|---|-----------|
| 1 | `aicarmine_project_memory_health` |
| 2 | `aicarmine_project_memory_search` |
| 3 | `aicarmine_project_memory_get` |
| 4 | `aicarmine_project_memory_upsert_verified` |
| 5 | `aicarmine_project_memory_mark_stale` |
| 6 | `aicarmine_project_memory_supersede` |
| 7 | `aicarmine_project_memory_audit_sources` |

#### rag (3 tools)
| # | Tool Name |
|---|-----------|
| 1 | `aicarmine_rag_context` |
| 2 | `aicarmine_rag_index_status` |
| 3 | `aicarmine_rag_reindex` |

#### repo_code (5 tools)
| # | Tool Name |
|---|-----------|
| 1 | `aicarmine_repo_code_health` |
| 2 | `aicarmine_repo_code_propose_edit` |
| 3 | `aicarmine_repo_code_unidiff_validate` |
| 4 | `aicarmine_repo_code_git_apply_check` |
| 5 | `aicarmine_repo_code_apply_patch` |

#### repo_search_det (8 tools)
| # | Tool Name |
|---|-----------|
| 1 | `aicarmine_repo_search_det_health` |
| 2 | `aicarmine_repo_search_fd` |
| 3 | `aicarmine_repo_search_rg` |
| 4 | `aicarmine_repo_search_jq` |
| 5 | `aicarmine_repo_search_ast_grep` |
| 6 | `aicarmine_repo_search_ast_grep_dry_run` |
| 7 | `aicarmine_repo_search_tree_sitter_parse` |
| 8 | `aicarmine_repo_search_ctags` |

#### repo_state (3 tools)
| # | Tool Name |
|---|-----------|
| 1 | `aicarmine_repo_state_health` |
| 2 | `aicarmine_repo_state_status` |
| 3 | `aicarmine_repo_state_capabilities` |

#### repo_symbol_index (4 tools)
| # | Tool Name |
|---|-----------|
| 1 | `aicarmine_repo_symbol_index_health` |
| 2 | `aicarmine_repo_symbol_index_build` |
| 3 | `aicarmine_repo_symbol_query` |
| 4 | `aicarmine_repo_symbol_summary` |

#### repo_validate (9 tools)
| # | Tool Name |
|---|-----------|
| 1 | `aicarmine_repo_validate_health` |
| 2 | `aicarmine_repo_validate_diffcheck` |
| 3 | `aicarmine_repo_validate_ruff` |
| 4 | `aicarmine_repo_validate_pyright` |
| 5 | `aicarmine_repo_validate_pytest` |
| 6 | `aicarmine_repo_validate_shellcheck` |
| 7 | `aicarmine_repo_validate_semgrep` |
| 8 | `aicarmine_repo_validate_probe_profiles` |
| 9 | `aicarmine_repo_validate_probe_run` |

#### sqlite_readonly (4 tools)
| # | Tool Name |
|---|-----------|
| 1 | `aicarmine_sqlite_readonly_health` |
| 2 | `aicarmine_sqlite_readonly_list_databases` |
| 3 | `aicarmine_sqlite_readonly_schema` |
| 4 | `aicarmine_sqlite_readonly_query` |

#### test_discovery (5 tools)
| # | Tool Name |
|---|-----------|
| 1 | `aicarmine_test_discovery_health` |
| 2 | `aicarmine_test_discover_patterns` |
| 3 | `aicarmine_test_find_uncovered` |
| 4 | `aicarmine_test_generate_scaffold` |
| 5 | `aicarmine_test_map_tests` |

#### refactor (8 tools — NO aicarmine_ prefix)
| # | Tool Name |
|---|-----------|
| 1 | `refactor_rename_symbol` |
| 2 | `refactor_rename_symbol_rope` |
| 3 | `refactor_add_parameter` |
| 4 | `refactor_extract_function` |
| 5 | `refactor_rename_project` |
| 6 | `refactor_rename_project_bowler` |
| 7 | `git_list_tracked_files` |
| 8 | `refactor_health` |

#### codex_ops (7 tools)
| # | Tool Name |
|---|-----------|
| 1 | `aicarmine_codex_ops_health` |
| 2 | `aicarmine_mcp_inventory_health` |
| 3 | `aicarmine_mcp_inventory_list_targets` |
| 4 | `aicarmine_mcp_inventory_probe` |
| 5 | `aicarmine_service_state_health` |
| 6 | `aicarmine_service_state_ports` |
| 7 | `aicarmine_service_state_processes` |
| 8 | `aicarmine_service_state_logs` |
| 9 | `aicarmine_service_state_snapshot` |

**Note:** codex_ops actually has 9 tools (not 7 as previously documented). The `aicarmine_service_state_*` tools are part of codex_ops server.

### 1.2 Formatting Servers (5 servers, tools not probed — use Cline built-in names)

| Server | Script | Notes |
|--------|--------|-------|
| `aicarmine_prettier` | `prettier_mcp_server.py` | Uses Cline `format_file` |
| `aicarmine_biome` | `biome_mcp_server.py` | Uses Cline `check_file` |
| `aicarmine_ruff` | `ruff_mcp_server.py` | Linting |
| `aicarmine_eslint` | `eslint_mcp_server.py` | Linting |
| `aicarmine_black` | `black_mcp_server.py` | Formatting |

---

## 2. Known Issues

All known issues have been resolved (2026-06-25).

| Issue | Status | Fix Applied |
|-------|--------|-------------|
| `project_memory` health failed | ✅ Fixed | `_path_is_under` → `path_is_under` (imported from repo_mcp_common) |
| `rag` had no health tool | ✅ Fixed | Added `aicarmine_rag_health` to TOOL_SCHEMAS and handlers dict |

---

## 3. OOP Refactoring Completed (2026-06-25)

### 3.1 domain/models.py — 10 Frozen Dataclasses Added

All functions in `repo_deterministic.py` now return typed dataclass instances instead of raw dicts.

### 3.2 repo_mcp_common.py — Centralized Helpers

All shared stdio MCP helpers centralized here: `json_dumps()`, `compact_text()`, `tool_content()`, `ok()`/`err()`, `safe_int()`, `read_tail()`, `diagnostic_preview()`, `json_compress()`, `smart_json_dumps()`, `decompress_tool_text()`.

---

## 4. Naming Convention Rules

| Server Category | Prefix Pattern | Example |
|-----------------|----------------|---------|
| Core/Repo/Data/Jobs/Ops | `aicarmine_` | `aicarmine_repo_search_rg` |
| Refactor | **NO prefix** | `refactor_rename_symbol` |
| Formatting | Cline built-in | `format_file`, `check_file` |

---

## 5. Completed Fixes (2026-06-25)

1. ✅ **Fixed `project_memory` health** — `_path_is_under` → `path_is_under` (imported from repo_mcp_common)
2. ✅ **Added `aicarmine_rag_health`** — Added to TOOL_SCHEMAS and handlers dict in rag_mcp_server.py
3. ✅ **Updated INSTRUCTIONS string** — Now mentions all 4 tools including health

## 6. Completed Fixes (2026-06-25)

1. ✅ **Fixed `project_memory` health** — `_path_is_under` → `path_is_under` (imported from repo_mcp_common)
2. ✅ **Added `aicarmine_rag_health`** — Added to TOOL_SCHEMAS and handlers dict in rag_mcp_server.py
3. ✅ **Updated INSTRUCTIONS string** — Now mentions all 4 tools including health

## 7. Formatting Servers Status

All 5 formatting servers confirmed as **Cline built-in tool wrappers** (no MCP tool definitions):

| Server | Script | Cline Tool | MCP Tools |
|--------|--------|------------|-----------|
| `aicarmine_prettier` | prettier_mcp_server.py | `format_file` | None |
| `aicarmine_biome` | biome_mcp_server.py | `check_file` | None |
| `aicarmine_ruff` | ruff_mcp_server.py | N/A | Uses `aicarmine_repo_validate_ruff` from repo_validate |
| `aicarmine_eslint` | eslint_mcp_server.py | N/A | Uses `aicarmine_repo_validate_*` from repo_validate |
| `aicarmine_black` | black_mcp_server.py | N/A | Uses `aicarmine_repo_validate_ruff` (Python) |

**Verification:** Zero `tools["..."] = ToolSpec(` definitions found in any formatting server file. These servers exist only as Cline configuration entries and are not independently probed via MCP protocol.
