# AI-Carmine Deterministic Repo MCP Contract

This document fixes the contract for external repo MCP servers loaded by
Codex. These MCPs are independent from the OpenWebUI and broker runtime.

## Scope

The stable repo MCP set is tool-only and state/search/validation oriented:

- `aicarmine_repo_state`: deterministic repository state, status, branch,
  commit, and capability reporting.
- `aicarmine_repo_search_det`: deterministic repository search through bounded
  tools such as `rg`, `fd`, `jq`, ast-grep, tree-sitter, and ctags.
- `aicarmine_repo_validate`: deterministic validation wrappers such as
  `git diff --check`, compile checks, pytest, ruff, pyright, shellcheck, and
  semgrep.

The incubating repo-code MCP is separate from the stable set:

- `aicarmine_repo_code`: candidate code-edit tooling. Proposal and diff-check
  tools are report-only. Exact source patching is available only through
  `aicarmine_repo_code_apply_patch` with `allow_source_write=true`; generic
  command execution and whole-file writes remain excluded.

The incubating Codex ops MCP is separate from repo-editing tools:

- `aicarmine_codex_ops`: local MCP smoke checks and read-only service-state
  inspection. It may inspect process tables, TCP listeners and repo-local log
  tails, but it must not call HTTP health routes, 3571, 3572, `vulkan_helper`
  or the agentic loop.

The read-only observability MCP set is separate from repo-editing tools:

- `aicarmine_sqlite_readonly`: allowlisted SQLite inspection for existing
  repo-local databases. User queries are limited to one bounded `SELECT`/`WITH`
  statement, with row/time/cell limits and no user PRAGMA or write keywords.
- `aicarmine_job_artifact`: filesystem-only agent job artifact reader for
  `job.json`, `events.ndjson`, `final.json`, `tool-results/`,
  `planner-prompts/` and rejection summaries.
- `aicarmine_job_view`: filesystem/local-renderer-only agent job HTML view
  reader. It renders existing `job_html.py`/`job_planner_lab.py` views,
  extracts outlines/links and validates bounded HTML without broker HTTP.
- `aicarmine_git_readonly`: bounded Git diagnostics for log/show/diff/blame
  and branch comparison. It does not fetch, checkout, reset, commit, push or
  mutate the worktree.

The project-local memory MCP is write-capable but semantic and isolated:

- `aicarmine_project_memory`: persistent project memory for verified
  operational facts, preferences, contracts, path mappings, confirmed bug
  causes and architecture decisions. It writes only
  `state/project_memory/project_memory.sqlite3` under the selected repo root,
  never global memory and never RAG/job/planner SQLite databases. Writes are
  available only through semantic tools and explicit confirmation strings.

The shared implementation lives in:

- `C:\Users\carmi\AI\services\codex_bridge\repo_mcp_common.py`

Server entrypoints:

- `C:\Users\carmi\AI\services\codex_bridge\repo_state_mcp_server.py`
- `C:\Users\carmi\AI\services\codex_bridge\repo_search_det_mcp_server.py`
- `C:\Users\carmi\AI\services\codex_bridge\repo_validate_mcp_server.py`
- `C:\Users\carmi\AI\services\codex_bridge\repo_code_mcp_server.py`
- `C:\Users\carmi\AI\services\codex_bridge\ops_mcp_server.py`
- `C:\Users\carmi\AI\services\codex_bridge\sqlite_readonly_mcp_server.py`
- `C:\Users\carmi\AI\services\codex_bridge\job_artifact_mcp_server.py`
- `C:\Users\carmi\AI\services\codex_bridge\job_view_mcp_server.py`
- `C:\Users\carmi\AI\services\codex_bridge\git_readonly_mcp_server.py`
- `C:\Users\carmi\AI\services\codex_bridge\project_memory_mcp_server.py`

## Runtime Requirements

Required Python executable:

```text
C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe
```

Required environment:

```text
AICARMINE_CODEX_MCP_REPO_ROOT=C:\Users\carmi\AI
AICARMINE_USEFUL_TOOLS_ROOT=C:\Users\carmi\AI\services\useful_tools
AICARMINE_REPO_MCP_MAX_TEXT_CHARS=24000
```

`AICARMINE_LAB_REPO` may still be inherited from the OpenWebUI/3572 broker
environment. The repo MCP process must not trust that inherited value when
Codex selected a different root. `repo_mcp_common.py` resolves the Codex root
from `AICARMINE_CODEX_MCP_REPO_ROOT`, Codex workspace env or cwd, then rewrites
only the MCP process' `AICARMINE_LAB_REPO` before importing broker repo tools.
This does not require the OpenWebUI lab shadow to equal the Codex repo root.

The effective health gate must report:

- `python_executable`: `C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe`
- `repo_root`: `C:\Users\carmi\AI`
- `codex_mcp_repo_root`: `C:\Users\carmi\AI`
- `aicarmine_lab_repo`: `C:\Users\carmi\AI` after MCP process-local sync.
- `cwd`: `C:\Users\carmi\AI`
- `git_root_ok`: `true`
- `branch`: the current Codex work branch for the selected repo root.

## Self-Test Commands

Run self-tests with the absolute Python executable:

```powershell
& "C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe" "C:\Users\carmi\AI\services\codex_bridge\repo_state_mcp_server.py" --self-test
& "C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe" "C:\Users\carmi\AI\services\codex_bridge\repo_search_det_mcp_server.py" --self-test
& "C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe" "C:\Users\carmi\AI\services\codex_bridge\repo_validate_mcp_server.py" --self-test
& "C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe" "C:\Users\carmi\AI\services\codex_bridge\repo_code_mcp_server.py" --self-test
& "C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe" "C:\Users\carmi\AI\services\codex_bridge\ops_mcp_server.py" --self-test
& "C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe" "C:\Users\carmi\AI\services\codex_bridge\sqlite_readonly_mcp_server.py" --self-test
& "C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe" "C:\Users\carmi\AI\services\codex_bridge\job_artifact_mcp_server.py" --self-test
& "C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe" "C:\Users\carmi\AI\services\codex_bridge\job_view_mcp_server.py" --self-test
& "C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe" "C:\Users\carmi\AI\services\codex_bridge\git_readonly_mcp_server.py" --self-test
& "C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe" "C:\Users\carmi\AI\services\codex_bridge\project_memory_mcp_server.py" --self-test
```

The server self-tests must pass before the MCP entries are considered valid for
Codex reload testing.

## Codex Reload Gate

After a Codex reload or new session, the MCP list must expose:

- `aicarmine_repo_state`
- `aicarmine_repo_search_det`
- `aicarmine_repo_validate`
- `aicarmine_repo_code` if the incubator server is enabled locally.
- `aicarmine_codex_ops` if the ops incubator server is enabled locally.
- `aicarmine_sqlite_readonly` if the SQLite observability server is enabled locally.
- `aicarmine_job_artifact` if the job artifact observability server is enabled locally.
- `aicarmine_job_view` if the job HTML view observability server is enabled locally.
- `aicarmine_git_readonly` if the Git observability server is enabled locally.
- `aicarmine_project_memory` if the project-local memory server is enabled locally.

Required health tool calls:

- `aicarmine_repo_state_health`
- `aicarmine_repo_search_det_health`
- `aicarmine_repo_validate_health`
- `aicarmine_repo_code_health` if the incubator server is enabled locally.
- `aicarmine_codex_ops_health` if the ops incubator server is enabled locally.
- `aicarmine_sqlite_readonly_health` if the SQLite observability server is enabled locally.
- `aicarmine_job_artifact_health` if the job artifact observability server is enabled locally.
- `aicarmine_job_view_health` if the job HTML view observability server is enabled locally.
- `aicarmine_git_readonly_health` if the Git observability server is enabled locally.
- `aicarmine_project_memory_health` if the project-local memory server is enabled locally.

If health is OK, the minimal real-tool gate is:

- `aicarmine_repo_state_status`
- `aicarmine_repo_search_rg` with pattern `AICARMINE_CODEX_MCP_REPO_ROOT|AICARMINE_LAB_REPO`
- `aicarmine_repo_validate_diffcheck`
- `aicarmine_repo_code_unidiff_validate` for the incubator server. The
  incubator self-test deliberately avoids source writes.
- `aicarmine_mcp_smoke_run` with `servers=["aicarmine_repo_state"]`.
- `aicarmine_service_state_snapshot` with bounded process/log limits.
- `aicarmine_sqlite_readonly_list_databases` with a low `max_results`.
- `aicarmine_job_artifact_list_jobs` with a low `limit`.
- `aicarmine_job_view_list_views`.
- `aicarmine_git_readonly_log` with `max_count=1`.
- `aicarmine_project_memory_search` with a low `limit`. The self-test must
  not require a write.

Stable MCP reload verification on 2026-06-11 passed the state/search/validate
gates in that session. The incubator server requires its own reload gate after
being enabled in local Codex configuration. The `rg` result was intentionally
bounded by MCP text limits, so only the successful tool result and count are
used as the gate, not the full match set.

## Non-Negotiable Exclusions

These MCPs must not introduce or depend on:

- broker HTTP
- OpenWebUI
- agentic loop
- general dispatcher
- generic command execution
- whole-file write tools in the incubator phase
- source-write tools in the stable state/search/validation MCPs
- write-capable SQL, unbounded SQL, user PRAGMA, or path-unallowlisted database reads
- job artifact readers that call 3571, 3572, `vulkan_helper` or HTTP routes
- job view renderers that start services, call broker HTTP routes or mutate job state
- Git commands that mutate local or remote state
- local subagent MCP calls to 11435, GPU0 task models, 3571, 3572,
  OpenWebUI, service launchers, `vulkan_helper` or source-write tools
- persistent memory writes without source metadata and one of the required
  confirmation strings: `project_memory_upsert_verified`,
  `project_memory_mark_stale`, `project_memory_supersede`
- global memory writes from Codex MCPs unless a separate explicit contract is
  created

The ops MCP may read whether ports such as `3571` and `3572` are listening as
local diagnostic state. It must not call `/health`, send HTTP requests to those
ports or use that inspection as an agentic-loop substitute.

The only incubating source-write path is
`aicarmine_repo_code_apply_patch`, which must require
`allow_source_write=true`, use exact `old_text` to `new_text` replacement and
return `source_writes_performed` plus `patch_application_performed` flags.

The MCPs are external deterministic helpers at the same architectural level as
the RAG MCP. They are not a replacement for the planner, validator, controller,
or OpenWebUI transport contracts.

## Local Codex Configuration

`C:\Users\carmi\.codex\config.toml` is local machine configuration. It is not a
project source file and must not be committed to this repository. Backups of
that global TOML file are also local artifacts and must not be committed.

Example TOML only, for local documentation:

```toml
[mcp_servers.aicarmine_repo_state]
command = 'C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe'
args = ['C:\Users\carmi\AI\services\codex_bridge\repo_state_mcp_server.py']
env = { AICARMINE_CODEX_MCP_REPO_ROOT = 'C:\Users\carmi\AI', AICARMINE_USEFUL_TOOLS_ROOT = 'C:\Users\carmi\AI\services\useful_tools', AICARMINE_REPO_MCP_MAX_TEXT_CHARS = '24000' }

[mcp_servers.aicarmine_repo_search_det]
command = 'C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe'
args = ['C:\Users\carmi\AI\services\codex_bridge\repo_search_det_mcp_server.py']
env = { AICARMINE_CODEX_MCP_REPO_ROOT = 'C:\Users\carmi\AI', AICARMINE_USEFUL_TOOLS_ROOT = 'C:\Users\carmi\AI\services\useful_tools', AICARMINE_REPO_MCP_MAX_TEXT_CHARS = '24000' }

[mcp_servers.aicarmine_repo_validate]
command = 'C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe'
args = ['C:\Users\carmi\AI\services\codex_bridge\repo_validate_mcp_server.py']
env = { AICARMINE_CODEX_MCP_REPO_ROOT = 'C:\Users\carmi\AI', AICARMINE_USEFUL_TOOLS_ROOT = 'C:\Users\carmi\AI\services\useful_tools', AICARMINE_REPO_MCP_MAX_TEXT_CHARS = '24000' }

[mcp_servers.aicarmine_repo_code]
command = 'C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe'
args = ['C:\Users\carmi\AI\services\codex_bridge\repo_code_mcp_server.py']
env = { AICARMINE_CODEX_MCP_REPO_ROOT = 'C:\Users\carmi\AI', AICARMINE_USEFUL_TOOLS_ROOT = 'C:\Users\carmi\AI\services\useful_tools', AICARMINE_REPO_MCP_MAX_TEXT_CHARS = '24000' }

[mcp_servers.aicarmine_codex_ops]
command = 'C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe'
args = ['C:\Users\carmi\AI\services\codex_bridge\ops_mcp_server.py']
env = { AICARMINE_CODEX_MCP_REPO_ROOT = 'C:\Users\carmi\AI', AICARMINE_USEFUL_TOOLS_ROOT = 'C:\Users\carmi\AI\services\useful_tools', AICARMINE_REPO_MCP_MAX_TEXT_CHARS = '24000' }

[mcp_servers.aicarmine_sqlite_readonly]
command = 'C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe'
args = ['C:\Users\carmi\AI\services\codex_bridge\sqlite_readonly_mcp_server.py']
env = { AICARMINE_CODEX_MCP_REPO_ROOT = 'C:\Users\carmi\AI', AICARMINE_REPO_MCP_MAX_TEXT_CHARS = '24000' }

[mcp_servers.aicarmine_job_artifact]
command = 'C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe'
args = ['C:\Users\carmi\AI\services\codex_bridge\job_artifact_mcp_server.py']
env = { AICARMINE_CODEX_MCP_REPO_ROOT = 'C:\Users\carmi\AI', AICARMINE_REPO_MCP_MAX_TEXT_CHARS = '24000' }

[mcp_servers.aicarmine_job_view]
command = 'C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe'
args = ['C:\Users\carmi\AI\services\codex_bridge\job_view_mcp_server.py']
env = { AICARMINE_CODEX_MCP_REPO_ROOT = 'C:\Users\carmi\AI', AICARMINE_REPO_MCP_MAX_TEXT_CHARS = '24000' }

[mcp_servers.aicarmine_git_readonly]
command = 'C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe'
args = ['C:\Users\carmi\AI\services\codex_bridge\git_readonly_mcp_server.py']
env = { AICARMINE_CODEX_MCP_REPO_ROOT = 'C:\Users\carmi\AI', AICARMINE_REPO_MCP_MAX_TEXT_CHARS = '24000' }

[mcp_servers.aicarmine_project_memory]
command = 'C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe'
args = ['C:\Users\carmi\AI\services\codex_bridge\project_memory_mcp_server.py']
env = { AICARMINE_CODEX_MCP_REPO_ROOT = 'C:\Users\carmi\AI', AICARMINE_REPO_MCP_MAX_TEXT_CHARS = '24000' }

[mcp_servers.aicarmine_local_subagent]
command = 'C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe'
args = ['C:\Users\carmi\AI\services\codex_bridge\local_subagent_mcp_server.py']
env = { AICARMINE_CODEX_MCP_REPO_ROOT = 'C:\Users\carmi\AI', AICARMINE_REPO_MCP_MAX_TEXT_CHARS = '24000', AICARMINE_LOCAL_SUBAGENT_OLLAMA_URL = 'http://127.0.0.1:11434/api/chat', AICARMINE_LOCAL_SUBAGENT_MODEL = 'qwen3.5:9b-coding' }

[mcp_servers.playwright]
command = 'npx'
args = ['-y', '@playwright/mcp@latest', '--headless', '--isolated', '--output-dir', 'C:\Users\carmi\AI\state\playwright_mcp']
cwd = 'C:\Users\carmi\AI'
```

The Playwright MCP entry is a local Codex convenience server, not an
AI-Carmine repo MCP. It should stay stdio-based; do not configure it as a
long-lived HTTP sidecar unless a separate diagnostic proves that is needed.
