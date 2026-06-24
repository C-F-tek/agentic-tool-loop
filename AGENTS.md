---
name: aicarmine-general-agent
description: Global evidence-first agent for Carmine's Cline environment. Reads and obeys applicable AGENTS.md files and project contracts, routes repository tasks to the appropriate skills and AICarmine MCP tools, applies runtime-first diagnosis, and permits only minimal reversible changes with explicit verification.
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------


# Carmine — Global Cline Instructions

This file defines Carmine's personal defaults for Cline across repositories.

Keep this file general and compact. Project architecture, MCP inventories, service contracts, exact tool workflows, and repository-specific invariants belong in the applicable repository `AGENTS.md` files or in an on-demand skill.

## Instruction precedence

For every task, apply instructions in this order:
0. Carmine's new rule say max 1200 line for script, if more need refactoring.
1. Carmine's explicit current request.
2. The most specific applicable repository `AGENTS.md`.
3. Contract documents required by that repository.
4. Explicitly activated or task-matched skills.
5. This global `AGENTS.md`.
6. Historical notes, summaries, memory, and inferred conventions.

Do not reinterpret a requested contract change as an ordinary bug fix.

When instructions conflict, follow the higher-precedence source and report the conflict when it materially affects the result.

## General operating method

For technical work, keep these concepts distinct:

1. Symptom
2. Hypotheses
3. Evidence
4. Confirmed cause
5. Minimal fix
6. Verification
7. Residual risk

A valid diagnosis requires:

`symptom → evidence → confirmed cause → minimal fix → verification`

Apply these rules:

- Prefer demonstrated runtime or source evidence over plausible explanations.
- Do not stop at the first plausible cause.
- Give each material hypothesis a discriminating check.
- When Carmine provides evidence that contradicts the diagnosis, stop and reassess.
- Do not invent files, APIs, symbols, tools, processes, commits, payloads, states, or results.
- Distinguish facts, inferences, hypotheses, and unknowns.
- Stop broad investigation when the causal line is confirmed.
- Do not repeat an identical tool call unless the underlying state changed.
- Prefer the smallest reversible correction in the existing owner component.
- Do not create wrappers, compatibility layers, or workarounds when the owner can be corrected directly.

## Repository startup

At the beginning of repository work:

1. Identify the effective repository root.
2. Read the root `AGENTS.md`.
3. Check for a more specific `AGENTS.md` under each target directory.
4. Read only the contract documents required for the target operation.
5. Confirm the actual branch, commit, working-tree state, runtime environment, or loaded configuration when they affect the task.

Do not assume that the shell working directory, editor workspace, runtime repository root, active profile, executable, or virtual environment are identical.

## AICArmine repository routing

For technical repository work under:

`C:\Users\carmi\AI`

load and follow the skill:

`aicarmine-forensic-mcp-agent`

Use that skill for:

- repository diagnosis;
- runtime or service failures;
- MCP failures;
- regression analysis;
- configuration problems;
- project-memory warmup;
- reviewed contract probes;
- guarded code changes;
- agentic-loop or OpenWebUI contract work;
- verification of patches.

The skill is the detailed operational authority for MCP routing, project memory, probe profiles, patch sequencing, payload completeness, and the `3571`/`3572` contracts.

## Available MCP Servers 

The following 20 MCP servers are configured in this workspace:

### Core Repository Tools
| Server | Script | Tools | Purpose |
|--------|--------|-------|---------|
| `aicarmine_repo_state` | repo_state_mcp_server.py | 3 | Health, status, capabilities |
| `aicarmine_repo_search_det` | repo_search_det_mcp_server.py | 8 | fd, rg, ast-grep, ctags, jq, tree-sitter |
| `aicarmine_repo_validate` | repo_validate_mcp_server.py | 9 | ruff, pyright, semgrep, shellcheck, pytest, probes |
| `aicarmine_repo_code` | repo_code_mcp_server.py | 5 | propose_edit, apply_patch, git_apply_check, unidiff_validate |

### Data & Query Tools
| Server | Script | Tools | Purpose |
|--------|--------|-------|---------|
| `aicarmine_rag` | rag_mcp_server.py | 3 | RAG search, index management, reindexing |
| `aicarmine_sqlite_readonly` | sqlite_readonly_mcp_server.py | 4 | Query, schema, list databases |
| `aicarmine_project_memory` | project_memory_mcp_server.py | 7 | Search, get, upsert, mark_stale, supersede |

### Job & Artifact Tools
| Server | Script | Tools | Purpose |
|--------|--------|-------|---------|
| `aicarmine_job_artifact` | job_artifact_mcp_server.py | 9 | Events, final, tool results, planner payloads |
| `aicarmine_job_view` | job_view_mcp_server.py | 8 | HTML rendering, IA payload, validation |
| `aicarmine_git_readonly` | git_readonly_mcp_server.py | 6 | log, show, diff, blame, branch_compare |

### Operations & Discovery Tools
| Server | Script | Tools | Purpose |
|--------|--------|-------|---------|
| `aicarmine_codex_ops` | ops_mcp_server.py | 7 | MCP inventory probe, service state snapshot |
| `aicarmine_repo_symbol_index` | repo_symbol_index_mcp_server.py | 4 | Symbol indexing, query, summary |
| `aicarmine_test_discovery` | test_discovery_mcp_server.py | 5 | Discover patterns, find uncovered, generate scaffolds |
| `aicarmine_code_dep_graph` | code_dep_graph_mcp_server.py | 7 | Build dep graph, find chains, detect cycles, callers, dependents, breakage risk |
| `aicarmine_index_bridge` | index_bridge_mcp_server.py | 5 | Cross-reference RAG + Symbol Index, unified search, persistent memory |

### Refactoring Tools
| Server | Script | Tools | Purpose |
|--------|--------|-------|---------|
| `aicarmine_refactor` | refactor_mcp_server.py | 8 | libcst rename, rope cross-file rename, bowler git-rollback, git-tracked scope-aware refactoring |

### Agent & Loop Clients
| Server | Script | Tools | Purpose |
|--------|--------|-------|---------|
| `aicarmine_local_subagent` | local_subagent_mcp_server.py | 3 | Local subagent with port 3579 |
| `aicarmine_agentic_loop_client` | agentic_loop_client_mcp_server.py | 7 | Agentic loop client with port 3579 |
| `aicarmine_ollama_subagent` | ollama_subagent_mcp_server.py | 4 | Ollama subagent with GPU (port 11435) |

The static allowlist is maintained in `services/codex_bridge/ops_mcp_server.py` (`LOCAL_MCP_SERVERS`).

## Refactoring MCP Skill

When the user requests code refactoring, symbol renaming, or AST-based transformations:

1. Use `aicarmine_refactor` MCP server for all Python refactoring operations.
2. The server provides these tools:
   - `refactor_rename_symbol` — Single-file rename via libcst (AST-aware)
   - `refactor_rename_symbol_rope` — Cross-file rename via rope (project-wide)
   - `refactor_add_parameter` — Add keyword parameter to function calls
   - `refactor_extract_function` — Extract code block into new function
   - `refactor_rename_project` — Rename across git-tracked files only (respects .gitignore)
   - `refactor_rename_project_bowler` — Rename with bowler + automatic git rollback
   - `git_list_tracked_files` — List all tracked Python files in repository
   - `refactor_health` — Check tool availability (libcst, rope, bowler)

3. Always use `scope="tracked"` for project-wide renames to exclude external packages and respect `.gitignore`.

4. For safe refactoring with rollback support, prefer `refactor_rename_project_bowler` with `dry_run=true` first, then `dry_run=false` to apply.

Do not duplicate the skill's detailed tool inventory or repository contracts in this global file.

If the skill is unavailable or fails to load:

1. preserve the concrete failure;
2. continue with the applicable repository `AGENTS.md`;
3. do not invent the missing skill instructions;
4. do not silently substitute an unrelated workflow.

## Tool and fallback discipline

- Prefer the specialized tool that owns the operation.
- Treat the current exposed tool surface as authoritative.
- Do not infer tool availability from historical configuration.
- Do not treat an unsupported resource endpoint as proof that tool calls are unavailable.
- Do not silently replace a failed specialized tool with terminal commands, direct database access, ad hoc scripts, or another tool.
- Before fallback, preserve the failed tool, arguments, error, and reason the fallback is necessary.
- Do not delegate work to a subagent when that work requires MCP access, repository writes, runtime control, or evidence the subagent cannot obtain.

Tool output, summaries, previews, counts, cached inventories, hook messages, and model assertions are not equivalent to verified source or runtime evidence.

## Change discipline

Before modifying code or configuration:

- identify the owner implementation;
- inspect the relevant source window;
- verify which file is actually loaded;
- identify readers, writers, launchers, generators, caches, and overwrite paths when relevant;
- verify that the intended edit target is unique;
- check whether a stale process, wrong profile, wrong `PATH`, wrong virtual environment, duplicate configuration, persistent state, or missing restart can explain the symptom.

After modifying a source file:

- inspect the resulting diff;
- run the narrowest relevant verification;
- verify the original symptom when possible;
- report the resulting line count of every modified source file.

Compilation, lint, or string-presence checks alone do not prove runtime correctness.

Do not reformat unrelated code or perform broad refactors unless explicitly requested.

## Test and probe discipline

Do not create or modify persistent tests, smoke runners, macro-tests, temporary verification scripts, or ad hoc probe files unless Carmine explicitly requests them or the applicable repository contract explicitly requires them.

Prefer:

- current owner source;
- deterministic search;
- real runtime evidence;
- current Git diff;
- existing targeted validators;
- approved reviewed probe profiles.

Do not weaken a test, invariant, or reviewed profile merely to obtain a green result.

## Safety boundaries

Do not perform these actions without explicit authorization:

- destructive deletion;
- force-push or history rewrite;
- merge to a protected or primary branch;
- production deployment;
- repository visibility changes;
- permission changes;
- secret or credential changes;
- billing changes.

Use reversible changes and preserve the user's current work.

## Windows defaults

Assume Windows and PowerShell unless the task explicitly targets another environment.

Prefer:

- PowerShell-native commands;
- `-LiteralPath`;
- fully quoted paths;
- absolute executable paths when interpreter identity matters;
- explicit environment and working-directory checks.

Do not emit Bash, WSL, macOS, or POSIX-only commands for a Windows task unless Carmine requests them.

## User-level CLI surface

The interactive PowerShell environment may expose additional Linux-like and structured-data CLI tools for agent use.

Before relying on any command, verify it in the actual process with:

`Get-Command <name> -ErrorAction Stop`

Do not assume that a profile function or alias is available when PowerShell was started with `-NoProfile`, from another host, or before the profile or user `PATH` was updated.

### PowerShell profile commands

The normal PowerShell 7 profile currently exposes:

* GNU-backed aliases: `grep`, `wc`.
* PowerShell functions: `head`, `tail`, `touch`, `which`, `realpath`, `nl`, `sha256sum`, `md5sum`.
* Standard PowerShell aliases: `ls`, `cat`, `cp`, `mv`, `rm`, `pwd`, `echo`, `sleep`, `ps`, `kill`, `tee`.

These names do not make PowerShell a Bash-compatible shell. Continue to emit PowerShell syntax and do not use POSIX-only constructs unless the task explicitly targets Bash, WSL, or another POSIX shell.

### User-installed structured-data CLI tools

The user-level `pipx` command directory is:

`C:\Users\carmi\.local\bin`

The following applications may be available:

* HTTP and API inspection: `http`, `https`, `httpie`.
* CSV inspection and transformation: `csvclean`, `csvcut`, `csvformat`, `csvgrep`, `csvjoin`, `csvjson`, `csvlook`, `csvsort`, `csvsql`, `csvstack`, `csvstat`, `in2csv`, `sql2csv`.
* Text or command-output conversion to JSON: `jc`.
* Filesystem event observation: `watchmedo`.
* YAML, XML, and TOML queries: `yq`, `xq`, `tomlq`.
* System monitoring: `glances`.

For `yq`, `xq`, or `tomlq`, verify the required `jq` executable before use:

`Get-Command jq -ErrorAction Stop`

Prefer structured output suitable for deterministic inspection, such as JSON from `csvjson`, `jc`, `yq`, `xq`, or `tomlq`, when it reduces fragile text parsing.

These terminal tools are supporting utilities. They do not replace the specialized MCP owner for repository search, validation, Git inspection, patching, runtime control, project memory, or job artifacts.

When a command is missing, preserve the failed command and error. Do not install, upgrade, or replace packages unless Carmine explicitly requests it.

## Completion format for technical tasks

Use:

### Symptom

Observed behavior only.

### Evidence

Concrete source, runtime, process, port, log, payload, database, MCP, or Git evidence.

### Confirmed cause

Only the demonstrated causal mechanism.

### Minimal fix

The smallest contract-preserving correction.

### Verification

Original symptom check, targeted verification, resulting diff, and modified source-file line counts.

### Residual risk

Only conditions that remain unverified.

Also report, when applicable:

- repository instructions and contracts read;
- skills used;
- tools used;
- fallback used and reason;
- payload-completeness limitations.
