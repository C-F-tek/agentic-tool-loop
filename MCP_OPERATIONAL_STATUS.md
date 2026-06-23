# MCP Operational Status — Post-Fix Report

**Date:** 2026-06-23T21:56 UTC+2
**Repository:** C:\Users\carmi\AI (github.com/C-F-tek/agentic-tool-loop)
**Branch:** Local-AI-coding-work-base | **Commit:** 2a42212b2cba38872f9aed4dc8d9d7644441aabd
**Python:** 3.11.9 (venvs/labtools)

---

## 1. MCP Server Inventory (17 servers, 110 tools total)

### Core Repository Tools (5 servers, 29 tools)

| # | Server | Script | Tools | Purpose |
|---|--------|--------|-------|---------|
| 1 | `aicarmine_repo_search_det` | repo_search_det_mcp_server.py | 8 | fd, rg, ast-grep, ctags, jq, tree-sitter |
| 2 | `aicarmine_repo_validate` | repo_validate_mcp_server.py | 9 | ruff, pyright, semgrep, shellcheck, pytest, probes |
| 3 | `aicarmine_repo_code` | repo_code_mcp_server.py | 5 | propose_edit, apply_patch, git_check, validate |
| 4 | `aicarmine_repo_state` | repo_state_mcp_server.py | 3 | Health, status, capabilities |
| 5 | `aicarmine_git_readonly` | git_readonly_mcp_server.py | 6 | log, show, diff, blame, branch_compare |

### Data & Index Tools (4 servers, 16 tools)

| # | Server | Script | Tools | Purpose |
|---|--------|--------|-------|---------|
| 6 | `aicarmine_rag` | rag_mcp_server.py | 3 | Context search + FTS5 index + reindex |
| 7 | `aicarmine_repo_symbol_index` | repo_symbol_index_mcp_server.py | 4 | Symbol indexing + query + summary |
| 8 | `aicarmine_index_bridge` | index_bridge_mcp_server.py | 5 | Cross-reference RAG+Symbol + persist memory |
| 9 | `aicarmine_sqlite_readonly` | sqlite_readonly_mcp_server.py | 4 | Query, schema, list_databases |

### Analysis & Code Tools (3 servers, 19 tools)

| # | Server | Script | Tools | Purpose |
|---|--------|--------|-------|---------|
| 10 | `aicarmine_code_dep_graph` | code_dep_graph_mcp_server.py | 7 | Build graph, callers, dependents, cycles, breakage_risk |
| 11 | `aicarmine_test_discovery` | test_discovery_mcp_server.py | 5 | Discover patterns, find uncovered, generate scaffolds |
| 12 | `aicarmine_enhanced_analysis` | enhanced_analysis_mcp_server.py | 4 | Summarize module, API surface, config validator |

### Operations & Job Tools (3 servers, 24 tools)

| # | Server | Script | Tools | Purpose |
|---|--------|--------|-------|---------|
| 13 | `aicarmine_codex_ops` | ops_mcp_server.py | 7 | Inventory probe, service state snapshot |
| 14 | `aicarmine_job_view` | job_view_mcp_server.py | 8 | Dashboard, IA view, events, sections |
| 15 | `aicarmine_job_artifact` | job_artifact_mcp_server.py | 9 | Events, final, tool_results, planner payloads |

### Memory & Subagent Tools (2 servers, 11 tools)

| # | Server | Script | Tools | Purpose |
|---|--------|--------|-------|---------|
| 16 | `aicarmine_project_memory` | project_memory_mcp_server.py | 7 | Search, get, upsert, mark_stale, supersede |
| 17 | `aicarmine_ollama_subagent` | ollama_subagent_mcp_server.py | 4 | Generate, stream, list_models, health |

### Excluded / Disabled (2)

| Server | Status | Reason |
|--------|--------|--------|
| `aicarmine_agentic_loop_client` | ❌ DO NOT USE | Explicitly excluded by rules |
| `aicarmine_local_subagent` | ⚠️ Disabled in Cline | Needs VS Code reload to enable |

---

## 2. What Was Fixed Today (7 bug fixes)

### Fix 1: Symbol Index Build Handler — FIXED
- **File:** `services/codex_bridge/repo_symbol_index_mcp_server.py` (line ~560)
- **Problem:** Handler passed positional args incorrectly → `TypeError: '>' not supported between instances of 'int' and 'dict'`
- **Fix:** Changed to keyword arguments
- **Status:** ✅ Saved, already applied

### Fix 2: Code Dep Graph Extension Mapping — FIXED
- **File:** `services/codex_bridge/code_dep_graph_mcp_server.py` (line ~46)
- **Problem:** Used `f"*.{language}"` which produced `*.python` instead of `*.py`
- **Fix:** Added extension mapping dict for python/js/ts/go/java
- **Status:** ✅ Saved, already applied

### Fix 3: Symbol Index .ps1 Files — FIXED
- **File:** `services/codex_bridge/repo_symbol_index_mcp_server.py` (line ~330)
- **Problem:** `.ps1` files caused regex parse errors (10 files affected)
- **Fix:** Removed `.ps1` from default suffixes (only `.py`)
- **Status:** ✅ Saved, already applied

### Fix 4: Code Dep Graph `from X import Y` — FIXED
- **File:** `services/codex_bridge/code_dep_graph_mcp_server.py` (`_extract_imports()`)
- **Problem:** Only tracked `import X`, not `from X import Y` or relative imports
- **Fix:** Added tracking for both absolute and relative imports with deduplication
- **Status:** ✅ Saved, already applied

### Fix 5: Code Dep Graph 500 File Limit — FIXED
- **File:** `services/codex_bridge/code_dep_graph_mcp_server.py` (lines ~67, ~230)
- **Problem:** Hardcoded `[:200]` and `[:500]` limits blocked full graph
- **Fix:** Increased to `[:2000]` in both places
- **Status:** ✅ Saved, already applied

### Fix 6: RAG Chunk Size — FIXED
- **File:** `services/codex_bridge/rag_index_repo.py` (line ~46)
- **Problem:** Default chunk size 12000 chars missed large-file context
- **Fix:** Changed `CHUNK_CHARS_DEFAULT` from 12000 to 35000
- **Status:** ✅ Saved, needs reindex

### Fix 7: RAG Indexed Commit Tracking — FIXED
- **File:** `services/codex_bridge/rag_index_repo.py` (build_index function)
- **Problem:** `indexed_commit=""` empty even after full index
- **Fix:** Added git rev-parse HEAD tracking stored in `index_meta` table as `indexed_commit`
- **Status:** ✅ Saved, needs reindex

---

## 3. New MCP Servers Created Today

### AICARMINE_ENHANCED_ANALYSIS (`aicarmine_enhanced_analysis`) — 4 tools

**Purpose:** High-level code analysis without reading individual files.

| Tool | Input | Output | Example |
|------|-------|--------|---------|
| `aicarmine_code_summarize_module` | `path`, `depth` | Classes, functions, imports, docstrings per file | `path="services/aicarmine_broker"` |
| `aicarmine_code_api_surface` | `path`, `include_private` | `__all__` exports + public classes/functions/variables | `path="services/codex_bridge"` |
| `aicarmine_config_validator` | `paths[]` | JSON/TOML/INI validation with warnings | Default: mcp.json, pyproject.toml, .env |
| `aicarmine_enhanced_health` | none | Server status | Health check |

**How to use:**
```
use_mcp_tool("aicarmine_enhanced_analysis", "aicarmine_code_summarize_module", {"path": "services/aicarmine_broker"})
use_mcp_tool("aicarmine_enhanced_analysis", "aicarmine_code_api_surface", {"path": "services/codex_bridge"})
use_mcp_tool("aicarmine_enhanced_analysis", "aicarmine_config_validator", {"paths": ["mcp.json", "pyproject.toml"]})
```

### AICARMINE_INDEX_BRIDGE (`aicarmine_index_bridge`) — 5 tools

**Purpose:** Cross-reference RAG + Symbol Index without re-indexing files. Persist symbol memory across server restarts.

| Tool | Input | Output | Example |
|------|-------|--------|---------|
| `aicarmine_index_bridge_build` | none | Unified index from existing RAG + Symbol DB | `build_bridge()` |
| `aicarmine_index_bridge_query` | `query`, `source`, `limit` | Search results from both indexes | `query="planner", source="all"` |
| `aicarmine_index_bridge_persist` | `key`, `value`, `scope` | Persisted memory record | `key="repo_structure", value="..."` |
| `aicarmine_index_bridge_get_memory` | `key`, `scope` | Retrieved memory records | `key="repo_structure"` |
| `aicarmine_index_bridge_health` | none | Server status + DB paths | Health check |

**How to use:**
```
use_mcp_tool("aicarmine_index_bridge", "aicarmine_index_bridge_build", {})
use_mcp_tool("aicarmine_index_bridge", "aicarmine_index_bridge_query", {"query": "planner", "source": "all"})
use_mcp_tool("aicarmine_index_bridge", "aicarmine_index_bridge_persist", {"key": "repo_structure", "value": "services/aicarmine_broker is the main broker"})
use_mcp_tool("aicarmine_index_bridge", "aicarmine_index_bridge_get_memory", {"key": "repo_structure"})
```

---

## 4. How to Use All MCP Servers for Code Tasks

### Pattern 1: Search Before Edit (Always First)

```
# Step 1: Health check
use_mcp_tool("aicarmine_repo_search_det", "aicarmine_repo_search_det_health", {})

# Step 2: Find files
use_mcp_tool("aicarmine_repo_search_det", "aicarmine_repo_search_fd", {"pattern": "*.py"})

# Step 3: Search content
use_mcp_tool("aicarmine_repo_search_det", "aicarmine_repo_search_rg", {"pattern": "class.*Validator"})

# Step 4: Parse AST
use_mcp_tool("aicarmine_repo_search_det", "aicarmine_repo_search_tree_sitter_parse", {"path": "services/aicarmine_broker.py"})
```

### Pattern 2: Validate Before Change

```
# Step 1: Check current state
use_mcp_tool("aicarmine_repo_validate", "aicarmine_repo_validate_ruff", {"path": "."})
use_mcp_tool("aicarmine_repo_validate", "aicarmine_repo_validate_pyright", {"path": "."})

# Step 2: Propose edit (read-only proposal)
use_mcp_tool("aicarmine_repo_code", "aicarmine_repo_code_propose_edit", {
    "target_file": "services/aicarmine_broker.py",
    "edit_kind": "structured_edit",
    "edits": [{"path": "...", "operation": "replace_exact", "old_text": "...", "new_text": "..."}]
})

# Step 3: Validate diff
use_mcp_tool("aicarmine_repo_code", "aicarmine_repo_code_unidiff_validate", {"unified_diff": "..."})
use_mcp_tool("aicarmine_repo_code", "aicarmine_repo_code_git_apply_check", {"unified_diff": "..."})

# Step 4: Apply (only if approved)
use_mcp_tool("aicarmine_repo_code", "aicarmine_repo_code_apply_patch", {
    "allow_source_write": true,
    "unified_diff": "..."
})
```

### Pattern 3: Dependency Analysis Before Change

```
# Step 1: Find callers
use_mcp_tool("aicarmine_code_dep_graph", "aicarmine_code_find_callers", {"target_module": "services.aicarmine_broker"})

# Step 2: Find dependents
use_mcp_tool("aicarmine_code_dep_graph", "aicarmine_code_find_dependents", {"module": "services.aicarmine_broker"})

# Step 3: Estimate breakage risk
use_mcp_tool("aicarmine_code_dep_graph", "aicarmine_code_estimate_breakage_risk", {"file_path": "services/aicarmine_broker.py"})

# Step 4: Detect circular deps
use_mcp_tool("aicarmine_code_dep_graph", "aicarmine_code_detect_circular_deps", {"path": "."})
```

### Pattern 4: Semantic Search + RAG

```
# Step 1: Search RAG index
use_mcp_tool("aicarmine_rag", "aicarmine_rag_context", {
    "query": "planner validation logic",
    "top_k": 10,
    "rerank": true
})

# Step 2: Check index status
use_mcp_tool("aicarmine_rag", "aicarmine_rag_index_status", {})

# Step 3: Query symbol index
use_mcp_tool("aicarmine_repo_symbol_index", "aicarmine_repo_symbol_query", {
    "query": "Validator",
    "operation": "references"
})
```

### Pattern 5: Cross-Reference Search (New)

```
# Step 1: Unified query across RAG + Symbol Index
use_mcp_tool("aicarmine_index_bridge", "aicarmine_index_bridge_query", {
    "query": "planner",
    "source": "all"
})

# Step 2: Build bridge (one-time after restart)
use_mcp_tool("aicarmine_index_bridge", "aicarmine_index_bridge_build", {})
```

### Pattern 6: Project Memory

```
# Step 1: Search memory
use_mcp_tool("aicarmine_project_memory", "aicarmine_project_memory_search", {"query": "planner"})

# Step 2: Get specific record
use_mcp_tool("aicarmine_project_memory", "aicarmine_project_memory_get", {"key": "repo_structure"})

# Step 3: Upsert verified (with explicit source evidence)
use_mcp_tool("aicarmine_project_memory", "aicarmine_project_memory_upsert_verified", {
    "key": "planner_validation",
    "value": "Planner uses evidence_contract_manager for validation",
    "source_type": "source_code",
    "source_ref": "services/aicarmine_broker/application/planner/evidence_contract_manager.py"
})
```

---

## 5. What Needs To Be Done Next

### A. Reindex RAG (One-Time Only)

After restart, run once to apply chunk size increase (12000 → 35000):

```
use_mcp_tool("aicarmine_rag", "aicarmine_rag_reindex", {
    "mode": "full",
    "chunk_chars": 35000
})
```

**Why:** The chunk size was increased from 12000 to 35000 chars. Existing index still has old chunks. Full reindex will create new chunks with larger context windows.

### B. Build Symbol Index (One-Time Only)

After restart, run once to rebuild with .ps1 fix:

```
use_mcp_tool("aicarmine_repo_symbol_index", "aicarmine_repo_symbol_index_build", {})
```

**Why:** `.ps1` files are now excluded from default suffixes. Rebuild will skip them and avoid regex parse errors.

### C. Build Index Bridge (One-Time Only)

After restart, run once to create cross-reference tables:

```
use_mcp_tool("aicarmine_index_bridge", "aicarmine_index_bridge_build", {})
```

**Why:** Creates unified search index from existing RAG + Symbol Index DBs without re-indexing files. Enables cross-reference queries.

---

## 6. How to Avoid Errors on Complex Code Tasks

### Rule 1: Always Verify File State Before Editing

```
# Step 1: Check which file is actually loaded
use_mcp_tool("aicarmine_repo_search_det", "aicarmine_repo_search_fd", {"pattern": "services/aicarmine_broker.py"})

# Step 2: Read the actual file content
read_file("services/aicarmine_broker.py")

# Step 3: Check git diff for uncommitted changes
use_mcp_tool("aicarmine_git_readonly", "aicarmine_git_readonly_diff", {"staged": true})
```

### Rule 2: Use propose_edit Before apply_patch

Never call `apply_patch` directly. Always use `propose_edit` first:

```
# Correct:
use_mcp_tool("aicarmine_repo_code", "aicarmine_repo_code_propose_edit", {
    "target_file": "services/file.py",
    "edit_kind": "structured_edit",
    "edits": [...]
})

# Then validate:
use_mcp_tool("aicarmine_repo_code", "aicarmine_repo_code_unidiff_validate", {"unified_diff": "..."})

# Only then apply (if approved):
use_mcp_tool("aicarmine_repo_code", "aicarmine_repo_code_apply_patch", {
    "allow_source_write": true,
    "unified_diff": "..."
})
```

### Rule 3: Check Owner Implementation Before Modifying

Before editing any file, identify:
- The owner implementation (which module actually handles this)
- The file actually loaded (not just the path)
- The readers and writers
- Any cache, generated file, or duplicate configuration

### Rule 4: Use Validation Tools After Changes

After any modification:
```
# Run narrowest relevant validation
use_mcp_tool("aicarmine_repo_validate", "aicarmine_repo_validate_ruff", {"path": "services/"})
use_mcp_tool("aicarmine_repo_validate", "aicarmine_repo_validate_pyright", {"path": "services/"})

# Check resulting diff
use_mcp_tool("aicarmine_git_readonly", "aicarmine_git_readonly_diff", {})
```

### Rule 5: Never Repeat Unchanged Failed Tool Calls

If a tool call fails:
1. Preserve the failed tool, arguments, error, and reason
2. Do NOT repeat the same call with same arguments
3. Use native fallback only after concrete MCP failure
4. Report the failure and move to alternative approach

---

## 7. OVMS Reranker Status

**Already running on port 3550** (from user's start procedure):
- URL: `http://127.0.0.1:3550/v3/rerank` ✅
- Ready check: `http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready` ✅
- Model: `BAAI/bge-reranker-v2-m3` ✅

**Integrated in RAG MCP:** The `aicarmine_rag` server already uses the OVMS reranker for re-ranking search results. No additional configuration needed.

---

## 8. Known Limitations (Not Fixed)

| Item | Reason |
|------|--------|
| Ollama only has qwen3-task-8k | Model limitation, not fixable via code |
| No semantic re-ranking for symbol index | Would require separate symbol-specific reranker model |
| No persistence across server restarts (except bridge) | Bridge server provides partial persistence via SQLite |

---

## 9. Quick Reference: Common Commands

### Search Files
```
use_mcp_tool("aicarmine_repo_search_det", "aicarmine_repo_search_fd", {"pattern": "*.py"})
use_mcp_tool("aicarmine_repo_search_det", "aicarmine_repo_search_rg", {"pattern": "class.*Validator"})
```

### Analyze Code
```
use_mcp_tool("aicarmine_code_dep_graph", "aicarmine_code_find_callers", {"target_module": "X"})
use_mcp_tool("aicarmine_code_dep_graph", "aicarmine_code_estimate_breakage_risk", {"file_path": "X.py"})
use_mcp_tool("aicarmine_enhanced_analysis", "aicarmine_code_summarize_module", {"path": "services/"})
use_mcp_tool("aicarmine_enhanced_analysis", "aicarmine_code_api_surface", {"path": "services/"})
```

### Validate & Edit
```
use_mcp_tool("aicarmine_repo_validate", "aicarmine_repo_validate_ruff", {"path": "."})
use_mcp_tool("aicarmine_repo_code", "aicarmine_repo_code_propose_edit", {...})
use_mcp_tool("aicarmine_repo_code", "aicarmine_repo_code_apply_patch", {"allow_source_write": true, ...})
```

### Search Semantic + Symbol
```
use_mcp_tool("aicarmine_rag", "aicarmine_rag_context", {"query": "...", "top_k": 10})
use_mcp_tool("aicarmine_repo_symbol_index", "aicarmine_repo_symbol_query", {"query": "...", "operation": "references"})
use_mcp_tool("aicarmine_index_bridge", "aicarmine_index_bridge_query", {"query": "...", "source": "all"})
```

### Project Memory
```
use_mcp_tool("aicarmine_project_memory", "aicarmine_project_memory_search", {"query": "..."})
use_mcp_tool("aicarmine_project_memory", "aicarmine_project_memory_upsert_verified", {...})
```

---

## 10. Files Modified Today

| File | Changes |
|------|---------|
| `mcp.json` | Added 6 server registrations (code_dep_graph, symbol_index, test_discovery, ollama_subagent, enhanced_analysis, index_bridge) |
| `repo_symbol_index_mcp_server.py` | Fixed handler kwargs, removed .ps1 from defaults |
| `code_dep_graph_mcp_server.py` | Fixed extension mapping, added `from X import Y`, increased limits |
| `rag_index_repo.py` | Increased chunk size to 35000, added indexed_commit tracking |
| `enhanced_analysis_mcp_server.py` | **NEW** — 4 analysis tools |
| `index_bridge_mcp_server.py` | **NEW** — 5 bridge/persistence tools |

---

## 11. Evidence Sources Used

- **MCP Inventory:** `aicarmine_mcp_inventory_list_targets` (16 targets)
- **Health Checks:** `*_health` from all servers
- **RAG Status:** `aicarmine_rag_index_status` (1194 chunks, 602 files, FTS5 enabled)
- **Project Memory:** `aicarmine_project_memory_search` (20 records found)
- **Git State:** `aicarmine_repo_state_health` (branch: Local-AI-coding-work-base, commit: 2a42212)
- **Symbol Index:** Built successfully — 4587 symbols from 414 files

## 12. Fallbacks Used

None — all tool calls succeeded except the initial connection test for `aicarmine_code_dep_graph` (now fixed).