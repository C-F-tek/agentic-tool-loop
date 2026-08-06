---
name: aicarmine-repo-diagnosis
description: 'Offline skill for repository diagnosis. Use when investigating runtime failures, configuration problems, or service failures.'
metadata:
  version: 1.0.0
---

# Repository Diagnosis Skill

## Purpose

Provide structured diagnosis workflow for repository-level issues without requiring network access or external services.

## Diagnosis Workflow

### Step 1: Symptom Collection
- Observe the actual behavior (error messages, unexpected results)
- Do not assume causes without evidence

### Step 2: Evidence Gathering
Use MCP tools in this order:
1. `aicarmine_repo_status` → check Git state
2. `aicarmine_git_readonly_log` → check recent commits
3. `aicarmine_git_readonly_diff` → check uncommitted changes
4. `aicarmine_repo_read` → read relevant files
5. `aicarmine_repo_search` → search for relevant code patterns

### Step 3: Hypothesis Generation
- List all plausible causes
- Each hypothesis must have a discriminating check

### Step 4: Evidence Testing
- Run discriminating checks for each hypothesis
- Prefer live runtime evidence over plausible explanations
- Do not stop at the first plausible cause

### Step 5: Confirmed Cause
- Only report the demonstrated causal mechanism
- Distinguish facts, inferences, hypotheses, and unknowns

### Step 6: Minimal Fix
- Smallest contract-preserving correction
- Do not reformat unrelated code
- Do not perform broad refactors unless explicitly requested

### Step 7: Verification
- Original symptom result
- Targeted checks
- Resulting diff
- Modified source-file line counts

### Step 8: Residual Risk
- Only conditions that remain unverified

## Tool Priority

| Operation | MCP Tool (prefer) | Native Cline tool (avoid) |
|-----------|-------------------|--------------------------|
| Read file | `aicarmine_repo_read` | `read_file` |
| Search repo | `aicarmine_repo_search`, `aicarmine_repo_rg_search` | `search_files` |
| List files | `aicarmine_repo_list_files`, `aicarmine_repo_tree` | `list_files` |
| Git operations | `aicarmine_git_readonly_*` | `execute_command git` |
| SQLite queries | `aicarmine_sqlite_readonly_*` | `execute_command sqlite3` |
| Semantic search | `aicarmine_rag_context` | `search_files` + manual read |
| Code validation | `aicarmine_repo_ruff_check`, `pyright_check`, `pytest_run`, `shellcheck`, `semgrep_scan` | `execute_command ruff/pyright/pytest` |

## Completion Format

### Symptom
Observed behavior only.

### Evidence
Concrete MCP, source, Git, process, port, log, payload, or database evidence.

### Confirmed cause
The demonstrated causal mechanism only.

### Minimal fix
The smallest contract-preserving correction.

### Verification
Original symptom check, targeted verification, resulting diff, and modified source-file line counts.

### Residual risk
Only conditions that remain unverified.

Also report, when applicable:
- repository instructions and contracts read
- skills used
- tools used
- fallback used and reason
- payload-completeness limitations