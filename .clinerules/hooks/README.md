# AICarmine Cline Hooks Architecture

## Overview

This directory contains PowerShell-based Cline lifecycle hooks that provide deterministic MCP routing, tool observation, and post-task cleanup for the AI-Carmine project workspace.

## Hook Surface

| Hook | File | Trigger Point | Purpose |
|------|------|---------------|---------|
| **TaskStart** | `TaskStart.ps1` | Before task execution | Bootstrap MCP server inventory + routing hints |
| **UserPromptSubmit** | `UserPromptSubmit.ps1` | Before user prompt submission | MCP routing hint generation + routing state persistence |
| **PreToolUse** | `PreToolUse.ps1` | Before each tool call | Pre-tool observation: detect write tools on read-only tasks, identical retries, native-after-MCP-failure |
| **PostToolUse** | `PostToolUse.ps1` | After each tool call | Post-tool correlation: outcome tracking, failure signal logging, pending call resolution |
| **TaskResume** | `TaskResume.ps1` | Task resume | Restores task context from observation archive + routing state + reindex status |
| **TaskComplete** | `TaskComplete.ps1` | Task completion | Observation archive summary + stale routing purge + reindex verification + instructions |
| **PreCompact** | `PreCompact.ps1` | Before Cline context compaction | Preserves task context across conversation truncation |

## Architecture

```
.clinerules/hooks/
├── lib/
│   ├── aicarmine_cline_contract_probe.ps1        # Contract validation helper
│   ├── aicarmine_cline_mcp_router.ps1            # Deterministic MCP routing hint generator
│   ├── aicarmine_cline_pretool_observer.ps1      # Pre-tool observation + routing state management
│   ├── aicarmine_cline_posttool_observer.ps1     # Post-tool correlation + failure signal logging
│   ├── aicarmine_cline_task_bootstrap.ps1        # TaskStart bootstrap + TaskResume observation payloads
│   └── aicarmine_cline_precompact_continuity.ps1 # PreCompact context preservation across truncation
├── TaskComplete.ps1
├── TaskResume.ps1
├── TaskStart.ps1
├── PostToolUse.ps1
├── PreToolUse.ps1
├── PreCompact.ps1
├── UserPromptSubmit.ps1
└── reindex_status.json                           # Reindex status metadata (written by TaskComplete)
```

## Key Components

### 1. MCP Router (`aicarmine_cline_mcp_router.ps1`)

Deterministic scoring system that maps task intent to MCP tool recommendations:

- **Scoring classes**: `repository_validation`, `repository_patch`, `repository_refactor`, `repository_search`, `code_format`, `code_analysis`, `data_query`, `project_memory`, `repository_state`, `git_readonly`, `job_diagnostics`, `semantic_search`, `code_complexity`, `mcp_batch_proxy`
- **TieOrder**: Ensures deterministic ranking when multiple classes score equally
- **Constraints output**: Injects read-only, existing-diff, dry-run constraints into context

### 2. PreToolObserver (`aicarmine_cline_pretool_observer.ps1`)

Atomic routing state management with SHA-256 correlation:

- **Mutex locking**: Local mutex per task key prevents concurrent state corruption
- **Atomic writes**: Temp file + rename pattern ensures no partial state files
- **Correlation tracking**: 32-entry bounded recent calls + 32-entry pending calls
- **Advisory codes**: `recommended_mcp_selected`, `native_used_while_mcp_recommended`, `identical_tool_call_repeated`, `identical_tool_call_after_observed_failure`, `native_after_observed_mcp_failure`, `read_only_write_tool_candidate`

### 3. PostToolObserver (`aicarmine_cline_posttool_observer.ps1`)

Outcome correlation and failure signal logging:

- **Correlation methods**: `invocation_id`, `tool_call_sha256`, `unique_identity`
- **Outcome detection**: Distinguishes success/failure via `isError`, `success`, `error`, `status` fields
- **Failure signals**: `is_error_true`, `success_false`, `error_field_present`, `status_failure`, `result_error_prefix`, `none`

### 4. TaskComplete (`TaskComplete.ps1`)

Post-task cleanup, reindex verification, and index freshness:

- **Observation archive summary**: Counts pre/post observations + routing files
- **Stale routing purge**: Removes routing state files older than 24h
- **Reindex status check**: Reads `reindex_status.json` to determine if reindex was already completed
- **Reindex instructions**: Outputs `mcp_batch_execute` command when reindex not done or failed — includes Wily build step
- **Metadata write**: Writes updated `reindex_status.json` for TaskResume to read
- **Error output**: All errors written to `errorMessage` field (not silently ignored)

### 5. TaskResume (`TaskResume.ps1`)

Task context restoration on session resume:

- **Conditional injection**: Only injects contextModification when observation archive has data OR reindex metadata exists
- **No empty hint messages**: Returns empty contextModification when observer root not found and no observations exist
- **Observation archive state**: Reports pre/post observation counts + routing file count (when observations exist)
- **Reindex status**: Reads `reindex_status.json` and injects success/failure status with action instructions
- **Error output**: All errors written to `errorMessage` field (not silently ignored)

### 6. PreCompact (`PreCompact.ps1`)

Context preservation across Cline conversation compaction (truncation):

- **Compacted context summary**: Injects task context so agent retains MCP routing state, observation counts, and index freshness after truncation
- **Failure warning**: Alerts about recent failure signals detected during task
- **Index freshness note**: Reminds about stale indexes needing reindex
- **Error output**: All errors written to `errorMessage` field (not silently ignored)

## Error Output Policy

All 7 hooks now write errors to the `errorMessage` field instead of silently ignoring them:

| Hook | Error Collection Pattern |
|------|-------------------------|
| **TaskStart** | `$errorMessages += "TaskStart failed: $_"` → `errorMessage = ($errorMessages -join '; ')` |
| **TaskResume** | `$errorMessages += "TaskResume failed: $_"` → `errorMessage = ($errorMessages -join '; ')` |
| **TaskComplete** | `$errorMessages += "Observer root not found — observation archive unavailable"` → `errorMessage = ($errorMessages -join '; ')` |
| **PreToolUse** | `$errorMessages += "PreToolUse failed: $_"` → `errorMessage = ($errorMessages -join '; ')` |
| **PostToolUse** | `$errorMessages += "PostToolUse failed: $_"` → `errorMessage = ($errorMessages -join '; ')` |
| **PreCompact** | `$errorMessages += "PreCompact failed: $_"` → `errorMessage = ($errorMessages -join '; ')` |
| **UserPromptSubmit** | `$errorMessages += "UserPromptSubmit failed: $_"` → `errorMessage = ($errorMessages -join '; ')` |

Errors are collected in an `$errorMessages` array and joined with `; ` separator before being written to the `errorMessage` output field. This ensures errors are visible to Cline rather than silently dropped.

## Wily Integration (Code Complexity)

### New MCP Server: `aicarmine_wily`

Created `services/codex_bridge/wily_mcp_server.py` — wraps Wily CLI for code complexity analysis:

- **Tools**: `wily_health`, `wily_report`, `wily_rank`, `wily_build`, `wily_index`, `wily_diff`, `wily_list_metrics`
- **Metrics**: raw lines, Halstead length, cyclomatic complexity, maintainability index
- **Cache**: Uses `~/.wily/` directory with git revision history

### MCP Router Integration

Added `code_complexity` scoring class to `aicarmine_cline_mcp_router.ps1`:

- **Score 100**: Keywords like `wily`, `code complexity`, `cyclomatic`, `halstead`, `maintainability`, `raw lines`
- **Score 80**: Keywords like `complexity report`, `rank files`, `code quality`, `code smell`, `high cyclomatic`
- **Score 60**: Keywords like `code metric`, `metric rank`, `function complexity`, `file metrics`

### TaskComplete Reindex Batch

Updated reindex batch instructions to include Wily:

```python
use_mcp_tool('aicarmine_mcp_batch_proxy', 'mcp_batch_execute', {
  'operations': [
    {'server': 'aicarmine_rag', 'tool': 'aicarmine_rag_reindex', 'args': {'source': 'git', 'mode': 'delta'}},
    {'server': 'aicarmine_repo_symbol_index', 'tool': 'build', 'args': {}},
    {'server': 'aicarmine_index_bridge', 'tool': 'build', 'args': {}},
    {'server': 'aicarmine_wily', 'tool': 'wily_build', 'args': {'mode': 'delta'}}
  ],
  'compress': true
})
```

### Usage Examples

**Report file metrics:**
```python
use_mcp_tool("aicarmine_wily", "wily_report", {"path": "services/aicarmine_broker/planner.py"})
```

**Rank files by complexity:**
```python
use_mcp_tool("aicarmine_wily", "wily_rank", {"metric": "cyclomatic", "limit": 20})
```

**Rebuild Wily cache:**
```python
use_mcp_tool("aicarmine_wily", "wily_build", {"mode": "delta"})
```

## Smart Improvements Implemented

### TaskComplete Hook (Updated)

The TaskComplete hook now provides:

1. **Observation archive summary** — Shows how many pre/post observations were recorded during the task
2. **Stale routing state purge** — Automatically removes routing files older than 24 hours
3. **Reindex status verification** — Reads `reindex_status.json` to check if reindex was already completed
4. **Conditional instructions** — Outputs "Already completed" message when reindex done, or mcp_batch_execute instructions when not done/failed
5. **Wily build step** — Includes Wily in the reindex batch workflow
6. **Error output** — All errors written to `errorMessage` field

### TaskResume Hook (Updated)

The TaskResume hook now:

1. **Conditional context injection** — Only injects contextModification when observation archive has data OR reindex metadata exists
2. **No empty hint messages** — Returns empty contextModification when observer root not found and no observations exist (prevents "AICARMINE MCP ROUTING HINT" spam during ongoing chat)
3. **Reindex status injection** — Reads `reindex_status.json` and reports success/failure with action instructions
4. **Error output** — All errors written to `errorMessage` field

### TaskStart Bootstrap (Updated)

The bootstrap now includes:

1. **Batch proxy server** — `aicarmine_mcp_batch_proxy(3 tools)` listed as a new MCP server category
2. **Wily server** — `aicarmine_wily(7 tools)` listed as a new MCP server category
3. **Updated counts** — 27 servers, 97 tools (was 25/87)
4. **Proper result handling** — Checks `$result.contextModification` instead of using raw return value directly
5. **Error output** — All errors written to `errorMessage` field

### MCP Router (Updated)

The router now includes:

1. **`code_complexity` scoring class** — Detects Wily-related keywords for code complexity analysis
2. **TieOrder entry** — Position 12 (between semantic_search and mcp_batch_proxy)
3. **Switch case** — Generates `wily_health`, `wily_report`, `wily_rank`, `wily_build`, `wily_index`, `wily_diff`, `wily_list_metrics` tools
4. **Batch proxy** — Detects keywords like `batch`, `parallel`, `multiple.*tool`, `concurrent.*mcp`
5. **Constraints output** — Adds batch proxy usage hints when active

## How to Use

### Automatic Hook Execution

Hooks are executed automatically by Cline at the appropriate lifecycle points. No manual invocation is needed.

### Manual Batch Reindex After Task Completion

After a task that modified source files, use this command:

```python
use_mcp_tool("aicarmine_mcp_batch_proxy", "mcp_batch_execute", {
    "operations": [
        {"server": "aicarmine_rag", "tool": "aicarmine_rag_reindex", "args": {"source": "git", "mode": "delta"}},
        {"server": "aicarmine_repo_symbol_index", "tool": "build", "args": {}},
        {"server": "aicarmine_index_bridge", "tool": "build", "args": {}},
        {"server": "aicarmine_wily", "tool": "wily_build", "args": {"mode": "delta"}}
    ],
    "compress": True
})
```

### Batch MCP Operations During Task

Replace multiple individual MCP calls with a single batch operation:

```python
use_mcp_tool("aicarmine_mcp_batch_proxy", "mcp_batch_execute", {
    "operations": [
        {"server": "aicarmine_repo_search_det", "tool": "repo_search_rg", "args": {"path": ".", "pattern": "def \\w+"}},
        {"server": "aicarmine_repo_symbol_index", "tool": "repo_search_ctags", "args": {"path": ".", "limit": 100}},
        {"server": "aicarmine_rag", "tool": "aicarmine_rag_context", "args": {"query": "authentication"}}
    ],
    "compress": True
})
```

## Design Principles

1. **Fail-open**: All hooks catch exceptions and return empty strings; hook failures never affect Cline operation
2. **Error visibility**: All errors are written to `errorMessage` field instead of silently ignored
3. **Observation-only**: PreToolObserver and PostToolObserver do not block tool calls; they only emit advisory context modifications
4. **Bounded state**: All observation arrays are capped at 32 entries; routing files older than 24h are purged
5. **Atomic writes**: State files use temp file + rename pattern to prevent partial writes
6. **SHA-256 correlation**: Tool calls are identified by canonical SHA-256 hashes for deterministic deduplication
7. **Conditional injection**: TaskResume only injects context when observations exist, preventing empty hint message spam
8. **Wily integration**: Code complexity metrics are available as MCP tools and integrated into the reindex workflow