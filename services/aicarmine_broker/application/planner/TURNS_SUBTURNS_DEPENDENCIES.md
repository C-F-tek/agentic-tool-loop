# Planner Turns ↔ Subturns Dependencies & Behavioral Flows

**Created:** 2026-08-15  
**Purpose:** Document in detail how planner turns depend on subturn tools, the behavioral flows between them, state transitions, and the complete dependency graph connecting turn decisions to subturn tool execution. This is the operational reference for understanding when and why turns invoke subturns.

---

## Overview: The Turn-Subturn Relationship

The **planner turn** (`turn.py::planner_decision`) produces a decision dict with `action` field values like `"tool"`, `"final"`, or `"block"`. When `action == "tool"` and the chosen tool is a **subturn tool**, the validator (`validator.py::validate_planner_decision`) enforces constraints that determine whether the subturn call is allowed, rejected, or triggers state escalation.

### Key Distinction
| Concept | Role | Lifecycle |
|---------|------|-----------|
| **Turn** | Decision cycle - evaluates goal + history → produces planner decision | Per-iteration, ephemeral |
| **Subturn** | Support tool execution - stores/retrieves scratchpad data, persists memory | Cross-turn, persistent state |
| **Validator** | Gate between turn decision and subturn execution - checks constraints | Per-iteration, bridges turn→subturn |

---

## Turn → Subturn Dependency Chain

### Step 1: Turn Produces Decision with Tool Selection
```python
# turn.py lines 975-1260
decision = normalize_planner_decision(raw_text, goal, step, state)
decision["action"] = "tool"
decision["tool"] = "planner_scratchpad_read"
decision["arguments"] = {"kind": "prompt_context_window", "document_id": "..."}
```

The turn's Ollama response processing determines which tool the planner wants to call. This decision carries forward into validation.

**Where:** `services/aicarmine_broker/application/planner/turn.py` → `normalize_planner_decision()`, `_native_tool_calls_decision()`

### Step 2: Validator Receives Decision + Evidence Contract
```python
# validator.py lines 1380-1600+
validate_planner_decision(
    decision,      # From turn.py output
    evidence_contract,  # Built by builder.py::planner_evidence_contract()
    history,       # Previous iteration history
    deps,          # Dependencies (path_exists_repo_relative, etc.)
)
```

The validator receives the decision and checks it against the current evidence contract state. This is where turn-subturn dependencies are enforced.

**Where:** `services/aicarmine_broker/application/planner/validator.py` → `validate_planner_decision()` function

### Step 3: Validator Checks prompt_context_continuation_required
```python
# validator.py lines 1389-1405
prompt_context_continuation_required = decision.get("prompt_context_continuation_required")
prompt_context_continuation_matches = bool(
    prompt_context_continuation_required
    and _decision_matches_prompt_context_continuation(decision, prompt_context_continuation_required)
)
if prompt_context_continuation_required:
    contract = _enforce_required_scratchpad_read_continuation_contract(contract, prompt_context_continuation_required)
```

**Dependency:** If the evidence contract has `prompt_context_continuation_required=True`, only `planner_scratchpad_read` with matching arguments is allowed. This creates a hard dependency between turn state and subturn tool selection.

**Where:** 
- `services/aicarmine_broker/application/planner/validator.py` lines 1389-1405
- `services/aicarmine_broker/application/tool_surface/candidate_actions.py` → `_decision_matches_prompt_context_continuation()` function (lines 493-517)

### Step 4: Validator Checks Rewrite Lane State
```python
# validator.py lines 2678-2784
final_reject_count = int(contract.get("planner_final_quality_reject_count") or 0)
final_rewrite_latch = _coerce_final_rewrite_latch(contract.get("final_rewrite_latch"))
rewrite_active = final_rewrite_latch != "inactive" and final_reject_count >= 1
if rewrite_active:
    # Enforces specific subturn tool constraints based on rewrite lane state
```

**Dependency:** When `final_rewrite_latch` is active (not `"inactive"`), the validator enforces different subturn rules depending on whether we're in `"rewrite_required"`, `"required_gap_only"`, or `"terminal_block_required"` state.

**Where:** `services/aicarmine_broker/application/planner/validator.py` lines 2678-2784

### Step 5: Validator Increments Retry Count on Subturn Rejection
```python
# validator.py lines 2704-2779
if not required_rewrite_tool:
    if tool in SUPPORT_SUBTURN_TOOLS and not (prompt_context_continuation_required and prompt_context_continuation_matches):
        violations.append("support_subturn_validation_failed")
        contract["support_subturn_rewrite_retry_count"] = int(contract.get("support_subturn_rewrite_retry_count") or 0) + 1
        if contract["support_subturn_rewrite_retry_count"] >= 2:
            contract["final_rewrite_latch"] = "terminal_block_required"
            contract["planner_may_choose_block"] = True
            contract["planner_may_choose_final"] = False
```

**Dependency:** Each rejected subturn call increments `support_subturn_rewrite_retry_count`. This counter persists across turns and triggers state escalation when thresholds are crossed.

**Where:** `services/aicarmine_broker/application/planner/validator.py` lines 2704-2779

---

## Subturn Tool Categories & Turn Dependencies

### SUPPORT_SUBTURN_TOOLS (from validator/guards)
```python
SUPPORT_SUBTURN_TOOLS = frozenset({
    "planner_scratchpad_read",
    "planner_scratchpad_write",
    "runtime_sqlite_memory_search",
    "runtime_sqlite_memory_write",
})
```

### 1. planner_scratchpad_read ↔ Turn Dependency

**Turn Context:** Called when the evidence contract has unconsumed prompt context windows or when `prompt_context_continuation_required=True`.

**Subturn Behavior:**
- **SQLite Window Mode** (`mode="prompt_context_window"`): Reads from `planner_composer.sqlite` → `planner_prompt_context_documents` table with windowing (offset, max_chars)
- **JSON Generic Mode**: Reads from `planner_scratchpad.json` file with kind/tag filtering

**Turn Dependency Flow:**
```
Turn decision → validator checks prompt_context_continuation_required
→ If True + matches → allows planner_scratchpad_read
→ If True + doesn't match → rejects with support_subturn_validation_failed
→ Increments retry count on rejection
→ ≥2 rejections → terminal_block_required state
```

**State Transitions Triggered:**
| Condition | State Change | Effect on Next Turn |
|-----------|--------------|---------------------|
| First subturn rejection in rewrite lane | `support_subturn_rewrite_retry_count = 1` | Progress message set, continue rewrite |
| Second subturn rejection | `final_rewrite_latch = "terminal_block_required"` | No tools allowed, may_choose_final=False |
| Third+ rejection + coverage satisfied | Forced finalization triggered | Transition to action=final |

**Where:** 
- `services/aicarmine_broker/memory_tools.py` → `planner_scratchpad_read()` implementation (lines ~441-600)
- `services/aicarmine_broker/application/planner/validator.py` lines 2704-2779

### 2. planner_scratchpad_write ↔ Turn Dependency

**Turn Context:** Called when the planner needs to store scratchpad data for later retrieval or compose answer chunks.

**Subturn Behavior:**
- Writes to `planner_scratchpad.json` (generic kinds) or `planner_composer.sqlite` (code_product_build_state kind)
- Validates kind, text/content, target_file, status fields

**Turn Dependency Flow:**
```
Turn decision → validator checks if in rewrite lane
→ If in rewrite lane + no required_next_tool_call → rejects subturn write
→ Increments retry count on rejection
→ ≥2 rejections → terminal_block_required state
```

**State Transitions Triggered:** Same as planner_scratchpad_read - increments retry counter and can trigger terminal block.

**Where:**
- `services/aicarmine_broker/memory_tools.py` → `planner_scratchpad_write()` implementation (lines ~410-438)
- `services/aicarmine_broker/application/planner/validator.py` lines 2875-2886 (answer_chunk validation)

### 3. runtime_sqlite_memory_search ↔ Turn Dependency

**Turn Context:** Called when the controller needs to inject memory queries or the planner needs to search operational/persistent memory for context.

**Subturn Behavior:**
- FTS5 search on `broker_memory_records` table via `broker_memory_records_fts` virtual table
- Filters by kind, tag, query text
- Returns items with text truncated to 2000 chars

**Turn Dependency Flow:**
```
Turn decision → validator checks if in rewrite lane
→ If in rewrite lane + tool != required_rewrite_tool → rejects
→ Increments retry count on rejection
→ ≥3 rejections + coverage satisfied → forced finalization
```

**State Transitions Triggered:** Same as other subturns - increments retry counter and can trigger forced finalization.

**Where:**
- `services/aicarmine_broker/memory_tools.py` → `runtime_sqlite_memory_search()` implementation (lines 762-816)
- `services/aicarmine_broker/application/planner/validator.py` lines 2730-2779

### 4. runtime_sqlite_memory_write ↔ Turn Dependency

**Turn Context:** Called when the planner or controller needs to persist operational memory records for later retrieval.

**Subturn Behavior:**
- Writes to `broker_memory_records` SQLite table with FTS5 sync triggers
- Validates text/content, ttl_days, metadata fields
- Returns record_id and expires_at timestamp

**Turn Dependency Flow:** Same as runtime_sqlite_memory_search - subject to rewrite lane constraints.

**Where:**
- `services/aicarmine_broker/memory_tools.py` → `runtime_sqlite_memory_write()` implementation (lines 669-759)
- `services/aicarmine_broker/application/planner/validator.py` lines 2867-2868 (missing_text validation)

---

## State Transition Graph: Turn ↔ Subturn Interaction

### Rewrite Lane States

```
[inactive] ←──┐
    │         │
    ▼         │
[rewrite_required] ──→ retry_count=1, required_next_tool_call set
    │             │
    ▼             │
[required_gap_only] ──→ retry_count=2, gap route active
    │             │
    ▼             │
[terminal_block_required] ──→ retry_count≥2, no tools allowed
    │             │
    └─────────────┘ (reset by valid final answer via _clear_final_terminal_block_state)
```

**Where:** `services/aicarmine_broker/application/planner/validator.py` lines 104-123 → `_next_final_rewrite_latch()` function

### Support Subturn Retry Count Evolution

| Retry Count | State | Effect | Next Turn Behavior |
|-------------|-------|--------|-------------------|
| 0 | First rejection in rewrite lane | Counter starts at 0 | Continue with progress message |
| 1 | Second attempt rejected | Counter becomes 1 | Progress: "Rewrite lane requires {required_rewrite_tool}" |
| 2 | Third attempt rejected | Counter becomes 2, `final_rewrite_latch = "terminal_block_required"` | No tools allowed, may_choose_final=False |
| 3+ | Fourth+ attempt + coverage satisfied | Forced finalization triggered | Returns ok=True with forced_finalization=True marker |

**Where:** `services/aicarmine_broker/application/planner/validator.py` lines 2704-2779

---

## Turn Decision Processing → Subturn Validation Flow

### validate_planner_decision Function Structure

```python
def validate_planner_decision(decision, evidence_contract, history, deps):
    # [1] Extract prompt_context_continuation_required from decision
    prompt_context_continuation_required = decision.get("prompt_context_continuation_required")
    
    # [2] Check if continuation matches actual tool arguments
    prompt_context_continuation_matches = bool(
        prompt_context_continuation_required
        and _decision_matches_prompt_context_continuation(decision, prompt_context_continuation_required)
    )
    
    # [3] Enforce scratchpad read continuation contract if required
    if prompt_context_continuation_required:
        contract = _enforce_required_scratchpad_read_continuation_contract(contract, ...)
    
    # [4] Check rewrite lane state (final_rewrite_latch + final_reject_count)
    final_reject_count = int(contract.get("planner_final_quality_reject_count") or 0)
    final_rewrite_latch = _coerce_final_rewrite_latch(contract.get("final_rewrite_latch"))
    rewrite_active = final_rewrite_latch != "inactive" and final_reject_count >= 1
    
    # [5] If rewrite active, enforce subturn constraints
    if rewrite_active:
        required_tool_call = contract.get("required_next_tool_call", {})
        required_rewrite_tool = str(required_tool_call.get("tool") or "").strip()
        
        # [5a] No required tool call set → reject all non-continuation subturns
        if not required_rewrite_tool:
            if tool in SUPPORT_SUBTURN_TOOLS and not continuation_matches:
                violations.append("support_subturn_validation_failed")
                retry_count += 1
                if retry_count >= 2:
                    terminal_block_required = True
        
        # [5b] Tool doesn't match required → reject unless continuation matches
        if tool != required_rewrite_tool:
            if tool in SUPPORT_SUBTURN_TOOLS and not continuation_matches:
                violations.append("support_subturn_validation_failed")
                retry_count += 1
                if retry_count >= 3 and coverage_satisfied:
                    forced_finalization = True
    
    # [6] Check individual tool argument validation (repo_read, repo_search, etc.)
    if tool == "planner_scratchpad_write" and kind == CODE_PRODUCT_BUILD_STATE_KIND:
        # Validate code_product_build_state payload structure
    
    # [7] Return ok=True/False with violations list and updated contract
    return {"ok": False, "violations": [...], "evidence_contract": contract}
```

**Where:** `services/aicarmine_broker/application/planner/validator.py` lines 1380-2900+

---

## Evidence Contract Fields That Bridge Turn ↔ Subturn

| Field | Type | Source | Effect on Subturns |
|-------|------|--------|-------------------|
| `prompt_context_continuation_required` | dict | evidence builder / candidate_actions | Controls whether only matching planner_scratchpad_read is allowed |
| `final_rewrite_latch` | str | validator `_next_final_rewrite_latch()` | Determines rewrite lane state and subturn constraints |
| `planner_final_quality_reject_count` | int | validator final quality gate | Tracks overall rejection pressure |
| `support_subturn_rewrite_retry_count` | int | validator support subturn validation | Tracks subturn-specific rejections, triggers escalation |
| `required_next_tool_call` | dict | validator / evidence builder | Specific tool the planner must call next in rewrite lane |
| `required_next_missing_evidences` | list | validator missing evidence detection | Paths that must be read before terminal action |
| `coverage_satisfied` | bool | evidence builder / validator coverage checks | Determines whether forced finalization can trigger |
| `planner_may_choose_final` | bool | validator final quality gate | Whether final action is allowed |
| `planner_may_choose_block` | bool | validator terminal conditions | Whether block action is allowed |

**Where:**
- `services/aicarmine_broker/application/evidence/builder.py` → `planner_evidence_contract()` function
- `services/aicarmine_broker/application/planner/validator.py` → contract mutation functions

---

## Behavioral Flow: When Turns Invoke Subturns

### Scenario 1: Normal Turn (No Rewrite Lane)
```
Turn decision → tool=planner_scratchpad_read
→ Validator checks prompt_context_continuation_required=False
→ No rewrite lane constraints apply
→ Subturn call allowed if arguments valid
→ History updated with subturn result
→ Next turn proceeds normally
```

**Key:** In normal mode, subturn tools are allowed freely as long as their arguments pass basic validation (missing text, missing selector, etc.).

### Scenario 2: Rewrite Lane - First Rejection
```
Final quality gate rejects final answer → planner_final_quality_reject_count=1
→ final_rewrite_latch transitions to "rewrite_required"
→ required_next_tool_call set by validator (e.g., repo_read)
→ Turn decision → tool=planner_scratchpad_read (not matching required tool)
→ Validator rejects with support_subturn_validation_failed
→ support_subturn_rewrite_retry_count=1
→ Progress message: "Rewrite lane requires {required_rewrite_tool}"
→ Next turn continues rewrite with progress guidance
```

**Key:** First rejection in rewrite lane allows the planner to try again with a progress message pointing to the required tool.

### Scenario 3: Rewrite Lane - Terminal Block
```
support_subturn_rewrite_retry_count reaches 2
→ final_rewrite_latch forced to "terminal_block_required"
→ planner_may_choose_final=False, planner_may_choose_block=True
→ No tools allowed (empty tool surface)
→ Turn decision → any subturn call rejected
→ Contract cleared of required_next_tool_call
→ Progress message: "Rewrite lane support-subturn loop detected..."
```

**Key:** Terminal block state prevents further subturn calls and clears the required tool call, forcing the planner to produce a rewritten terminal final or explicit block.

### Scenario 4: Forced Finalization
```
support_subturn_rewrite_retry_count reaches 3+
→ _minimum_read_coverage_satisfied()=True
→ planner_may_choose_final=True
→ Validator returns ok=True with forced_finalization=True marker
→ Planner allowed to choose action=final from existing evidence
→ No additional tool calls permitted
```

**Key:** After 3 rejections with coverage satisfied, the validator forces transition to action=final, preventing infinite retry loops where planner keeps trying support tools instead of finalizing.

---

## Turn → Subturn Dependency Matrix

| Turn State | Subturn Tool Allowed? | Constraints | Retry Threshold | Escalation |
|------------|----------------------|-------------|-----------------|------------|
| Normal (inactive) | Yes | Valid arguments only | N/A | None |
| rewrite_required | Conditional | Must match required_next_tool_call or continuation | 2 retries | terminal_block_required |
| required_gap_only | Conditional | Must match gap-filling tool | 2 retries | terminal_block_required |
| terminal_block_required | No | No subturns allowed | - | Final answer clears latch |
| forced_finalization | No | Transition to action=final | 3+ retries + coverage | ok=True, forced_finalization=True |

---

## File Reference Map: Turn ↔ Subturn Dependencies

| Concept | Primary Implementation | Secondary References |
|---------|----------------------|---------------------|
| Turn decision production | `turn.py::planner_decision()` | `decision_normalizer.py`, Ollama response processing |
| Validator enforcement | `validator.py::validate_planner_decision()` | `guards.py`, loop dispatcher |
| Prompt context continuation check | `candidate_actions.py::_decision_matches_prompt_context_continuation()` | `context_windows.py`, pack_builder.py |
| Rewrite latch state machine | `validator.py::_next_final_rewrite_latch()`, `_escalate_final_rewrite_retry_count()` | `state.py` |
| Subturn tool implementations | `memory_tools.py` → planner_scratchpad_*, runtime_sqlite_memory_* | terminal_dispatcher.py registration |
| Evidence contract construction | `builder.py::planner_evidence_contract()` | validator mutation functions |
| Retry count tracking | `validator.py` support_subturn_rewrite_retry_count logic | turn decision processing |
| Forced finalization guard | `validator.py` lines 2753-2779 | coverage_satisfied checks |

---

## Quick Reference: Turn ↔ Subturn Interaction Flow Diagram

```
planner_decision() [turn.py]
│
├── Ollama response → decision dict (action, tool, arguments)
│
└── validate_planner_decision(decision, evidence_contract, history, deps) [validator.py]
    │
    ├── [1] Check prompt_context_continuation_required
    │   └── _decision_matches_prompt_context_continuation(decision, continuation)
    │       └── Strict match on: tool name, kind, document_id, offset, max_chars
    │
    ├── [2] Check rewrite lane state
    │   ├── final_reject_count ≥ 1 AND final_rewrite_latch != "inactive"
    │   └── required_next_tool_call from validator / evidence builder
    │
    ├── [3] If rewrite active + subturn tool called
    │   ├── No required_rewrite_tool → reject + retry_count++
    │   ├── Tool != required_rewrite_tool → reject + retry_count++
    │   └── retry_count ≥ 2 → terminal_block_required
    │       └── retry_count ≥ 3 + coverage_satisfied → forced_finalization
    │
    ├── [4] Individual tool argument validation
    │   ├── planner_scratchpad_write → missing text, answer_chunk validation
    │   ├── runtime_sqlite_memory_* → missing query/tag/kind/text
    │   └── All tools → missing required arguments (query, path, etc.)
    │
    └── Return ok=True/False with violations and updated contract
        └── ok=False → turn rejected, history updated with violation info
        └── ok=True → subturn allowed, executes in loop dispatcher
```

---

## Related Documentation Files

| File | Purpose |
|------|---------|
| `SUBTURNS_EXPLORATION.md` | Subturn tool implementations, FTS5 search behavior, scope separation |
| `TURNS_MAPPING.md` | Turn logic flow, decision processing, where to find specific behaviors |
| `TURNS_SUBTURNS_DEPENDENCIES.md` (this file) | Detailed turn-subturn dependency graph, state transitions, behavioral flows |
| `validator/README.md` | Validator enforcement rules and violation catalog |
| `memory_tools.py` | Actual subturn tool implementation code |