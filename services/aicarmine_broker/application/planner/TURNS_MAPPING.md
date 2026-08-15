# Planner Turns Mapping Guide

**Created:** 2026-08-15  
**Purpose:** Explain turn logic flow and where to find specific behaviors when encountering difficulties during planner searches. This is a reference map for navigating the agentic loop turn system.

---

## Overview

The **planner turn** is the core decision cycle of the agentic loop. Each turn:
1. Builds evidence contract from goal + history
2. Computes tool surface (which tools are available)
3. Sends request to Ollama/Planner model
4. Processes response into a decision (action=tool, action=final, action=block)
5. Applies validator checks before executing the decision

### Main Entry Point
- **File:** `services/aicarmine_broker/application/planner/turn.py`
- **Function:** `planner_decision(job_id, state, step, history, deps, config)` → dict[str, Any]
- **Called by:** Loop dispatcher at each agentic loop iteration

---

## Turn Logic Flow

### Step 1: Input Validation
```python
# turn.py lines 478-486
if _input_error_goal(goal):
    return {
        "action": "block",
        "reason": "missing_user_request_no_fallback",
        "final_answer": "Public tool call is missing the natural-language user request..."
    }
```
**Where to find:** `services/aicarmine_broker/application/shared/payload_metadata.py` → `_input_error_goal()` function

### Step 2: Build Tool Manifest & Known Names
```python
# turn.py lines 487-502
all_tool_manifest = [...]  # From TOOLS_SCHEMA filtered by internal_tools_list
known_tool_names = {...}   # Set of canonical tool names
```
**Where to find:** 
- `services/aicarmine_broker/tool_contract.py` → `TOOLS_SCHEMA` global
- `services/aicarmine_broker/application/planner/lane_catalog.py` → `control_lane_event_metadata()`

### Step 3: Evidence Contract Construction
```python
# turn.py lines 504-537
last_step = history[-1] if history else {}
last_tool_result = last_step.get("tool_result")
evidence_contract = planner_evidence_contract(goal, history)
planner_memory = planner_memory_surface({...})
intrinsic_context = build_planner_intrinsic_context(...)
evidence_contract = _apply_step_budget_guidance_to_contract(evidence_contract, state)
```
**Where to find:**
- `services/aicarmine_broker/application/evidence/builder.py` → `planner_evidence_contract()` function
- `services/aicarmine_broker/memory_tools.py` → `planner_memory_surface()` function (controller-injected queries)
- `services/aicarmine_broker/planner_intrinsic_context.py` → `build_planner_intrinsic_context()` function
- `turn.py` lines 83-239 → `_apply_step_budget_guidance_to_contract()` function

### Step 4: Tool Surface Computation
```python
# turn.py lines 541-576
base_tool_names = _tool_surface_names_for_turn(goal, evidence_contract, intrinsic_context)
native_tool_names = _post_final_reject_turn_tool_names(evidence_contract, base_tool_names, known_tool_names)
final_rewrite_latch = str(evidence_contract.get("final_rewrite_latch") or "inactive").strip().lower()
```
**Where to find:**
- `services/aicarmine_broker/application/tool_surface/manifest_builder.py` → `_tool_surface_names_for_turn()` function
- `turn.py` lines 337-396 → `_post_final_reject_turn_tool_names()` function (filters tools based on final_rewrite_latch state)

### Step 5: Native Tool Schema & User Payload Building
```python
# turn.py lines 578-618
schema = _native_tools_schema_for_planner(TOOLS_SCHEMA, tool_names)
user_payload, budget = _build_planner_user_payload(...)
prompt_context_continuation_required = _prompt_context_continuation_from_payload(user_payload)
refined_native_tool_names = _tool_surface_names_for_turn(..., prompt_context_continuation_required=prompt_context_continuation_required)
```
**Where to find:**
- `services/aicarmine_broker/application/prompt/pack_builder.py` → `_build_planner_user_payload()` function
- `services/aicarmine_broker/application/tool_surface/candidate_actions.py` → `_prompt_context_continuation_from_payload()` function

### Step 6: Runtime Roots Mismatch Check
```python
# turn.py lines 620-683
runtime_roots_mismatch = not (normalized_cwd == normalized_lab or ...)
if runtime_roots_mismatch_blocks_final:
    return {"action": "block", "reason": "runtime_roots_mismatch", ...}
```
**Where to find:** `services/aicarmine_broker/application/planner/turn.py` lines 620-683

### Step 7: Hard Required Errors Check (Generation Headroom)
```python
# turn.py lines 685-773
hard_required_errors = [err for err in required_errors if err.get("error") in {...}]
if hard_required_errors:
    return {"action": "block", "reason": "planner_prompt_no_generation_headroom", ...}
```
**Where to find:** `services/aicarmine_broker/application/prompt/budget.py` → prompt budget computation functions

### Step 8: System Prompt & History Messages Building
```python
# turn.py lines 774-842
planner_system_prompt = _planner_system_for_current_mode()
history_messages, history_messages_report = _planner_history_messages_for_ollama(...)
```
**Where to find:**
- `services/aicarmine_broker/application/planner/system_prompt.py` → `PLANNER_SYSTEM` constant and `_planner_system_for_current_mode()` function
- `services/aicarmine_broker/application/prompt/history_messages.py` → `_planner_history_messages_for_ollama()` function

### Step 9: Planner Payload Construction
```python
# turn.py lines 865-888
planner_payload = {
    "model": PLANNER_MODEL,
    "stream": False,
    "messages": [...],
    "options": {...},
    "tools": native_tools_schema if AGENTIC_PLANNER_NATIVE_TOOLS else None,
}
```
**Where to find:** `turn.py` lines 865-888

### Step 10: Ollama Request & Response Processing
```python
# turn.py lines 975-1260
response = post_json_stream_to_file(PLANNER_URL, planner_payload, ...)
# Process response based on type:
# - native_calls → _native_tool_calls_decision()
# - plain text terminal action → normalize_planner_decision()
# - degenerate output → _degenerate_output_block_decision()
# - timeout → block with non-json reason
# - done token → final or block depending on code product candidate
# - otherwise → normalize_planner_decision(raw_text)
```
**Where to find:**
- `services/aicarmine_broker/application/planner/decision_normalizer.py` → `normalize_planner_decision()` function
- `turn.py` lines 1001-1063 → `_native_tool_calls_decision()` handling
- `turn.py` lines 1173-1208 → degenerate output and timeout handling

---

## Decision Processing Functions

### _native_tool_calls_decision (lines ~1001-1015)
When Ollama returns native tool calls, this function extracts them into a decision structure.
**Location:** Imported from deps["native_tool_calls_decision"]

### _degenerate_output_block_decision (lines ~314-334)
Handles degenerate planner output (repeated characters, non-parseable text).
Returns action=block with PLANNER_DEGENERATE_OUTPUT_NON_JSON reason.
**Location:** `turn.py` lines 314-334

### _post_final_reject_turn_tool_names (lines ~337-396)
Filters available tools based on final_rewrite_latch state:
- `"terminal_block_required"` → returns empty list (no tools allowed)
- `"rewrite_required"` / `"required_gap_only"` → returns only required_next_tool_call tool
- `"inactive"` → returns base tool names unchanged
**Location:** `turn.py` lines 337-396

### _apply_step_budget_guidance_to_contract (lines ~83-239)
Applies step budget guidance to evidence contract:
- `"prepare_terminal_decision"` mode → adds operational_notes with step_budget_hint
- `"force_terminal_decision"` mode → clears candidate actions, sets terminal_decision_required=True
- Also handles planner_scratchpad_read continuation and required_next_tool_call deferral
**Location:** `turn.py` lines 83-239

### _planner_role_system_suffix (lines ~66-80)
Adds specialist role suffix to system prompt when planner_role_override is set.
**Location:** `turn.py` lines 66-80

---

## Turn Tool Surface Policy

The turn computes a tool surface policy that determines which tools are available:

| State | final_rewrite_latch | Available Tools | Behavior |
|-------|---------------------|-----------------|----------|
| Normal | `"inactive"` | All base tools | Standard planning |
| Rewrite Required | `"rewrite_required"` | Only required_next_tool_call tool | Must follow required path |
| Gap Only | `"required_gap_only"` | Only gap-filling tools | Must fill evidence gaps |
| Terminal Block | `"terminal_block_required"` | None (empty) | Cannot call any tool |

**Where to find:** `services/aicarmine_broker/application/planner/turn.py` lines 546-576, `_post_final_reject_turn_tool_names()` function

---

## Evidence Contract Fields Used in Turn

| Field | Type | Purpose | Where Set |
|-------|------|---------|-----------|
| `final_rewrite_latch` | str | Controls tool surface filtering | validator.py support_subturn validation |
| `planner_may_choose_final` | bool | Whether final action is allowed | validator.py coverage checks |
| `planner_may_choose_block` | bool | Whether block action is allowed | validator.py terminal conditions |
| `required_next_tool_call` | dict | Specific tool the planner must call next | evidence builder / validator |
| `required_next_progress` | str | Instruction for what to do next | validator.py progress guidance |
| `minimum_read_coverage` | dict | Evidence coverage requirements | evidence builder |
| `coverage_satisfied` | bool | Whether minimum coverage is met | evidence builder |
| `finalization_contract` | dict | Final/block decision constraints | validator.py final quality gate |
| `turn_tool_surface_policy` | dict | Tool surface filtering reason | turn.py computation |

**Where to find:**
- `services/aicarmine_broker/application/evidence/builder.py` → `planner_evidence_contract()` function
- `services/aicarmine_broker/application/planner/validator.py` → contract mutation functions
- `services/aicarmine_broker/application/planner/state.py` → state management functions

---

## Common Turn Difficulties & Where to Find Solutions

### Problem: Planner keeps calling same tool without progress
**Check:** `services/aicarmine_broker/application/planner/validator.py` → repeated_tool_call_count logic (lines ~3304-3329)
**Solution:** Look for `repeated_same_tool_arguments_without_progress` violation and forced finalization guard

### Problem: Planner cannot produce final answer
**Check:** `services/aicarmine_broker/application/evidence/builder.py` → `_minimum_read_coverage_satisfied()` function
**Solution:** Check if coverage_satisfied is True, verify minimum_read_coverage requirements are met

### Problem: Prompt context continuation blocking tool calls
**Check:** `services/aicarmine_broker/application/tool_surface/candidate_actions.py` → `_decision_matches_prompt_context_continuation()` function (lines 493-517)
**Solution:** Verify prompt_context_continuation_required matches actual planner_scratchpad_read arguments

### Problem: Step budget exhausted before max_steps_reached
**Check:** `turn.py` lines 83-239 → `_apply_step_budget_guidance_to_contract()` function
**Solution:** Look for terminal_decision_required=True in finalization_contract, allowed_actions=[final, block]

### Problem: Runtime roots mismatch blocking final
**Check:** `turn.py` lines 620-683 → runtime_roots_mismatch computation
**Solution:** Verify AICARMINE_LAB_REPO matches OPEN_TERMINAL_CWD and AICARMINE_OPEN_TERMINAL_WORKDIR

### Problem: No generation headroom for planner output
**Check:** `services/aicarmine_broker/application/prompt/budget.py` → prompt budget computation
**Solution:** Check AGENTIC_PLANNER_NUM_CTX vs ollama_prompt_eval_count, verify native_history_reserve_chars

---

## Turn Event Metadata

Each turn emits event metadata via control_lane_event_metadata:
```python
planner_lane_metadata = control_lane_event_metadata(
    planner_lane_id,  # "planner.primary" or "planner.cuda_rewrite"
    step=step,
    attempt=1,
    trigger=trigger,  # "planner_turn" or "planner_role_override"
)
```
**Where to find:** `services/aicarmine_broker/application/planner/lane_catalog.py` → `control_lane_event_metadata()` function

---

## File Reference Map

| Concept | Primary Implementation | Secondary References |
|---------|----------------------|---------------------|
| Turn entry point | `turn.py::planner_decision()` | `loop.py`, dispatcher |
| Evidence contract | `builder.py::planner_evidence_contract()` | `validator.py`, `state.py` |
| Tool surface computation | `manifest_builder.py::_tool_surface_names_for_turn()` | `candidate_actions.py`, `lane_catalog.py` |
| Validator enforcement | `validator.py::validate_planner_decision()` | `guards.py`, `loop.py` |
| Prompt context continuation | `candidate_actions.py::_decision_matches_prompt_context_continuation()` | `context_windows.py`, `pack_builder.py` |
| Step budget guidance | `turn.py::_apply_step_budget_guidance_to_contract()` | `budget.py`, `state.py` |
| Decision normalization | `decision_normalizer.py::normalize_planner_decision()` | `system_prompt.py` |
| Intrinsic context | `planner_intrinsic_context.py::build_planner_intrinsic_context()` | `rag_mcp_server.py`, memory_tools.py |

---

## Quick Reference: Turn Flow Diagram

```
planner_decision()
├── [1] Input validation → block if missing user request
├── [2] Build tool manifest & known names
├── [3] Evidence contract construction
│   ├── planner_evidence_contract(goal, history)
│   ├── planner_memory_surface(controller queries)
│   └── _apply_step_budget_guidance_to_contract(state)
├── [4] Tool surface computation
│   ├── _tool_surface_names_for_turn()
│   └── _post_final_reject_turn_tool_names()
├── [5] Native tool schema & payload building
│   ├── _native_tools_schema_for_planner()
│   ├── _build_planner_user_payload()
│   └── _prompt_context_continuation_from_payload()
├── [6] Runtime roots mismatch check → block if mismatch + terminal surface
├── [7] Hard required errors (generation headroom) → block if insufficient
├── [8] System prompt & history messages building
│   ├── _planner_system_for_current_mode()
│   └── _planner_history_messages_for_ollama()
├── [9] Planner payload construction (model, stream, options, tools)
├── [10] Ollama request & response processing
│   ├── native_calls → _native_tool_calls_decision()
│   ├── plain text terminal → normalize_planner_decision()
│   ├── degenerate output → _degenerate_output_block_decision()
│   ├── timeout → block with non-json reason
│   ├── done token → final or block
│   └── otherwise → normalize_planner_decision(raw_text)
└── Return decision dict
```

---

## Related Documentation Files

| File | Purpose |
|------|---------|
| `SUBTURNS_EXPLORATION.md` | Subturn tool implementations, validator logic, retry count mechanism |
| `TURNS_MAPPING.md` (this file) | Turn logic flow, decision processing, where to find specific behaviors |
| `validator/README.md` | Validator enforcement rules and violation catalog |
| `system_prompt.py` | PLANNER_SYSTEM constant with system prompt rules |
| `context_windows.py` | Prompt context window functions for scratchpad continuation |