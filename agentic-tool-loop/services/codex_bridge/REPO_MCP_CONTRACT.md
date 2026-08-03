# AI-Carmine Codex MCP Contract

This document fixes the contract for external Codex MCP servers loaded by
Codex or compatible stdio MCP clients. These MCPs are independent from the
OpenWebUI 3571 public bridge and the shared 3572 broker runtime unless a tool
explicitly documents a dedicated Codex broker client path.

## Scope

The stable repo MCP set is tool-only and state/search/validation oriented:

- `aicarmine_repo_state`: deterministic repository state, status, branch,
  commit, and capability reporting.
- `aicarmine_repo_search_det`: deterministic repository search through bounded
  tools such as `rg`, `fd`, `jq`, ast-grep, tree-sitter, and ctags.
- `aicarmine_repo_validate`: deterministic validation wrappers such as
  `git diff --check`, compile checks, ruff, pyright, shellcheck and semgrep.
  Pytest/test execution is not an active default workflow and must not be used
  unless Carmine explicitly asks.

The incubating repo-code MCP is separate from the stable set:

- `aicarmine_repo_code`: candidate code-edit tooling. Proposal and diff-check
  tools are report-only. Exact source patching is available only through
  `aicarmine_repo_code_apply_patch` with `allow_source_write=true`; generic
  command execution and whole-file writes remain excluded.

The incubating Codex ops MCP is separate from repo-editing tools:

- `aicarmine_codex_ops`: local MCP inventory and read-only service-state
  inspection. It may inspect process tables, TCP listeners, repo-local log
  tails and allowlisted MCP stdio inventory, but it must not call HTTP health
  routes, 3571, 3572, `vulkan_helper` or the agentic loop. It must not own or
  restore deleted project test/smoke scripts.

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
- `aicarmine_rag`: Codex-side SQLite/FTS retrieval over the selected Git
  candidate surface. It exposes `aicarmine_rag_context`,
  `aicarmine_rag_index_status` and `aicarmine_rag_reindex`. Reranker failure
  is diagnostic; FTS results remain valid orientation evidence.

The project-local memory MCP is write-capable but semantic and isolated:

- `aicarmine_project_memory`: persistent project memory for verified
  operational facts, preferences, contracts, path mappings, confirmed bug
  causes and architecture decisions. It writes only
  `state/project_memory/project_memory.sqlite3` under the selected repo root,
  never global memory and never RAG/job/planner SQLite databases. Writes are
  available only through semantic tools and explicit confirmation strings.

The dedicated Codex agentic-loop MCP set is explicit and gated:

- `aicarmine_agentic_loop_client`: client for a dedicated multi-instance broker
  on a non-shared port, default `127.0.0.1:3579`. It can start the broker only
  when the configured port is free and the start confirmation token is supplied.
  It cannot reload or restart a live broker; loading new code is a manual
  operator stop/start followed by PID/log/port verification. It must not target
  shared OpenWebUI/3572/model ports such as 3571, 3572, 11434 or 11435.
- `aicarmine_local_subagent`: read-only facade over
  `aicarmine_agentic_loop_client`. It does not call Ollama directly, does not
  host a parallel local tool loop and does not inherit Codex app `/subagents`;
  confirmed runs delegate to the dedicated 3579 broker path.

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
- `C:\Users\carmi\AI\services\codex_bridge\rag_mcp_server.py`
- `C:\Users\carmi\AI\services\codex_bridge\agentic_loop_client_mcp_server.py`
- `C:\Users\carmi\AI\services\codex_bridge\local_subagent_mcp_server.py`

For operator-facing tool selection, stdio JSON client shape and confirmation
gates, use `C:\Users\carmi\AI\services\codex_bridge\MCP_GUIDE.md`.

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

## Test/Smoke Guardrail

Do not create, restore, run or document project test/smoke scripts unless
Carmine explicitly asks for them. MCP reload verification should use read-only
health/status/capability tools, bounded artifact/log/process inspection,
allowlisted MCP stdio inventory probes and targeted compile/lint/diff checks
when appropriate.

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
- `aicarmine_rag` if the Codex RAG server is enabled locally.
- `aicarmine_agentic_loop_client` if dedicated Codex broker calls are enabled locally.
- `aicarmine_local_subagent` if the read-only local-subagent facade is enabled locally.

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
- `aicarmine_rag_index_status` if the Codex RAG server is enabled locally.
- `aicarmine_agentic_loop_health` if the dedicated broker client is enabled locally.
- `aicarmine_local_subagent_health` if the local-subagent facade is enabled locally.

If health is OK, the minimal real-tool gate is:

- `aicarmine_repo_state_status`
- `aicarmine_repo_search_rg` with pattern `AICARMINE_CODEX_MCP_REPO_ROOT|AICARMINE_LAB_REPO`
- `aicarmine_repo_validate_diffcheck`
- `aicarmine_repo_code_unidiff_validate` for the incubator server.
- `aicarmine_service_state_snapshot` with bounded process/log limits.
- `aicarmine_sqlite_readonly_list_databases` with a low `max_results`.
- `aicarmine_job_artifact_list_jobs` with a low `limit`.
- `aicarmine_job_view_list_views`.
- `aicarmine_git_readonly_log` with `max_count=1`.
- `aicarmine_project_memory_search` with a low `limit`.
- `aicarmine_rag_context` with bounded `candidate_limit` and `max_total_chars`.
- `aicarmine_agentic_loop_capabilities` for confirmation tokens and dedicated
  port policy.
- `aicarmine_local_subagent_capabilities` for facade/delegation policy.

Stable MCP reload verification should be based on current health/status outputs
and bounded real-tool reads in the active Codex session. Historical reload
notes are not a substitute for current process/root/runtime evidence.

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
  OpenWebUI, service launchers, `vulkan_helper` or source-write tools; local
  subagent execution must delegate through the dedicated agentic-loop client
  and its confirmation gates
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

The one exception to "no agentic loop" is explicit and named:
`aicarmine_agentic_loop_client` and `aicarmine_local_subagent` may call the
dedicated Codex broker path only when their confirmation arguments are supplied.
That path is not the OpenWebUI 3571 public helper and not the shared 3572
runtime.

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

[mcp_servers.aicarmine_rag]
command = 'C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe'
args = ['-u', 'C:\Users\carmi\AI\services\codex_bridge\rag_mcp_server.py']
cwd = 'C:\Users\carmi\AI'
env = { AICARMINE_CODEX_MCP_REPO_ROOT = 'C:\Users\carmi\AI', AICARMINE_RAG_REPO = 'C:\Users\carmi\AI', AICARMINE_RAG_DB = 'C:\Users\carmi\AI\state\codex_rag\code_rag.sqlite3' }

[mcp_servers.aicarmine_agentic_loop_client]
command = 'C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe'
args = ['-u', 'C:\Users\carmi\AI\services\codex_bridge\agentic_loop_client_mcp_server.py']
cwd = 'C:\Users\carmi\AI'
env = { AICARMINE_CODEX_MCP_REPO_ROOT = 'C:\Users\carmi\AI', AICARMINE_AGENTIC_LOOP_CLIENT_PORT = '3579' }

[mcp_servers.aicarmine_local_subagent]
command = 'C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe'
args = ['-u', 'C:\Users\carmi\AI\services\codex_bridge\local_subagent_mcp_server.py']
cwd = 'C:\Users\carmi\AI'
env = { AICARMINE_CODEX_MCP_REPO_ROOT = 'C:\Users\carmi\AI', AICARMINE_AGENTIC_LOOP_CLIENT_PORT = '3579', AICARMINE_REPO_MCP_MAX_TEXT_CHARS = '24000' }

[mcp_servers.playwright]
command = 'npx'
args = ['-y', '@playwright/mcp@latest', '--headless', '--isolated', '--output-dir', 'C:\Users\carmi\AI\state\playwright_mcp']
cwd = 'C:\Users\carmi\AI'
```

The Playwright MCP entry is a local Codex convenience server, not an
AI-Carmine repo MCP. It should stay stdio-based; do not configure it as a
long-lived HTTP sidecar unless a separate diagnostic proves that is needed.
