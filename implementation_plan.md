# Implementation Plan — MCP Servers, Refactoring & Indexing

## Status: Active

This plan tracks all ongoing work across MCP server integration, code refactoring, index management, and documentation updates.

---

## Completed Work ✅

### 1. Duplicate Function Refactoring (~70% reduction)

| Server | Functions Removed | Status |
|--------|------------------|--------|
| job_artifact_mcp_server.py | _json_text, _json_page, _json_overview, _safe_job_id, _read_json, _payload_preview | ✅ Done |
| rag_mcp_server.py | _json_dumps, _safe_int, _safe_float, _safe_bool, _tool_content, _ok, _err | ✅ Done |
| project_memory_mcp_server.py | string_prop, integer_prop, boolean_prop, _safe_int, _safe_float | ✅ Done |
| sqlite_readonly_mcp_server.py | string_prop, integer_prop, boolean_prop, _safe_int | ✅ Done |
| repo_search_det_mcp_server.py | string_prop, integer_prop, _safe_int | ✅ Done |
| repo_code_mcp_server.py | string_prop, integer_prop, _safe_int | ✅ Done |
| git_readonly_mcp_server.py | string_prop, integer_prop, boolean_prop, _safe_int | ✅ Done |
| job_view_mcp_server.py | string_prop, integer_prop, boolean_prop, _safe_int, _truncate_text, _safe_job_id | ✅ Done |
| local_subagent_mcp_server.py | string_prop, integer_prop, boolean_prop, _safe_bool | ✅ Done |
| agentic_loop_client_mcp_server.py | string_prop, integer_prop, boolean_prop, _safe_int, _safe_bool | ✅ Done |
| repo_validate_mcp_server.py | string_prop, integer_prop, _safe_int | ✅ Done |
| repo_symbol_index_mcp_server.py | string_prop, integer_prop | ✅ Done |

**Total:** ~35 duplicate functions removed across 12 servers

### 2. Index Operations

| Index | Files | Chunks/Symbols | Status |
|-------|-------|----------------|--------|
| RAG code index | 627 | 1247 chunks | ✅ Reindexed (full) |
| Symbol index | 432 | 5286 symbols | ✅ Built (full) |
| Index bridge | — | 6533 unified entries, 763 refs | ✅ Built |

### 3. Configuration Updates

| File | Change | Status |
|------|--------|--------|
| `cline_mcp_settings.json` | Added `aicarmine_index_bridge` with autoApprove for all 5 tools | ✅ Done |
| `aicarmine_cline_mcp_router.ps1` | Added index_bridge health + all 4 bridge tools to semantic_search routing | ✅ Done |
| `AGENTS.md` | Updated count from 19 → 20 servers, added index_bridge row | ✅ Done |
| `index_bridge_mcp_server.py` | Fixed missing `import hashlib` bug | ✅ Done |

---

## Pending Work — Detailed Implementation Plan

### Phase 1: Code Quality & Linting (High Priority)

#### Step 1.1: Ruff Configuration Setup
- **File:** `services/pyproject.toml`
- **Action:** Add `[tool.ruff]` and `[tool.ruff.lint]` sections
- **Details:**
  - Set global `ignore = ["PLC0415"]` for lazy imports
  - Add per-file ignores for wildcard re-exports
  - Bump ruff version to `>=0.4.0`
- **Estimated effort:** 30 minutes

#### Step 1.2: Centralized Import Registry
- **File:** `services/aicarmine_broker/import_refs.py` (new)
- **Action:** Create `ImportRegistry` class with cached lazy loading
- **Details:**
  - ~80 lines, new file
  - Thread-safe via `threading.Lock`
  - Provides `_resolve_lazy(module_path, symbol_names)` method
- **Estimated effort:** 1 hour

#### Step 1.3: Replace Local Imports Across Files
- **Files affected:** 10 files in `services/aicarmine_broker/`
- **Action:** Replace local imports with registry/DI
- **Details:**
  - `loop.py` — 2 local imports
  - `loop_controller.py` — 4 local imports
  - `planner.py` — 3 local imports
  - `helper.py` — 2 local imports
  - `cache.py`, `job_store.py`, `mcp_server.py`, `job_view_mcp_server.py` — 1 each
- **Estimated effort:** 2 hours

#### Step 1.4: Fix Config Compatibility Module
- **Files:** `services/aicarmine_broker/config/compatibility.py`, `config/__init__.py`
- **Action:** Remove `# noqa: F401` comments, add `__all__` declarations
- **Estimated effort:** 30 minutes

#### Step 1.5: Verification
- **Commands:**
  ```bash
  ruff check services/ --output-format=json
  pytest services/ -v --tb=short
  python -c "from services.aicarmine_broker import helper, planner, job_store"
  ```
- **Estimated effort:** 30 minutes

---

### Phase 2: Index Bridge Enhancement (Medium Priority)

#### Step 2.1: Add Query Tool to Router
- **File:** `.clinerules/hooks/lib/aicarmine_cline_mcp_router.ps1`
- **Action:** Ensure `aicarmine_index_bridge_query` is added when "index bridge" keyword detected
- **Status:** Already done in Phase 1 (router update)

#### Step 2.2: Verify Bridge Query Functionality
- **Command:** Use `aicarmine_index_bridge_query` with sample queries
- **Estimated effort:** 30 minutes

---

### Phase 3: Documentation Updates (Low Priority)

#### Step 3.1: Update MCP_REFACCTOR_INTEGRATION.md
- **File:** `services/codex_bridge/MCP_REFACCTOR_INTEGRATION.md`
- **Actions:**
  - Update server count from 19 → 20
  - Add index_bridge row to Operations & Discovery table
  - Add section for index_bridge tools
  - Remove outdated code format tools section (5 servers no longer relevant)
- **Estimated effort:** 1 hour

#### Step 3.2: Create Index Operations Guide
- **File:** `docs/INDEX_OPERATIONS.md` (new)
- **Content:** How to reindex RAG, rebuild symbol index, build bridge
- **Estimated effort:** 1 hour

---

### Phase 4: Optional Follow-ups (Low Priority)

#### Step 4.1: Code Format MCP Servers Cleanup
- **Action:** Evaluate if prettier, biome, ruff, eslint, black MCP servers are still needed
- **Status:** Not currently used in active workflows
- **Estimated effort:** 30 minutes investigation

#### Step 4.2: Agent Client Health Check
- **Action:** Verify `aicarmine_local_subagent` and `aicarmine_agentic_loop_client` are still disabled as intended
- **Status:** Both set to `"disabled": true` in mcp settings
- **Estimated effort:** 15 minutes

---

## Implementation Order

1. **Step 1:** Ruff configuration (`pyproject.toml`) — 30 min
2. **Step 2:** Create `import_refs.py` — 1 hour
3. **Step 3:** Update config compatibility files — 30 min
4. **Step 4:** Replace local imports across 10 files — 2 hours
5. **Step 5:** Run verification (`ruff check`, `pytest`) — 30 min
6. **Step 6:** Update `MCP_REFACCTOR_INTEGRATION.md` — 1 hour
7. **Step 7:** Create `docs/INDEX_OPERATIONS.md` — 1 hour

**Total estimated effort: ~6 hours**

---

## Verification Checklist

- [ ] `ruff check services/ --output-format=json` returns zero PLC0415 violations
- [ ] `pytest services/ -v --tb=short` passes all existing tests
- [ ] All modified files can be imported successfully
- [ ] Lazy-loading overhead <5ms (first call vs subsequent)
- [ ] Wildcard exports still work (`from X import *`)
- [ ] Index bridge query returns valid results
- [ ] Router correctly routes to index_bridge tools

---

## Notes

- All refactoring uses `repo_code_mcp_server.py` structured_edit for safe changes
- .gitignore is automatically respected during reindex operations
- No new external packages required — all changes use stdlib