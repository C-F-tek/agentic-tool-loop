# AI-Carmine Deterministic Repo MCP Contract

This document fixes the contract for the three external deterministic repo MCP
servers loaded by Codex. These MCPs are independent from the OpenWebUI and
broker runtime.

## Scope

The repo MCP set is tool-only and read/validation oriented:

- `aicarmine_repo_state`: deterministic repository state, status, branch,
  commit, and capability reporting.
- `aicarmine_repo_search_det`: deterministic repository search through bounded
  tools such as `rg`, `fd`, `jq`, ast-grep, tree-sitter, and ctags.
- `aicarmine_repo_validate`: deterministic validation wrappers such as
  `git diff --check`, compile checks, pytest, ruff, pyright, shellcheck, and
  semgrep.

The shared implementation lives in:

- `C:\Users\carmi\AI\services\codex_bridge\repo_mcp_common.py`

Server entrypoints:

- `C:\Users\carmi\AI\services\codex_bridge\repo_state_mcp_server.py`
- `C:\Users\carmi\AI\services\codex_bridge\repo_search_det_mcp_server.py`
- `C:\Users\carmi\AI\services\codex_bridge\repo_validate_mcp_server.py`

## Runtime Requirements

Required Python executable:

```text
C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe
```

Required environment:

```text
AICARMINE_LAB_REPO=C:\Users\carmi\AI
AICARMINE_USEFUL_TOOLS_ROOT=C:\Users\carmi\AI\services\useful_tools
AICARMINE_REPO_MCP_MAX_TEXT_CHARS=24000
```

The effective health gate must report:

- `python_executable`: `C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe`
- `repo_root`: `C:\Users\carmi\AI`
- `cwd`: `C:\Users\carmi\AI`
- `git_root_ok`: `true`
- `branch`: `codex/rag-mcp-solid-base`

## Self-Test Commands

Run self-tests with the absolute Python executable:

```powershell
& "C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe" "C:\Users\carmi\AI\services\codex_bridge\repo_state_mcp_server.py" --self-test
& "C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe" "C:\Users\carmi\AI\services\codex_bridge\repo_search_det_mcp_server.py" --self-test
& "C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe" "C:\Users\carmi\AI\services\codex_bridge\repo_validate_mcp_server.py" --self-test
```

The server self-tests must pass before the MCP entries are considered valid for
Codex reload testing.

## Codex Reload Gate

After a Codex reload or new session, the MCP list must expose:

- `aicarmine_repo_state`
- `aicarmine_repo_search_det`
- `aicarmine_repo_validate`

Required health tool calls:

- `aicarmine_repo_state_health`
- `aicarmine_repo_search_det_health`
- `aicarmine_repo_validate_health`

If health is OK, the minimal real-tool gate is:

- `aicarmine_repo_state_status`
- `aicarmine_repo_search_rg` with pattern `AICARMINE_LAB_REPO`
- `aicarmine_repo_validate_diffcheck`

Codex reload verification on 2026-06-11 passed these gates in this session.
The `rg` result was intentionally bounded by MCP text limits, so only the
successful tool result and count are used as the gate, not the full match set.

## Non-Negotiable Exclusions

These MCPs must not introduce or depend on:

- broker HTTP
- port `3571`
- port `3572`
- OpenWebUI
- agentic loop
- general dispatcher
- write tools or generic command execution in this phase

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
env = { AICARMINE_LAB_REPO = 'C:\Users\carmi\AI', AICARMINE_USEFUL_TOOLS_ROOT = 'C:\Users\carmi\AI\services\useful_tools', AICARMINE_REPO_MCP_MAX_TEXT_CHARS = '24000' }

[mcp_servers.aicarmine_repo_search_det]
command = 'C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe'
args = ['C:\Users\carmi\AI\services\codex_bridge\repo_search_det_mcp_server.py']
env = { AICARMINE_LAB_REPO = 'C:\Users\carmi\AI', AICARMINE_USEFUL_TOOLS_ROOT = 'C:\Users\carmi\AI\services\useful_tools', AICARMINE_REPO_MCP_MAX_TEXT_CHARS = '24000' }

[mcp_servers.aicarmine_repo_validate]
command = 'C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe'
args = ['C:\Users\carmi\AI\services\codex_bridge\repo_validate_mcp_server.py']
env = { AICARMINE_LAB_REPO = 'C:\Users\carmi\AI', AICARMINE_USEFUL_TOOLS_ROOT = 'C:\Users\carmi\AI\services\useful_tools', AICARMINE_REPO_MCP_MAX_TEXT_CHARS = '24000' }
```
