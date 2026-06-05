# Agentic Tool Loop Refactoring Inventory

Baseline branch:

- Source baseline: `origin/main`
- Working branch: `codex/refactor-agentic-tool-loop`
- Plan source: `C:\Users\carmi\Downloads\piano_refactoring_completo_agentic_tool_loop.md`
- Current status snapshot: `docs/refactoring_status_current.md`

This inventory records the verified starting point for the refactor. It is not
runtime behavior and must not be used to change the 3571/3572 contract without a
separate code-backed proof.

## Baseline Verification

Commands run from `C:\Users\carmi\AI` with
`C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe`:

- `python -m compileall -q services`: passed.
- `python -m pytest`: failed during collection before project tests could run.

The pytest failure was not a source-code assertion failure. Pytest discovered
local generated/runtime directories that are ignored by git but still present on
disk, including `dash-smoke-*`, `lab-worktrees` and `ovms-runtime`. The new
`pytest.ini` constrains collection to versioned source/test areas and excludes
runtime artifact folders.

## Versioned Source Size

`git ls-files` reported 292 tracked files at baseline.

Critical runtime module size:

| Path | Lines | Characters |
| --- | ---: | ---: |
| `services/aicarmine_broker/planner.py` | 12242 | 577416 |
| `services/vulkan_bridge/app.py` | 3284 | 152102 |
| `services/aicarmine_broker/repo_tools.py` | 1793 | 74699 |
| `services/aicarmine_broker/tool_registry.py` | 817 | 34979 |
| `services/aicarmine_broker/memory_tools.py` | 784 | 31084 |
| `services/aicarmine_broker/planner_intrinsic_context.py` | 536 | 21955 |
| `services/aicarmine_broker/job_store.py` | 541 | 22894 |
| `services/aicarmine_broker/code_edit_proposal_contract.py` | 366 | 13765 |
| `services/aicarmine_broker/config.py` | 304 | 12095 |
| `services/aicarmine_broker/app.py` | 198 | 8301 |
| `services/aicarmine_broker/tool_dispatch.py` | 117 | 4260 |
| `services/vulkan_bridge/agentic_v9.py` | 11 | 314 |

## Refactor Boundary

Phase 1 adds importable domain and contract modules only. It does not move or
change the runtime flow:

```text
OpenWebUI -> 3571 /vulkan_helper -> 3572 /vulkan/agent
  -> 11434 planner -> 3572 validator -> tool_dispatch
  -> terminal payload -> 3571 OpenWebUI wrapper
```

The next safe extraction step must move behavior behind these boundaries with
adapter/facade compatibility tests before deleting any old entrypoint.

## Current Status Pointer

The original baseline above remains the historical starting point. The current
branch status after the ongoing refactor is tracked in
`docs/refactoring_status_current.md`, including current head/base SHA, latest
test results and remaining monolithic areas.

## Non-Negotiable Transport Rules

- 3571 still exposes only `vulkan_helper` publicly.
- OpenWebUI cannot read local job paths, SQLite document ids or artifact files.
- `tool_context_for_30b` and `priority_evidence_for_30b` must carry real inline
  payloads.
- `repo_propose_code_edit` remains report-only and must not apply patches.
- The controller validates planner decisions; it must not replace planner
  reasoning with hidden scripted steps.
