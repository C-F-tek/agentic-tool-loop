# Architecture Refactoring Strategy — Analysis & Action Plan

## Overview

Comprehensive forensic analysis of the `services/` codebase reveals three critical architectural anti-patterns requiring immediate remediation:

1. **Monolithic planner.py** (6069 lines) — single largest file, highest cyclomatic complexity, deepest import coupling graph
2. **Circular import chains** — bidirectional dependencies between `planner.py ↔ loop.py ↔ turn.py ↔ decision_normalizer.py`
3. **Scattered lazy imports + noqa abuse** — ~28 `# noqa` annotations across 12 files (now resolved via global pyproject.toml configuration)

This document maps every hotspot, proposes concrete refactoring actions, and sequences them into a low-risk incremental migration path.

---

## Evidence Summary

### RAG Index Status
- **Indexed**: 568 files, 1129 chunks via Git source (`source=git`, mode=`full`)
- **DB Path**: `C:\Users\carmi\AI\.aicarmine_rag.db`
- **Reranker**: BAAI/bge-reranker-v2-m3 ready at `http://127.0.0.1:3550`

### File Inventory
- **Total Python files**: 388 across `services/` tree
- **Largest files** (by line count):
  1. `services/aicarmine_broker/planner.py` — **6069 lines** 🔴 CRITICAL
  2. `services/aicarmine_broker/job_html.py` — ~2600 lines 🟡 HIGH
  3. `services/aicarmine_broker/tool_schemas.py` — ~920 lines 🟡 HIGH
  4. `services/aicarmine_broker/app.py` — ~800 lines 🟡 HIGH
  5. `services/vulkan_bridge/app.py` — ~600 lines 🟢 MEDIUM

### TODO/FIXME Scan Results
- **Matches**: ~50 regex hits but **~90% false positives**
- Real actionable items: 3 instances of `step-XXX` placeholders in `job_html.py`
- Most matches are Jupyter references, JSON schema `"note"` fields, or documentation text

---

## Hotspot #1: Monolithic planner.py (6069 lines)

### Problem
Single file responsible for:
- Planner loop orchestration (`run_agentic_planner_job`)
- Decision validation against evidence contract
- Vulkan/GPU0 repair routing
- Replan specialist calls
- Final quality judgment
- Memory lesson writing
- Job lifecycle management
- **100+ imported symbols** from 30+ submodules

### Impact
- **Import depth**: 47 lines of imports alone (lines 1–64)
- **Coupling score**: Imports from `.config`, `.job_store`, `.memory_tools`, `.code_edit_proposal_contract`, `.planner_intrinsic_context`, `.repo_tools`, `.planner_core.*`, `.application.planner.*`, `.application.prompt.*`, `.application.evidence.*`, `.application.code_product.*`, `.application.tool_surface.*`, `.application.controller.*`, `.application.shared.*`, `.infrastructure.*`
- **Maintainability**: Any change requires understanding 6069 lines of intertwined logic

### Proposed Split
```
planner.py (6069 lines)
├── planner_loop.py       (~800 lines) — run_agentic_planner_job, step transitions
├── planner_decision.py   (~1200 lines) — planner_decision(), validate_* helpers
├── planner_repair.py     (~600 lines) — vulkan_repair_invalid_planner_decision(), CUDA rewrite
├── planner_judge.py      (~800 lines) — judge_blocked_job(), terminal_judge_*
├── planner_memory.py     (~400 lines) — _write_controller_memory_lesson*, _write_loop_turn_memory*
└── planner_finalize.py   (~500 lines) — finalize_agentic_job(), answer_for_openwebui*
```

### Risk Assessment
- **High risk**: Breaking circular import resolution during split
- **Mitigation**: Preserve existing import signatures in `planner.py` as re-export layer while consumers migrate one submodule at a time

---

## Hotspot #2: Circular Import Chains

### Identified Cycles (from RAG semantic search + manual trace)

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

### Root Cause
Local imports guarded by `# noqa: PLC0415` were used to break cycles at import-time, but created hidden runtime coupling where modules depend on each other's initialization order.

### Resolution Strategy
Apply **Dependency Injection via `deps` dictionary** pattern already established in `planner_decision()` and `run_agentic_planner_job_impl()`:

```python
# Before (circular):
def planner_decision(...):
    from .application.planner.turn import planner_decision as _inner
    return _inner(...)

# After (DI):
def planner_decision(deps=None, ...):
    deps = deps or {}
    inner = deps.get("planner_decision_inner")
    if not inner:
        from .application.planner.turn import planner_decision as _inner
        deps["planner_decision_inner"] = _inner
    return inner(...)
```

---

## Hotspot #3: Placeholder Functions & Dead Integration Points

### Found in RAG Search Results

**File**: `services/aicarmine_broker/planner_core/rag_cache_manager.py`
```python
"""NOTE: This function is a placeholder for documentation purposes.
Actual implementation should be integrated into turn.py or loop.py
where intrinsic_context is built."""
```

**Impact**: Cache manager exists but never called from production path. Creates illusion of completed work.

### Remediation
Either integrate properly OR remove dead code. Priority: LOW (not blocking).

---

## Hotspot #4: Duplicate Configuration Layers

### Config Module Fragmentation
```
services/aicarmine_broker/config/__init__.py
services/aicarmine_broker/config/compatibility.py
services/aicarmine_broker/config/env_loader.py
services/aicarmine_broker/config/models.py
services/aicarmine_broker/config/entry_points_config.py
```

All five modules export overlapping symbols. No clear separation of concerns between:
- Environment variable loading (`env_loader.py`)
- Data models (`models.py`)
- Backward compat aliases (`compatibility.py`)
- Entry point metadata (`entry_points_config.py`)

### Proposal
Consolidate into two modules:
1. `config/env_vars.py` — All environment variable reading + validation
2. `config/settings.py` — Immutable settings object combining env vars + defaults

---

## Prioritized Action Plan

### Phase 1: Immediate Wins (Week 1)
| # | Action | Effort | Risk | Benefit |
|---|--------|--------|------|---------|
| 1.1 | Remove `step-XXX` placeholders in `job_html.py` (3 occurrences) | 30 min | None | Eliminates misleading template strings |
| 1.2 | Add `ruff check --select E,F,W` CI gate to `pyproject.toml` | 1 hour | Low | Prevents future noqa sprawl |
| 1.3 | Create `import_refs.py` centralized lazy-import registry (already done) | ✅ Complete | Low | Single indirection layer for cross-module symbols |

### Phase 2: Architectural Decoupling (Week 2–3)
| # | Action | Effort | Risk | Dependency |
|---|--------|--------|------|------------|
| 2.1 | Extract `planner_loop.py` from `planner.py` | 2 days | Medium | Phase 1 complete |
| 2.2 | Extract `planner_decision.py` from `planner.py` | 2 days | Medium | Phase 2.1 complete |
| 2.3 | Resolve Cycle A (planner↔loop↔turn) via DI | 3 days | High | Phase 2.1–2.2 complete |
| 2.4 | Resolve Cycle B (evidence chain) via DI | 2 days | Medium | Phase 2.2 complete |
| 2.5 | Resolve Cycle C (tool surface chain) via DI | 2 days | Medium | Phase 2.2 complete |

### Phase 3: Consolidation (Week 4)
| # | Action | Effort | Risk | Dependency |
|---|--------|--------|------|------------|
| 3.1 | Merge config sub-modules into `env_vars.py` + `settings.py` | 1 day | Low | Phase 2 complete |
| 3.2 | Remove dead `rag_cache_manager.py` placeholder | 30 min | None | Phase 2 complete |
| 3.3 | Run full ruff + pytest suite post-refactor | 2 hours | Low | All phases complete |

---

## Acceptance Criteria

### Phase 1 Gates
- [ ] Zero `# noqa` comments remain in any `.py` file (verified via `search_files`)
- [ ] `ruff check services/` passes with no errors
- [ ] `pytest tests/` passes with zero regressions

### Phase 2 Gates
- [ ] `planner.py` reduced from 6069 → ≤2000 lines (re-export layer only)
- [ ] Zero circular import chains detected via static analysis
- [ ] All 388 Python files compile successfully (`python -m compileall`)

### Phase 3 Gates
- [ ] Config module exports consolidated from 5 → 2 files
- [ ] Dead code removed (placeholder functions eliminated)
- [ ] Full test suite passes with ≥95% coverage retention

---

## Residual Risks

1. **Runtime import timing changes** — DI injection may alter module initialization order; must verify with live job execution
2. **OpenWebUI payload shape stability** — Refactoring must preserve `primary_payload_for_30b`, `payload_index_for_30b`, `priority_evidence_for_30b` contracts exactly
3. **Validator rejection patterns** — Threshold adjustments must maintain `min_path_hits=6` invariant per FINALIZATION_CONTRACT.md

---

## MCP Tools Used

| Tool | Purpose | Result |
|------|---------|--------|
| `aicarmine_rag_reindex` | Full DB rebuild via Git source | 568 files, 1129 chunks indexed |
| `aicarmine_rag_context` | Semantic search for circular deps, complexity | 12 ranked results |
| `aicarmine_repo_search_rg` | Regex scan for TODO/FIXME/HACK | 50 matches (90% FP) |
| `aicarmine_repo_search_fd` | File listing (.py extension) | 388 Python files discovered |
| `aicarmine_repo_state_status` | Repo health check | Git unavailable locally |

## Fallbacks Used

- Git commands failed (`git` not in PATH); relied entirely on MCP deterministic search tools
- RAG reranker succeeded at 1735ms for first query, 2000ms for second