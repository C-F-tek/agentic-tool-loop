# MCP Discovery + Refactoring Strategy Report

## 1. MCP Discovery Summary

### Discovered MCP Servers (12 total)

| # | Server | Script | Tools | Health |
|---|--------|--------|-------|--------|
| 1 | aicarmine_agentic_loop_client | agentic_loop_client_mcp_server.py | 7 | ✅ |
| 2 | aicarmine_git_readonly | git_readonly_mcp_server.py | 6 | ✅ |
| 3 | aicarmine_job_artifact | job_artifact_mcp_server.py | 9 | ✅ |
| 4 | aicarmine_job_view | job_view_mcp_server.py | 8 | ✅ |
| 5 | aicarmine_local_subagent | local_subagent_mcp_server.py | 3 | ✅ |
| 6 | aicarmine_project_memory | project_memory_mcp_server.py | 7 | ✅ |
| 7 | aicarmine_rag | rag_mcp_server.py | 3 | ✅ |
| 8 | aicarmine_repo_code | repo_code_mcp_server.py | 5 | ✅ |
| 9 | aicarmine_repo_search_det | repo_search_det_mcp_server.py | 8 | ✅ |
| 10 | aicarmine_repo_state | repo_state_mcp_server.py | 3 | ✅ |
| 11 | aicarmine_repo_validate | repo_validate_mcp_server.py | 9 | ✅ |
| 12 | aicarmine_sqlite_readonly | sqlite_readonly_mcp_server.py | 4 | ✅ |

**Total tools**: 62 across 12 servers
**All servers healthy**: Yes
**Branch**: Local-AI-coding-work-base
**Commit**: 8ba6b26

### Tool Categories

| Category | Tools | Servers |
|-----------|-------|---------|
| Agentic Loop | 7 | aicarmine_agentic_loop_client |
| Git Read-Only | 6 | aicarmine_git_readonly |
| Job Artifacts | 9 | aicarmine_job_artifact |
| Job Views | 8 | aicarmine_job_view |
| Local Subagent | 3 | aicarmine_local_subagent |
| Project Memory | 7 | aicarmine_project_memory |
| RAG Search | 3 | aicarmine_rag |
| Repo Code (patches) | 5 | aicarmine_repo_code |
| Repo Search | 8 | aicarmine_repo_search_det |
| Repo State | 3 | aicarmine_repo_state |
| Repo Validate | 9 | aicarmine_repo_validate |
| SQLite Read-Only | 4 | aicarmine_sqlite_readonly |

---

## 2. Monolithic/Problematic Areas Identified

### Area #1: planner.py — 6069 lines 🔴 CRITICAL

**Problem**: Single file handles 6 distinct responsibilities:
- Planner loop orchestration (`run_agentic_planner_job`)
- Decision validation (`planner_decision`)
- Vulkan/GPU0 repair routing
- Replan specialist calls
- Final quality judgment
- Memory lesson writing

**Import depth**: 47 lines of imports from 30+ submodules
**Coupling score**: Highest in codebase

**Impact**: Any change requires understanding 6069 lines of intertwined logic

---

### Area #2: job_html.py — ~2600 lines 🟡 HIGH

**Problem**: Massive HTML rendering module with 14+ route handlers in `app.py`
**Contains**: 3 `step-XXX` placeholder strings (misleading)

---

### Area #3: tool_schemas.py — ~920 lines 🟡 HIGH

**Problem**: All tool schemas in single file, tightly coupled to tool_registry

---

### Area #4: Circular Import Chains (3 cycles detected)

**Cycle A — Planner Loop Core:**
```
planner.py → application/planner/loop.py → application/planner/turn.py
  → application/prompt/history_messages.py → application/shared/diagnostics.py
  → back to planner.py (via config import)
```

**Cycle B — Evidence Contract:**
```
planner.py → application/evidence/builder.py → application/evidence/goal_classifier.py
  → application/evidence/goal_scope.py → application/shared/path_tokens.py
  → back to planner.py (via job_store import)
```

**Cycle C — Tool Surface Policy:**
```
planner.py → application/tool_surface/turn_surface_policy.py
  → application/tool_surface/candidate_actions.py
  → application/tool_surface/result_compaction.py
  → back to planner.py (via memory_tools import)
```

---

### Area #5: Terminal Block System (validation loop)

**Root cause**: After 2 planner rejections, `final_rewrite_latch` becomes `terminal_block_required`, which:
- Sets `final_allowed=False`
- Sets `planner_may_choose_final=False`
- Blocks all tool surface access

**Problem areas**:
- `validator.py` — `_next_final_rewrite_latch()`, `_escalate_final_rewrite_retry_count()`
- `turn_surface_policy.py` — Enforces latch-based tool blocking
- `builder.py` — Evidence overlay persists state across jobs
- `final_quality.py` — Generates `missing_core_candidate_paths` violations

---

### Area #6: Config Module Fragmentation

**5 modules with overlapping exports**:
1. `config/__init__.py`
2. `config/compatibility.py`
3. `config/env_loader.py`
4. `config/models.py`
5. `config/entry_points_config.py`

---

## 3. Refactoring Strategy

### Phase 1: Immediate (No Risk)

| # | Action | Effort | Files |
|---|--------|--------|-------|
| 1.1 | Remove 3 `step-XXX` placeholders in `job_html.py` | 30 min | job_html.py |
| 1.2 | Extract `planner_loop.py` from `planner.py` (~800 lines) | 2 days | planner.py → planner_loop.py |
| 1.3 | Extract `planner_decision.py` from `planner.py` (~1200 lines) | 2 days | planner.py → planner_decision.py |

### Phase 2: Decoupling (Medium Risk)

| # | Action | Effort | Dependency |
|---|--------|--------|------------|
| 2.1 | Extract `planner_repair.py`, `planner_judge.py`, `planner_memory.py`, `planner_finalize.py` | 4 days | Phase 1 |
| 2.2 | Resolve Cycle A (planner↔loop↔turn) via DI | 3 days | Phase 2.1 |
| 2.3 | Resolve Cycle B (evidence chain) via DI | 2 days | Phase 2.1 |
| 2.4 | Resolve Cycle C (tool surface chain) via DI | 2 days | Phase 2.2 |

### Phase 3: Consolidation (Low Risk)

| # | Action | Effort |
|---|--------|--------|
| 3.1 | Merge config sub-modules → `env_vars.py` + `settings.py` | 1 day |
| 3.2 | Remove dead `rag_cache_manager.py` placeholder | 30 min |
| 3.3 | Full ruff + pytest validation | 2 hours |

---

## 4. Terminal Block Prevention (Priority Fix)

### Problem
Terminal block activates after 2 planner rejections with no recovery path except valid final answer.

### Minimal Fix
Add early warning at `reject_count >= 1` in `validator.py`:

```python
# In _escalate_final_rewrite_retry_count(), after increment:
if reject_count >= 1:
    import logging
    logging.warning(
        f"Terminal block risk: reject_count={reject_count}. "
        f"Verify entry points before finalizing."
    )
```

### Surface Lock Clear
Add `_clear_surface_lock_if_safe()` in `builder.py` to reset lock when violations resolve.

---

## 5. MCP Tools Used for Discovery

| Tool | Purpose | Result |
|------|---------|--------|
| `aicarmine_mcp_inventory_list_targets` | List 12 servers | 12 targets found |
| `aicarmine_mcp_inventory_probe` | Health + tools per server | 62 tools, all healthy |
| `aicarmine_rag_context` | Semantic search for circular deps | 12 results |
| `aicarmine_rag_reindex` | Full DB rebuild | 568 files, 1129 chunks |
| `aicarmine_repo_search_rg` | Regex scan for TODO/FIXME | 50 matches (90% FP) |
| `aicarmine_repo_search_fd` | File listing (.py) | 388 Python files |
| `aicarmine_repo_state_status` | Repo health | Git available |

---

## 6. Fallbacks Used

- Git commands failed (`git` not in PATH); relied entirely on MCP deterministic search tools
- RAG reranker succeeded at 1735ms (first query), 2000ms (second)