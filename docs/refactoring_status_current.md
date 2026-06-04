# Current Refactoring Status

Date: 2026-06-04

This document records the verified current state of the refactoring branch. It
is an audit note only and does not change the 3571/3572 runtime contract.

## Branch

- Repository: `C-F-tek/agentic-tool-loop`
- Working branch: `codex/refactor-agentic-tool-loop`
- Remote tracking branch: `origin/codex/refactor-agentic-tool-loop`
- Base reference: `origin/main`
- Base SHA: `5b9e4b916a90c12d9bfa469ceb7ab424a3a12cc5`
- Head SHA: `d8a179c204cf6b72be2f725ffd9fd3ffc060a80a`
- Commits ahead of `origin/main`: `85`

## Baseline Verification

Commands run from `C:\Users\carmi\AI` with
`C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe`:

- `python -m compileall -q services`: passed.
- Initial baseline `python -m pytest -q`: `222 passed in 0.73s`.
- Current verification after execution evidence, code-product public output and
  agent-flow diagnostic splits: `303 passed in 1.12s`.
- `git pull --ff-only`: already up to date.

PowerShell launcher inventory command was also run:

```powershell
Select-String services\launch\*.ps1 -Pattern "3571|3572|11434|11435|AICARMINE_|venvs|OpenWebUI|openapi"
```

It confirms the launcher still carries active env, port, venv and process
knowledge. That is expected until the launcher module split phase.

## Refactored Areas

- `repo_tools.py` is a compatibility facade for `tools/*` and
  `infrastructure/*`.
- `tool_dispatch.py` is a compatibility facade for
  `application/tool_dispatcher.py`.
- Broker config has been split into the `aicarmine_broker.config` package.
- Many planner helper responsibilities now live in `application/*`, including:
  goal classification/scope, history shaping, prompt windows, turn surface
  policy, code-product state/history, repo path policy, repo history evidence,
  user scope claims, core discovery and scope-conflict resolution.
- Public OpenWebUI tool-context shaping has moved into
  `application/public_tool_context.py`.
- `agent_entry.py` lifecycle responsibilities have been split into:
  `application/job_worker.py`, `application/job_lifecycle.py`,
  `application/selector_runner.py` and `application/job_action_router.py`.
  The legacy entrypoint now builds/delegates to these application services.
- `job_store.py` public response shaping has started moving into application
  builders: `job_response_values.py`, `job_terminal_response.py`,
  `job_status_response.py` and `job_wait_response.py`. `job_store.py` now
  loads persisted state/events/final JSON and delegates those compact payloads.
- `job_store.py` SQLite schema/upsert/list/event insert primitives moved to
  `infrastructure/job_sqlite_store.py`; filesystem state/events remain in
  `job_store.py`.
- `vulkan_bridge/app.py` request-payload and response-value helpers moved to
  `vulkan_bridge/application/request_payload.py` and
  `vulkan_bridge/application/response_values.py`, with compatibility wrappers
  kept in `app.py`.
- `planner.py` has begun the controlled facade migration with pure
  planner-adjacent helpers moved to:
  `application/planner_status.py`,
  `application/final_state_result.py`,
  `application/public_terminal_sanitizer.py`,
  `application/public_terminal_result.py` and
  `application/terminal_context_rows.py`,
  `application/execution_evidence_digest.py`,
  `application/code_product_public_outputs.py` and
  `application/agent_flow_diagnostics.py`. These slices keep compatibility
  wrappers in `planner.py` and do not change validator, native tool gate,
  finalization rules or public 3571 payload contracts.

## Current Monolithic / Incomplete Areas

These areas still fail the final Definition of Done from the executive plan:

- `services/aicarmine_broker/planner.py` is still operational and not yet a
  facade to `application/planner_loop.py`, but pure status, terminal digest,
  terminal sanitization, public terminal result, terminal context row,
  execution-evidence, code-product public-output and diagnostic helpers have
  been extracted with tests. Current line count is 8426.
- `services/aicarmine_broker/agent_entry.py` still imports runtime dependencies
  to build compatibility adapters, but worker, lifecycle, selector dispatch and
  action routing behavior now live in `application/*`.
- `services/aicarmine_broker/job_store.py` is not storage-only yet, but terminal,
  status, wait-timeout response construction and SQLite primitives have been
  extracted to `application/*` / `infrastructure/*`.
- `services/vulkan_bridge/app.py` still owns route plus public payload wrapping
  behavior, but first pure request/response helper slices have been extracted
  to `application/*`.
- `services/model_export/cli.py` is still monolithic.
- `services/codex_bridge/mcp_server.py` is still monolithic.
- `services/launch/*.ps1` still carry implementation logic and are not yet
  module facades.
- Root wrappers still need final thin-wrapper verification.

## Runtime Contract Preserved

- No change to 3571 public surface.
- No change to `/subagents`.
- No change to launcher env, model, ports, context or max-step values.
- `repo_propose_code_edit` remains report-only.
- OpenWebUI payload isolation rule remains unchanged: local paths and SQLite
  document ids are not useful final content.
