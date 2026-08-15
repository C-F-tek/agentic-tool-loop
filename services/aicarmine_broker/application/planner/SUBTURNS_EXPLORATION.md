# Subturns Exploration - Planner Support Tools Mapping

**Created:** 2026-08-15  
**Purpose:** Document subturn tool implementations, validator logic, and behavioral patterns for planner agentic loop.  
**Status:** Complete - runtime_sqlite_memory_* FTS5 behavior fully documented.

---

## Overview

Subturn tools are internal support primitives that the planner can call during its decision cycle. They are designed to:
- Store/retrieve scratchpad data (planner_scratchpad_*)
- Persist operational/persistent memory (runtime_sqlite_memory_*)
- Enable prompt context continuation windows

The **validator** controls WHEN these tools can be called via `prompt_context_continuation_required` checks. The **memory_tools.py** module contains the actual implementation of these tools.

---

## Subturn Tool Inventory

### SUPPORT_SUBTURN_TOOLS (from validator.py, guards.py)
```python
SUPPORT_SUBTURN_TOOLS = frozenset({
    "planner_scratchpad_read",
    "planner_scratchpad_write",
    "runtime_sqlite_memory_search",
    "runtime_sqlite_memory_write",
})
```

Additional cleanup tool:
- `runtime_sqlite_memory_cleanup` - dry-run by default, requires apply=true for deletion

---

## 1. planner_scratchpad_write

**Implementation:** `services/aicarmine_broker/memory_tools.py` lines ~410-438  
**Dispatcher Registration:** `_simple(planner_scratchpad_write)`  
**Schema:** N/A (generic scratchpad) or `code_product_build_state.v1`  

### Storage Backends
| Kind | Storage | Description |
|------|---------|-------------|
| `code_product_build_state` | `planner_composer.sqlite` | SQLite table `planner_prompt_context_documents` |
| Other kinds | `planner_scratchpad.json` | Plain JSON file |

### Arguments
```json
{
  "kind": "note" | "answer_chunk" | "final_answer_chunk" | "code_product_build_state",
  "tag": "<optional>",
  "text": "<required>" | "content": "<alternative to text>",
  "target_file": "<for code_product_build_state>",
  "status": "<for code_product_build_state: collecting_source|ready_for_propose|blocked_incomplete>"
}
```

### Return Value
```json
{
  "ok": true,
  "tool": "planner_scratchpad_write",
  "artifact": "/path/to/planner_scratchpad.json",
  "count": 15,
  "written": {"id": "scratch-1234567890", "kind": "note", "tag": "", "ts": 1234567890.0}
}
```

### Error Cases
- `missing_text` - text/content field empty or missing
- `invalid_code_product_build_state_json` - JSON parse failure for code_product_build_state kind
- `code_product_build_state_not_object` - parsed value not a dict
- `invalid_code_product_build_state_schema` - schema mismatch (not code_product_build_state.v1)
- `missing_target_file` - no target_file specified for code_product_build_state
- `invalid_status` - status not in valid set

---

## 2. planner_scratchpad_read

**Implementation:** `services/aicarmine_broker/memory_tools.py` lines ~441-600  
**Dispatcher Registration:** `_simple(planner_scratchpad_read)`  

### Two Reading Modes

#### A. Prompt Context Window Mode (SQLite)
**Detection:** `result.get("mode") == "prompt_context_window"`  
**Storage:** `planner_composer.sqlite` → `planner_prompt_context_documents` table

Arguments:
- `document_id` - specific document to read
- `section` / `tag` - section-based query
- `query` - token-based search within text
- `offset` - window offset into full text
- `max_chars` - character budget (default 3000, min 500, max 100000)
- `limit` - number of results (default 3, min 1, max 100)

Return includes:
```json
{
  "ok": true,
  "tool": "planner_scratchpad_read",
  "mode": "prompt_context_window",
  "document_id": "prompt-context-abc123...",
  "store": "job_local_sqlite",
  "text": "<windowed text>",
  "window_start": 0,
  "window_end": 3000,
  "full_chars": 5000,
  "complete": false,
  "has_more_before": true,
  "has_more_after": true,
  "sha256": "<hash of full text>",
  "window_sha256": "<hash of windowed text>"
}
```

#### B. Generic Scratchpad Mode (JSON file)
**Detection:** `result.get("mode") != "prompt_context_window"`  
**Storage:** `planner_scratchpad.json`

Arguments:
- `kind` - filter by kind value
- `tag` - filter by tag value
- `limit` - number of results (default 200)

Return includes:
```json
{
  "ok": true,
  "tool": "planner_scratchpad_read",
  "count": 5,
  "items": [{"id": "...", "ts": ..., "kind": "...", "tag": "...", "text": "..."}]
}
```

---

## 3. runtime_sqlite_memory_write

**Implementation:** `services/aicarmine_broker/memory_tools.py` lines 669-759  
**Dispatcher Registration:** `_simple(runtime_sqlite_memory_write)`  

### Storage Schema (lines 627-639)
```sql
CREATE TABLE IF NOT EXISTS broker_memory_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    expires_at REAL,
    kind TEXT NOT NULL,
    tag TEXT,
    text TEXT NOT NULL,
    metadata_json TEXT,
    pinned INTEGER NOT NULL DEFAULT 0
)
```

### Arguments
```json
{
  "kind": "<default: 'planner_note'>",
  "tag": "<default: ''>",
  "text": "<required, max 24000 chars>",
  "ttl_days": <bounded int: default from PLANNER_MEMORY_RETENTION_DAYS, min 0, max 36500>,
  "metadata": {"key": "value"},
  "pinned": true | false
}
```

### Return Value
```json
{
  "ok": true,
  "tool": "runtime_sqlite_memory_write",
  "db": "/path/to/broker_memory_records.sqlite",
  "record_id": 1,
  "expires_at": 1234567890.0
}
```

### Error Cases
- `missing_text` - text/content field empty or missing
- `invalid_ttl_days` - non-integer ttl_days value
- `memory_metadata_json_serialization_failed` - metadata not JSON serializable
- SQLite errors → returns diagnostic with error_type and details

---

## 4. runtime_sqlite_memory_search

**Implementation:** `services/aicarmine_broker/memory_tools.py` lines 762-816  
**Dispatcher Registration:** `_simple(runtime_sqlite_memory_search)`  

### Storage Schema (lines 627-639)
```sql
CREATE TABLE IF NOT EXISTS broker_memory_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    expires_at REAL,
    kind TEXT NOT NULL,
    tag TEXT,
    text TEXT NOT NULL,
    metadata_json TEXT,
    pinned INTEGER NOT NULL DEFAULT 0
)
```

### FTS5 Virtual Table (lines 640-643)
```sql
CREATE VIRTUAL TABLE IF NOT EXISTS broker_memory_records_fts 
USING fts5(text, kind, tag, content='broker_memory_records', content_rowid='id')
```
- **Indexed columns**: `text`, `kind`, `tag` (stored as separate columns for filtering)
- **Content table**: `broker_memory_records` (FTS syncs from this table)
- **Row mapping**: `rowid` in FTS maps to `id` in main table

### Trigger-based Sync (lines 644-661)
**AFTER INSERT trigger**: Inserts new row into FTS with rowid, text, kind, tag.
**AFTER DELETE trigger**: Marks deleted row in FTS with `'delete'` operation.
**AFTER UPDATE trigger**: First deletes old values from FTS, then inserts updated values.

### Search Query Structure (lines 788-802)
```python
# When query is provided (FTS search):
sql = """
    SELECT m.* FROM broker_memory_records_fts f 
    JOIN broker_memory_records m ON m.id = f.rowid 
    WHERE f.broker_memory_records_fts MATCH ? AND <kind/tag filters> 
    ORDER BY m.updated_at DESC LIMIT ?
"""
 
# When query is empty (no FTS, only filters):
sql = """
    SELECT m.* FROM broker_memory_records m 
    WHERE <kind/tag filters> ORDER BY m.updated_at DESC LIMIT ?
"""
```

### Filtering Logic (lines 778-783)
**kind filter**: `m.kind = ?` - exact match on kind field
**tag filter**: `coalesce(m.tag, '') = ?` - treats None/empty tag as empty string for comparison

### Scope Separation Analysis
**No explicit "scope" column exists in broker_memory_records table.** The "scope" concept from the MCP tools (project vs codex_app) is NOT implemented at this level. Instead:
- **kind field** serves as the scope discriminator (e.g., `"controller_job_lesson"`, `"controller_loop_turn"`)
- **tag field** provides secondary categorization
- **db path** provides tertiary separation (different SQLite files for different contexts)

From `planner_memory_surface` function (lines 830-977):
```python
# Controller-injected memory queries use specific kind values:
runtime_sqlite_memory_search({
    "query": "",  # Empty query = no FTS search, only filters
    "kind": "controller_job_lesson",
    "tag": target_key,  # Specific tag for targeted lookup
    "limit": min(limit, 5)
})

runtime_sqlite_memory_search({
    "query": query,  # FTS search on extracted tokens from goal
    "kind": "controller_job_lesson",
    "limit": limit
})
```

### FTS MATCH Behavior
- **Query processing**: `_planner_memory_query` (lines 819-827) extracts word tokens (3+ chars) from goal string, deduplicates, joins with spaces
- **FTS MATCH** searches the `text` column only (as defined in FTS5 schema: `USING fts5(text, kind, tag, ...)`)
- **kind/tag filtering** happens via WHERE clause AFTER FTS MATCH, not within FTS itself
- **No rank/scoring** - results ordered by `updated_at DESC` (most recent first)

### Return Value Shaping (lines 814-816)
```python
for row in rows:
    row["text"] = str(row.get("text") or "")[:2000]  # Truncate to 2000 chars
return {"ok": True, "tool": "runtime_sqlite_memory_search", "db": str(db_path), "count": len(rows), "items": rows}
```

### Error Cases
- Missing/wrong db path → returns empty result if DB doesn't exist (line 771-772)
- SQLite errors → returns `{"ok": False, "error": "sqlite_memory_search_error"}` with diagnostics

### Arguments (exact from implementation lines 764-770)
```json
{
  "query": "<FTS5 search query string>",
  "kind": "<filter by exact kind match>",
  "tag": "<filter by exact tag match>",
  "db": "<optional explicit SQLite file path>",
  "limit": <bounded int: default 50, min 1, max 500>
}
```

### Return Value (exact from line 816)
```json
{
  "ok": true,
  "tool": "runtime_sqlite_memory_search",
  "db": "/path/to/broker_memory_records.sqlite",
  "count": 10,
  "items": [
    {"id": 1, "created_at": ..., "updated_at": ..., "kind": "...", "tag": "...", "text": "...[:2000]", ...}
  ]
}
```

Empty result:
```json
{
  "ok": true,
  "tool": "runtime_sqlite_memory_search",
  "db": "/path/to/memory.db",
  "count": 0,
  "items": []
}
```

---

## 5. runtime_sqlite_memory_cleanup

**Implementation:** `services/aicarmine_broker/memory_tools.py` lines 980-1119  
**Dispatcher Registration:** `_command(runtime_sqlite_memory_cleanup)`  

### Arguments
```json
{
  "apply": false | true,  // requires explicit confirmation
  "older_than_days": <int>,
  "expired_only": true | false (default),
  "kind": "<filter by kind>",
  "tag": "<filter by tag>",
  "pinned": true | false (default)
}
```

### Behavior
- Default is dry-run mode (reports what would be deleted)
- `apply=true` + user consent required for actual deletion
- Requires at least one filter condition (otherwise returns error "cleanup_requires_filter")
- Returns diagnostic with stage and error_type on failure

---

## Validator Logic Flow

### Location: `services/aicarmine_broker/application/planner/validator.py`

### Step 1: Check prompt_context_continuation_required
```python
prompt_context_continuation_required = decision.get("prompt_context_continuation_required")
prompt_context_continuation_matches = bool(
    prompt_context_continuation_required
    and _decision_matches_prompt_context_continuation(decision, prompt_context_continuation_required)
)
```

### Step 2: Enforce Required Scratchpad Read Continuation Contract
If `prompt_context_continuation_required=True`, the validator enforces that only `planner_scratchpad_read` with matching arguments is allowed.

### Step 3: Support Subturn Validation
When planner calls a support subturn tool:
```python
if tool in SUPPORT_SUBTURN_TOOLS and not (prompt_context_continuation_required and prompt_context_continuation_matches):
    violations.append("support_subturn_validation_failed")
    contract["support_subturn_rewrite_retry_count"] += 1
```

### Step 4: Retry Threshold Enforcement
After 2 retries:
```python
if contract["support_subturn_rewrite_retry_count"] >= 2:
    contract["final_rewrite_latch"] = "terminal_block_required"
```

After 3 retries + coverage satisfied:
```python
if support_retry_count >= 3 and coverage_satisfied_val and may_choose_final_val:
    contract["planner_may_choose_final"] = True
    return {"ok": True, "forced_finalization": True}
```

---

## Support Subturn Rewrite Retry Count Mechanism (`support_subturn_rewrite_retry_count`)

This mechanism tracks how many times a support subturn tool has been rejected in the **rewrite lane** — a state entered when final-quality gate rejects a final answer and sets `required_next_tool_call`.

### Trigger Conditions (validator.py lines 2678-2784)

The counter is incremented in two scenarios within the rewrite lane (`final_reject_count >= 1` AND `final_rewrite_latch != "inactive"`):

#### Scenario A: Empty Required Rewrite Tool (line 2706)
When final-quality gate rejects a final answer but does not set a concrete `required_next_tool_call`, and the planner attempts to use support subturn tools instead of producing a rewritten final.

```python
if not required_rewrite_tool:
    if tool in SUPPORT_SUBTURN_TOOLS and not (prompt_context_continuation_required and prompt_context_continuation_matches):
        violations.append("support_subturn_validation_failed")
        contract["support_subturn_rewrite_retry_count"] = int(
            contract.get("support_subturn_rewrite_retry_count") or 0
        ) + 1
        if contract["support_subturn_rewrite_retry_count"] >= 2:
            contract["final_rewrite_latch"] = "terminal_block_required"
            contract["planner_may_choose_block"] = True
            contract["planner_may_choose_final"] = False
            contract["required_next_tool_call"] = {}
```

**Behavior:** The final-quality gate rejected the final answer but did not set a concrete `required_next_tool_call`. The planner is attempting to use support subturn tools (scratchpad, runtime_sqlite_memory) instead of producing a rewritten final. After 2 such attempts, the validator forces terminal block state and clears the required tool call.

#### Scenario B: Tool Mismatch in Rewrite Lane (lines 2731-2779)
When final-quality gate sets a concrete `required_next_tool_call` (e.g., `repo_read`) but the planner calls a different tool.

```python
if tool != required_rewrite_tool:
    if tool in SUPPORT_SUBTURN_TOOLS:
        if not (prompt_context_continuation_required and prompt_context_continuation_matches):
            violations.append("support_subturn_validation_failed")
            contract["support_subturn_rewrite_retry_count"] = int(
                contract.get("support_subturn_rewrite_retry_count") or 0
            ) + 1
            if contract["support_subturn_rewrite_retry_count"] >= 2:
                # Terminal block forced
                contract["final_rewrite_latch"] = "terminal_block_required"
                ...
            else:
                # Continue rewrite with progress message
                contract["required_next_progress"] = (
                    f"Rewrite lane requires {required_rewrite_tool} as the next tool, "
                    "or a rewritten final."
                )
            
            # Forced finalization guard (lines 2753-2778):
            coverage_satisfied_val = _minimum_read_coverage_satisfied()
            may_choose_final_val = bool(contract.get("planner_may_choose_final")) or bool(
                final_contract.get("planner_may_choose_final")
            )
            support_retry_count = int(contract.get("support_subturn_rewrite_retry_count") or 0)
            if coverage_satisfied_val and may_choose_final_val and support_retry_count >= 3 and tool not in {"final", "done"}:
                contract["planner_may_choose_final"] = True
                contract["planner_may_choose_block"] = False
                final_contract["final_allowed"] = True
                ...
                return {
                    "ok": True,
                    "violations": [],
                    "evidence_contract": contract,
                    "forced_finalization": True,
                }
```

**Behavior:** The final-quality gate set a concrete `required_next_tool_call` (e.g., `repo_read`) but the planner is attempting to use support subturn tools instead of executing the required tool. After 2 rejections:
- Violation recorded with progress message pointing to required tool
- Counter incremented

After 3 rejections (forced finalization guard):
- If coverage is satisfied AND final is allowed → forces transition to action=final
- Returns `ok=True` with `forced_finalization=True` marker
- This prevents infinite retry loops where planner keeps trying support tools instead of finalizing

### Counter Evolution Across Turns

The counter persists in the evidence contract between turns via:
```python
contract["support_subturn_rewrite_retry_count"] = int(
    contract.get("support_subturn_rewrite_retry_count") or 0
) + 1
```

It is stored as part of the evidence contract which carries forward through the agentic loop. The counter only increments when:
1. We are in rewrite lane (`final_reject_count >= 1` AND `final_rewrite_latch != "inactive"`)
2. Tool is a support subturn tool (`planner_scratchpad_read`, `planner_scratchpad_write`, `runtime_sqlite_memory_search`, `runtime_sqlite_memory_write`)
3. NOT matching prompt context continuation (which would be allowed via `_decision_matches_prompt_context_continuation`)

### Threshold Behavior Table

| Retry Count | State | Effect |
|-------------|-------|--------|
| 0 | First rejection | Counter starts at 0, no action yet |
| 1 | Second attempt rejected | Counter becomes 1, progress message set: `"Rewrite lane requires {required_rewrite_tool} as the next tool, or a rewritten final."` |
| 2 | Third attempt rejected | Counter becomes 2, `final_rewrite_latch = "terminal_block_required"`, terminal block activated, `planner_may_choose_final = False` |
| 3+ | Fourth+ attempt with coverage satisfied | Forced finalization triggered if `_minimum_read_coverage_satisfied()` and `planner_may_choose_final` → returns `ok=True, forced_finalization=True` |

### State Persistence and Reset Conditions

The counter does not have an explicit reset mechanism within validator.py. It persists until:
- A valid final answer is produced (via `_clear_final_terminal_block_state` at line 170-273 which clears many contract fields but notably does NOT clear `support_subturn_rewrite_retry_count`)
- The contract state is replaced entirely by a new turn evaluation
- The agentic loop terminates or moves to a new job context

### Interaction with Final Rewrite Latch

`solution_subturn_rewrite_retry_count` tracks support subturn rejections specifically, while `final_rewrite_latch` tracks overall final-quality rejection pressure. They interact as follows:

| Condition | `final_rewrite_latch` State | `support_subturn_rewrite_retry_count` Effect |
|----------|----------------------------|---------------------------------------------|
| First final reject (no gap route) | `"rewrite_required"` → `"terminal_block_required"` | Counter starts at 0 |
| Second final reject | `"terminal_block_required"` if no gap route | Counter increments to 1 |
| Support subturn rejected (count >= 2) | Forced to `"terminal_block_required"` | Terminal block activated |
| Support subturn rejected (count >= 3) + coverage satisfied | N/A | Forces transition to action=final via forced_finalization marker |

### Key Distinction from Other Retry Mechanisms

Unlike `planner_final_quality_reject_count` which tracks overall final-quality rejections, `support_subturn_rewrite_retry_count` specifically tracks when the planner **misuses support tools as a substitute for proper evidence-based actions**. The thresholds are tighter:
- 2 retries → terminal block (vs. 2+ for general rewrite latch escalation)

---

## Decision Matches Prompt Context Continuation

**Location:** `services/aicarmine_broker/application/tool_surface/candidate_actions.py` lines 493-517  
**Used by:** Validator at lines ~1394-1400 via `_decision_matches_prompt_context_continuation(decision, continuation)`

### Logic Flow
```python
def decision_matches_prompt_context_continuation(
    decision: dict[str, Any],
    continuation: dict[str, Any],
) -> bool:
    # If either input is not a dict, default to True (allow through)
    if not isinstance(decision, dict) or not isinstance(continuation, dict):
        return True
    
    # If continuation doesn't require planner_scratchpad_read, allow any decision
    if continuation.get("tool") != "planner_scratchpad_read":
        return True
    
    # Decision MUST call planner_scratchpad_read
    if normalize_tool_name(safe_text(decision.get("tool"), limit=160)) != "planner_scratchpad_read":
        return False
    
    args = decision.get("arguments") or {}
    expected = continuation.get("arguments") or {}
    
    # kind must match (default expected_kind is "prompt_context_window")
    expected_kind = safe_text(expected.get("kind") or "prompt_context_window", limit=160)
    if safe_text(args.get("kind"), limit=160) != expected_kind:
        return False
    
    # document_id must match exactly
    if safe_text(args.get("document_id"), limit=300) != safe_text(expected.get("document_id"), limit=300):
        return False
    
    # offset must match exactly
    try:
        if int(args.get("offset") or 0) != int(expected.get("offset") or 0):
            return False
        # max_chars must match if specified in continuation
        if expected.get("max_chars") not in (None, ""):
            return int(args.get("max_chars") or 0) == int(expected.get("max_chars") or 0)
        return True
    except (TypeError, ValueError):
        return False
```

### Key Behaviors
1. **Strict matching:** Requires exact match on tool name, kind, document_id, offset, and optionally max_chars
2. **Lenient defaults:** If inputs are not dicts or continuation doesn't require scratchpad_read, returns True (allow through)
3. **Failure tolerance:** TypeError/ValueError during offset/max_chars comparison returns False (strict on errors)

### Impact on Validator Flow
When `prompt_context_continuation_required=True` but `_decision_matches_prompt_context_continuation(decision, continuation)=False`:
- The validator adds `"support_subturn_validation_failed"` to violations
- Increments `contract["support_subturn_rewrite_retry_count"]`
- After 2 retries: sets `final_rewrite_latch = "terminal_block_required"`
- After 3 retries + coverage satisfied: forces finalization

---

## Micro Batch Contract Generation

**Location:** `services/aicarmine_broker/application/evidence/builder.py` → `_micro_batch_contract_from_candidates()`  
**Schema:** `planner_micro_batch_contract.v1`  
**Constant:** `MICRO_BATCH_MAX_ACTIONS = 8` (line 33)

### Function Signature
```python
def _micro_batch_contract_from_candidates(
    candidates: list[dict[str, Any]],
    *,
    max_actions: int = MICRO_BATCH_MAX_ACTIONS,
) -> dict[str, Any]:
```

### How allowed_batch_actions Are Populated from Candidates

The function filters and deduplicates candidate actions to produce a batch-eligible set. Here is the detailed flow:

#### Step 1: Initialize Tracking Sets
```python
allowed_actions: list[dict[str, Any]] = []
seen_call_keys: set[str] = set()
seen_action_ids: set[str] = set()
```

#### Step 2: Iterate Through Candidates
For each action in `candidates`:
```python
for action in candidates if isinstance(candidates, list) else []:
    if not isinstance(action, dict):
        continue
```

#### Step 3: Filter by Tool Type (Read-Only Only)
```python
tool = str(action.get("tool") or "").strip()
if tool not in CACHEABLE_READ_TOOLS:
    continue
```
**CACHEABLE_READ_TOOLS** (from `planner_core/cache.py`): Contains read-only tools like `repo_read`, `repo_list_files`, `repo_tree`, `repo_search`, `repo_semantic_search`, etc. Write tools (`repo_write_file`, `repo_apply_patch`) and validation tools are excluded from batching.

#### Step 4: Deduplicate by Call Key
```python
args = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
call_key = canonical_batch_call_key(tool, args)
if call_key in seen_call_keys:
    continue
```
**canonical_batch_call_key** (from `tool_surface/batch_contract.py`): Creates a sanitized key from tool name + normalized arguments to detect duplicate calls with identical tool+arguments combinations.

#### Step 5: Deduplicate by Action ID
```python
action_id = str(action.get("action_id") or "").strip()
if not action_id or action_id in seen_action_ids:
    continue
```
Prevents duplicate entries that have the same `action_id`.

#### Step 6: Add to Allowed Actions
```python
seen_call_keys.add(call_key)
seen_action_ids.add(action_id)
allowed_actions.append({
    "action_id": action_id,
    "tool": tool,
    "arguments": args,
    "reason": action.get("reason"),
    "source": action.get("source"),
    "independent_read_only": True,
})
```

#### Step 7: Apply Limit and Determine Allow Flag
```python
limit = max(1, int(max_actions or MICRO_BATCH_MAX_ACTIONS))
visible_actions = allowed_actions[:limit]

# Allow micro_batch when:
# 1. At least 2 independent read-only candidates exist (original logic)
# 2. OR native tool mode is enabled (allows batch even with 1 action for flexibility)
_native_mode_enabled = len(visible_actions) >= 1
allowed_flag = len(visible_actions) >= 2 or _native_mode_enabled
```

### Return Value Structure
```json
{
  "schema": "planner_micro_batch_contract.v1",
  "allowed": true | false,
  "mode": "native_message_tool_calls_only",
  "max_batch_size": min(limit, len(visible_actions)) if visible_actions else 0,
  "allowed_tools": sorted({str(action.get("tool") or "") for action in visible_actions}),
  "allowed_batch_actions": [
    {
      "action_id": "...",
      "tool": "repo_read",
      "arguments": {"paths": [...]},
      "reason": "...",
      "source": "...",
      "independent_read_only": true
    }
  ],
  "candidate_action_count": len(candidates),
  "batchable_candidate_count": len(visible_actions),
  "guard": "Multiple native message.tool_calls are accepted only when every call matches one allowed_batch_actions entry by tool and sanitized arguments. Write/apply/command/validation/final actions remain single-step and separately validated.",
  "writes_allowed": false,
  "validation_tools_allowed": false,
  "reason": "at_least_two_independent_read_only_candidates" | "fewer_than_two_independent_read_only_candidates"
}
```

### Key Behaviors
1. **Read-only filtering**: Only tools in `CACHEABLE_READ_TOOLS` are batch-eligible (no writes, no validation)
2. **Deduplication**: Both by canonical call key (tool+args) and action_id
3. **Native mode override**: In native tool mode, even 1 visible action allows batching (flexibility for single-read scenarios)
4. **Limit enforcement**: Capped at `MICRO_BATCH_MAX_ACTIONS` (8) or custom `max_actions` parameter
5. **Guard clause**: Each batched call must match exactly one entry in `allowed_batch_actions` by tool and sanitized arguments

### Where Called
From builder.py line ~600+:
```python
contract["micro_batch_contract"] = _micro_batch_contract_from_candidates(
    contract["candidate_next_actions"]
)
```
The evidence builder calls this function when building the planner evidence contract, passing the candidate_next_actions list that was populated by `gate_candidate_actions`.

---

## Job Log Failure Patterns (from job-862ff003)

| Step | Tool Called | Violation | Cause |
|------|-------------|-----------|-------|
| 3 | planner_scratchpad_read | support_subturn_validation_failed | Called at first turn without prompt_context_continuation_required=True |
| 4, 8, 9 | Various | repeated_line:} | Degenerate stream output corruption |
| 7 | repo_read | repo_read_window_already_successful_without_progress | Repeated read of already-successful window |
| 10, 11 | final | final_not_allowed_by_evidence_contract | Insufficient evidence coverage for finalization |

---

## System Prompt Rules Added

**Location:** `services/aicarmine_broker/application/planner/system_prompt.py` → PLANNER_SYSTEM

### REGOLA SCRATCHPAD
- planner_scratchpad tools work ONLY when prompt_context_continuation_required=true AND prompt_context_continuation_matches=true
- At first turn, NEVER choose planner_scratchpad_write/read
- If validator rejects with support_subturn_validation_failed, you tried scratchpad without proper context continuation
- AT FIRST TURN: directly choose action=tool with tool=repo_read

### REGOLA CRITICA PER OUTPUT JSON
- Output MUST be valid parseable JSON via json.loads()
- NEVER produce output ending with repeated } without meaningful content (degenerate stream)
- If output is not valid JSON, the validator rejects it and you must try a different move
- NEVER produce empty final (final_empty_answer): if no concrete evidence, choose repo_read instead of final
- BEFORE choosing final, you MUST read at least 8 different files in the repository core area
- A valid final must contain: at least 5 paths read/listed, role of at least 3 concrete files, structured analysis

### REGOLA PER REPEAT READ WINDOW
- If validator rejects repo_read with repo_read_window_already_successful_without_progress, you're trying to re-read an already-successful window
- NEVER repeat the same repo_read call with identical arguments without progress
- If all available paths have been read, use existing evidence from verified_content_reads instead of calling repo_read
- Change strategy: read a different file or use search/RAG to discover new paths

### REGOLA PER CUDA REWRITE LOOP
- If planner_cuda_rewrite returns a tool decision that gets rejected by validator, DO NOT keep retrying the same tool
- After a cuda_rewrite rejection, change move: choose a different tool or proceed to action=final if evidence is sufficient
- Never repeat the same repo_read call after cuda_rewrite without varying arguments

### REGOLA PER EVIDENCE CONTRACT COMPLETO
To finalize a repository analysis, ALL these requirements must be satisfied:
1. Root/ranked orientation file reading (orientation files)
2. Baseline markdown/config readings (configuration files)
3. At least one meaningful non-infra/code area reading (significant code area)
4. 8/1 verified concrete readable reads (verified reads)
5. Semantic owner target coverage 7/2 for analysis/action-plan finalization
6. Target 20 remains advisory and constrained by discovered candidates
If even one requirement is missing, DO NOT choose final: continue with repo_read or search.

---

## File Mapping Reference

| Concept | Primary Implementation | Secondary References |
|---------|----------------------|---------------------|
| Subturn tool implementations | `memory_tools.py` | - |
| Validator logic | `validator.py` | `guards.py`, `loop.py` |
| Prompt context continuation | `context_windows.py` | `pack_builder.py`, `system_prompt.py` |
| Micro batch contract | `builder.py`, `candidate_actions.py` | - |
| Dispatcher registration | `dispatcher.py` | `turn_surface_policy.py` |
| Memory routing policy | `agent_memory_routing_policy.py` | - |
| Controller memory integration | `memory.py` | - |

---

## Context Windows Functions (context_windows.py)

### prompt_window_consumed_offsets(history, history_tool_result, code_product_build_state_kind) → dict[str, int]
Tracks consumed offsets per document_id from successful planner_scratchpad_read calls in history.
Returns `{document_id: window_end}` for each consumed window.

### prompt_window_tracking_metadata_errors(history, history_tool_result, code_product_build_state_kind) → list[dict]
Validates that all planner_scratchpad_read items have required tracking metadata keys.
Returns errors with step, document_id, item_index, and missing keys.

### prompt_context_continue_action(window, max_chars, reason, code_product_build_state_kind) → dict | None
Generates continuation action when `has_more_after=True`.
Returns tool call structure with next_unconsumed_offset.

### planner_scratchpad_next_window_action_from_history(args, history, history_tool_result, code_product_build_state_kind) → dict
Finds the latest unconsumed window for a given document_id and returns next offset.
Used to continue reading from where left off in SQLite windows.

### required_working_set_continuation_action(required_working_set, history, window_chars, history_tool_result, code_product_build_state_kind) → dict | None
Checks if required_working_set has unconsumed windows (repo_reads, code_product unified_diff, build_state).
Generates continuation action for real required content.

### evidence_contract_continuation_action(evidence_contract, history, window_chars, history_tool_result, code_product_build_state_kind) → dict | None
Checks if full_evidence_contract_window has unconsumed content.
Generates continuation action before final decision.

### prompt_context_continuation_from_payload(payload, code_product_build_state_kind) → dict
Extracts required_next_tool_call from evidence_contract and builds planner_scratchpad_read arguments.
Two sources:
1. `required_next_tool_call.tool == "planner_scratchpad_read"` → use its arguments directly
2. First item in `candidate_next_actions` with tool == "planner_scratchpad_read" → use its arguments

### forbidden_repeated_prompt_window_calls(history, continuation_action, history_tool_result, required_next_tool_call_from_action, code_product_build_state_kind) → list[dict]
Detects repeated calls to already-consumed prompt windows.
Returns list of already_consumed entries for the same document_id.

---

## Exploration Status Summary

| Item | Status | Key Findings |
|------|--------|--------------|
| planner_scratchpad_read | ✅ Complete | Two modes: SQLite window mode and JSON generic mode |
| decision_matches_prompt_context_continuation | ✅ Complete | Strict matching on tool name, kind, document_id, offset, max_chars |
| runtime_sqlite_memory_* tools | ✅ Complete | FTS5 search via text column only; scope separation via kind field + db path |
| Validator retry count mechanism | ✅ Complete | support_subturn_rewrite_retry_count increments in rewrite lane; 2 retries → terminal block, 3+ retries + coverage → forced finalization |
| Micro batch contract generation | ✅ Complete | Filters read-only tools, deduplicates by call key and action_id, allows batching when ≥2 candidates or native mode enabled |
