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
- Head SHA: `55de3d9ad1197c6c475b5f4064f7bc20a905b594`
- Commits ahead of `origin/main`: `57`

## Baseline Verification

Commands run from `C:\Users\carmi\AI` with
`C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe`:

- `python -m compileall -q services`: passed.
- `python -m pytest -q`: `222 passed in 0.73s`.
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

## Current Monolithic / Incomplete Areas

These areas still fail the final Definition of Done from the executive plan:

- `services/aicarmine_broker/planner.py` is still operational and not yet a
  facade to `application/planner_loop.py`.
- `services/aicarmine_broker/agent_entry.py` still owns lifecycle/worker/router
  behavior.
- `services/aicarmine_broker/job_store.py` is not storage-only yet.
- `services/vulkan_bridge/app.py` still owns route plus public payload wrapping
  behavior.
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
