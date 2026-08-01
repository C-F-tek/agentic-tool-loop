# Skills and Specifications for Software Engineering, Security, Debugging, and Scientific Method

This document defines the operational specifications for the key domains available in this Cline environment, based on the AICarmine forensic methodology and MCP tool surface.

## Table of Contents

1. [Software Engineering Specification](#1-software-engineering-specification)
2. [Security Specification](#2-security-specification)
3. [Debugging Specification](#3-debugging-specification)
4. [Scientific Method of Problem Solving](#4-scientific-method-of-problem-solving)
5. [MCP Tool Routing Specification](#5-mcp-tool-routing-specification)
6. [Repository Operations Specification](#6-repository-operations-specification)
7. [Runtime Diagnostics Specification](#7-runtime-diagnostics-specification)
8. [Patch and Change Management Specification](#8-patch-and-change-management-specification)

---

## 1. SOFTWARE ENGINEERING SPECIFICATION

### 1.1 Core Principles

- **Evidence-first development**: Every change must be backed by concrete source, runtime, or Git evidence.
- **Minimal reversible correction**: Prefer the smallest contract-preserving change.
- **Owner-component discipline**: Modify the existing owner implementation, not wrappers or workarounds.
- **Windows-first development**: Assume Windows/PowerShell unless explicitly targeting another environment.

### 1.2 Available Capabilities

| Capability | Description | Tool/Method |
|-----------|-------------|-------------|
| Code proposal | Structured code edit proposals without writing | `aicarmine_repo_code_propose_edit` |
| Diff validation | Validate unified diff structure | `aicarmine_repo_code_unidiff_validate` |
| Git apply check | Verify diff applies without applying | `aicarmine_repo_code_git_apply_check` |
| Patch application | Apply validated patches | `aicarmine_repo_code_apply_patch` |
| File search | Deterministic file search | `aicarmine_repo_search_fd` |
| Content search | Ripgrep-style content search | `aicarmine_repo_search_rg` |
| Semantic search | AST-level code search | `aicarmine_repo_search_ast_grep` |
| Symbol extraction | ctags-based symbol extraction | `aicarmine_repo_search_ctags` |
| Code parsing | Tree-sitter syntax parsing | `aicarmine_repo_search_tree_sitter_parse` |

### 1.3 Workflow

```
Requirement → Evidence gathering → Owner identification → Minimal change → Diff validation → Verification
```

### 1.4 Quality Gates

- [ ] Change affects only the targeted component
- [ ] No unrelated code reformatting
- [ ] Diff validated before application
- [ ] Line count reported for modified files
- [ ] Original symptom verified after change

---

## 2. SECURITY SPECIFICATION

### 2.1 Core Principles

- **No explicit authorization = no sensitive operations**: No deployment, permission changes, secret modifications, or visibility changes without explicit user approval.
- **Reversible changes only**: All modifications must be reversible.
- **Evidence isolation**: Symptoms, hypotheses, and evidence must be kept separate from security decisions.

### 2.2 Security Boundaries

| Action | Authorization Required | Notes |
|--------|----------------------|-------|
| Deletion | Explicit | Destructive operations require approval |
| Force-push | Explicit | History rewrites require approval |
| Merge to protected branch | Explicit | Primary branch changes require approval |
| Production deployment | Explicit | Deployment requires approval |
| Visibility changes | Explicit | Repository visibility changes require approval |
| Permission changes | Explicit | Access control changes require approval |
| Secret/credential changes | Explicit | Secret management requires approval |
| Billing changes | Explicit | Billing changes require approval |

### 2.3 Security Tools and Methods

| Tool | Purpose | Safety Level |
|------|---------|--------------|
| `aicarmine_repo_validate_semgrep` | Static security scanning | Automated |
| `aicarmine_repo_validate` | Repository validation | Automated |
| `aicarmine_repo_search` | Content search for secrets/leaks | Advisory |
| Git history | Audit trail | Read-only |

### 2.4 Security Checklist

- [ ] No secrets or credentials in diffs
- [ ] No permission or visibility changes without approval
- [ ] No production deployment without approval
- [ ] All changes reversible via Git
- [ ] Security scan results documented

---

## 3. DEBUGGING SPECIFICATION

### 3.1 Scientific Debugging Method

Based on the forensic methodology defined in `AGENTS.md`:

```
Symptom → Evidence → Confirmed cause → Minimal fix → Verification
```

### 3.2 Debugging Workflow

1. **Symptom identification**: Document the exact observed behavior.
2. **Hypothesis generation**: List all plausible explanations.
3. **Evidence gathering**: Use MCP tools to collect discriminating evidence.
4. **Cause confirmation**: Eliminate hypotheses until only one remains.
5. **Minimal fix**: Apply the smallest possible correction.
6. **Verification**: Confirm the symptom is resolved.
7. **Residual risk**: Document what remains unverified.

### 3.3 Debugging Tools

| Tool | Purpose | Example Use |
|------|---------|-------------|
| `aicarmine_git_readonly_log` | Review commit history | Find when a regression was introduced |
| `aicarmine_git_readonly_diff` | Inspect changes | Compare working tree vs committed state |
| `aicarmine_git_readonly_blame` | Line-level blame | Identify who changed a specific line |
| `aicarmine_service_state_logs` | Read log files | Diagnose runtime errors |
| `aicarmine_service_state_processes` | Check running processes | Verify service identity |
| `aicarmine_service_state_ports` | Check listening ports | Verify service connectivity |
| `aicarmine_job_view_render` | Render job view | Inspect agentic loop events |
| `aicarmine_job_artifact_events` | Read job events | Trace agentic loop execution |

### 3.4 Debugging Checklist

- [ ] Symptom clearly documented
- [ ] Multiple hypotheses considered
- [ ] Evidence gathered from runtime/source/Git
- [ ] Cause confirmed, not just hypothesized
- [ ] Fix is minimal and reversible
- [ ] Original symptom verified as resolved
- [ ] Residual risks documented

---

## 4. SCIENTIFIC METHOD OF PROBLEM SOLVING

### 4.1 Methodology

The AICarmine forensic method applies the scientific method to software engineering:

```
1. Observe symptom
2. Form hypotheses
3. Design discriminating tests
4. Collect evidence
5. Confirm cause
6. Implement minimal fix
7. Verify result
8. Document residual risk
```

### 4.2 Principles

| Principle | Description | Application |
|-----------|-------------|-------------|
| Evidence over speculation | Prefer demonstrated evidence over plausible explanations | Use MCP tools, not assumptions |
| Multiple hypotheses | Consider all plausible causes before acting | List and test each hypothesis |
| Discriminating tests | Each test should eliminate at least one hypothesis | Design tests that rule out alternatives |
| Minimal intervention | Make the smallest possible change | Prefer surgical fixes over refactors |
| Reversibility | All changes must be reversible | Use Git, document diffs |
| Verification | Confirm the fix resolves the symptom | Re-test the original symptom |

### 4.3 Problem-Solving Checklist

- [ ] Symptom clearly stated
- [ ] At least 2 hypotheses considered
- [ ] Each hypothesis has a discriminating test
- [ ] Evidence collected from reliable sources
- [ ] Cause confirmed by eliminating alternatives
- [ ] Fix is the smallest possible correction
- [ ] Result verified against original symptom
- [ ] Residual risks documented

---

## 5. MCP TOOL ROUTING SPECIFICATION

### 5.1 Available MCP Servers

| Server | Purpose | Key Tools |
|--------|---------|-----------|
| `aicarmine-codex-app` | Core MCP bridge | Health, search, read, apply |
| `aicarmine-repo-state` | Repository state | Status, capabilities |
| `aicarmine-repo-search-det` | Deterministic search | FD, ripgrep, ast-grep |
| `aicarmine-rag` | Semantic knowledge | Context search, index status |
| `aicarmine-repo-validate` | Validation | Diffcheck, ruff, pyright |
| `aicarmine-git-readonly` | Git operations | Log, show, diff, blame |
| `aicarmine-sqlite-readonly` | Database queries | Schema, query |
| `aicarmine-job-artifact` | Job inspection | Events, final output |
| `aicarmine-job-view` | Job rendering | Dashboard, events, IA |
| `aicarmine-project-memory` | Persistent memory | Search, get, upsert |
| `aicarmine-agentic-loop-client` | Agentic loop | Run, status, result |

### 5.2 Tool Selection Rules

1. **Prefer the specialized tool**: Use the MCP tool that owns the operation.
2. **Treat current surface as authoritative**: Use the exposed tool schema, not historical knowledge.
3. **No tool invention**: Do not assume tools exist that aren't in the current schema.
4. **Fallback preservation**: Document failed tools, arguments, errors, and fallback reasons.

### 5.3 MCP Workflow

```
Task → Identify owner tool → Verify tool availability → Execute → Verify result
```

---

## 6. REPOSITORY OPERATIONS SPECIFICATION

### 6.1 Repository Startup Checklist

- [ ] Effective repository root identified
- [ ] Root `AGENTS.md` read
- [ ] Directory-specific `AGENTS.md` checked
- [ ] Required contracts read
- [ ] Branch, commit, working-tree state confirmed
- [ ] Runtime environment verified

### 6.2 Repository Tools

| Tool | Purpose | Method |
|------|---------|--------|
| `aicarmine_repo_list_files` | File listing | Bounded recursive listing |
| `aicarmine_repo_search` | Content search | ripgrep-style |
| `aicarmine_repo_read` | File reading | Multi-file read |
| `aicarmine_repo_apply_patch` | Patch application | Validated diff application |
| `aicarmine_repo_validate` | Validation | Repository validation |
| `aicarmine_repo_git_apply_check` | Apply check | Git apply --check |

### 6.3 Repository Checklist

- [ ] Repository root confirmed
- [ ] Current branch identified
- [ ] Working-tree state documented
- [ ] Diff inspected before application
- [ ] Line count reported after changes

---

## 7. RUNTIME DIAGNOSTICS SPECIFICATION

### 7.1 Runtime Diagnostics Workflow

```
Symptom → Check process → Check port → Check log → Check source → Confirm cause
```

### 7.2 Runtime Tools

| Tool | Purpose | Output |
|------|---------|--------|
| `aicarmine_codex_ops_health` | MCP health | Service availability |
| `aicarmine_service_state_ports` | Port check | Listening sockets |
| `aicarmine_service_state_processes` | Process check | Running processes |
| `aicarmine_service_state_logs` | Log check | Log file tails |
| `aicarmine_service_state_snapshot` | Full snapshot | Combined view |

### 7.3 Runtime Checklist

- [ ] Process identity verified
- [ ] Port connectivity confirmed
- [ ] Log state examined
- [ ] Source state checked
- [ ] Configuration validated

---

## 8. PATCH AND CHANGE MANAGEMENT SPECIFICATION

### 8.1 Patch Workflow

```
Proposal → Validation → Apply-check → Apply → Verify
```

### 8.2 Patch Types

| Type | Use Case | Method |
|------|----------|--------|
| `structured_edit` | Multi-file changes | Preferred for most edits |
| `unified_diff` | Complete file changes | When full diff exists |
| `old_text/new_text` | Targeted replacements | Small targeted changes |

### 8.3 Patch Checklist

- [ ] Change proposal documented
- [ ] Diff validated before application
- [ ] Apply-check passed
- [ ] Patch applied with confirmation
- [ ] Resulting diff inspected
- [ ] Line count reported
- [ ] Original symptom verified

---

## SUMMARY

This document defines the operational specifications for:

1. **Software Engineering**: Evidence-first, minimal change, owner-component discipline.
2. **Security**: No sensitive operations without explicit authorization.
3. **Debugging**: Scientific method applied to runtime diagnosis.
4. **Scientific Method**: Hypothesis-driven problem solving with evidence.
5. **MCP Tool Routing**: Prefer specialized tools, document fallbacks.
6. **Repository Operations**: Confirm state before editing, verify after.
7. **Runtime Diagnostics**: Check process, port, log, source in order.
8. **Patch Management**: Validate, apply-check, apply, verify workflow.

All specifications follow the AICarmine forensic methodology: symptom → evidence → confirmed cause → minimal fix → verification.