# Implementation Plan: Fix Planner Native Tool Mode Rejection Loop

## Overview
Job `job-efc5b945` ("analizza la repo") is stuck in an infinite rejection loop at step 6 due to the planner model (`mio-qwen-code-6:latest` on Ollama 11434) producing JSON validator feedback instead of valid native tool calls when native mode is enabled. The root cause is that the planner emits protocol-shaped JSON text (e.g., `planner_controller_guard_history.v1`, `planner_tool_history_evidence.v1`) that passes JSON detection but fails native tool call validation, causing `planner_native_mode_non_json_output` rejection repeated 4+ times.

## Problem Analysis

### Symptom
- Job status: `running_agentic`, step 6
- Rejection count: 7 total, with 4+ identical `planner_native_mode_non_json_output` rejections
- Step 1: `repo_read` rejected for `repo_read_path_not_from_prior_file_evidence`
- Steps 3-6: Repeated `planner_native_mode_non_json_output` rejection

### Evidence
1. **Planner output analysis**: The raw_planner_text shows valid JSON objects like:
   ```json
   {
     "schema": "planner_controller_guard_history.v1",
     "kind": "validator_feedback",
     "source": "validator",
     ...
   }
   ```
   This is validator feedback text, not a tool call decision.

2. **Native tool mode enabled**: `planner_native_tools_enabled: true`, `native_tool_calls_seen: 0`
   - The model has no `message.tool_calls` in its response
   - It produces JSON text instead of native tool calls

3. **candidate_next_actions empty**: `candidate_next_actions_preview: []`
   - No candidate actions are populated in the evidence contract
   - This means the planner has no valid tools to choose from

4. **Model capability confirmed**: User verified `mio-qwen-code-6:latest` supports tool calls

### Confirmed Cause
The planner model is emitting JSON validator feedback text instead of native tool calls. When `AGENTIC_PLANNER_NATIVE_TOOLS=true`, the system expects either:
- Native `message.tool_calls` format
- Valid terminal JSON (action=final/block)

The model's JSON output passes JSON detection but fails validation because it's not a valid planner decision (no action field, no tool field). The turn.py code at lines 1147-1161 detects this as `planner_native_mode_non_json_output`.

## Root Cause Chain
1. `AGENTIC_PLANNER_NATIVE_TOOLS=true` enables native tool mode
2. Planner emits JSON validator feedback instead of tool calls
3. JSON passes detection but fails validation (not a valid decision)
4. Validator rejects with `planner_native_mode_non_json_output`
5. Controller guard counts repeated rejections
6. After 3+ repeats, `invalid_decision_repeat_count` triggers terminal block

## Types

No type changes required. The issue is in runtime behavior, not type definitions.

## Files

### Files to Read (Analysis Only)
- `services/aicarmine_broker/config/models.py` - Check `native_tools`, `require_native_tools`, `native_max_parallel_readonly` config fields
- `services/aicarmine_broker/planner.py` - Check how native tools config is passed to planner
- `services/aicarmine_broker/application/prompt/tool_contract.py` - Check TOOLS_SCHEMA and native tool shape examples
- `services/aicarmine_broker/application/prompt/pack_builder.py` - Check how candidate_next_actions are populated in prompt
- `services/aicarmine_broker/application/tool_surface/candidate_actions.py` - Check why candidate_next_actions is empty

### Configuration Investigation
- Environment variables: `AGENTIC_PLANNER_NATIVE_TOOLS`, `PLANNER_NATIVE_TOOLS`, `REQUIRE_NATIVE_TOOLS`
- Job configuration at creation time vs current runtime config

## Functions

### Functions to Investigate
1. `_try_native_tool_calls_fallback()` in `services/aicarmine_broker/application/planner/decision_normalizer.py`
   - How it extracts tool calls from raw text
   - Why it fails to find valid tool calls

2. `_parse_strict_json_object()` in `services/aicarmine_broker/application/planner/turn.py`
   - How it validates terminal JSON decisions
   - Why validator feedback JSON fails validation

3. `_looks_like_malformed_native_protocol()` in `services/aicarmine_broker/application/planner/turn.py`
   - How it detects malformed protocol text
   - Whether validator feedback JSON triggers this

4. `normalize_planner_decision()` in `services/aicarmine_broker/application/planner/decision_normalizer.py`
   - How it handles embedded JSON decisions
   - Whether validator feedback could be normalized as a decision

5. `candidate_action_tool()` and `dedupe_candidate_actions()` in `services/aicarmine_broker/application/tool_surface/candidate_actions.py`
   - Why candidate_next_actions is empty
   - How actions are populated for the planner prompt

## Classes

### Classes to Investigate
1. `ToolSurfacePolicy` in `services/aicarmine_broker/application/tool_surface/turn_surface_policy.py`
   - How tool surface is constructed per turn
   - Whether required_next_tool_call is properly set

2. Evidence contract builder in `services/aicarmine_broker/application/evidence/builder.py`
   - How evidence_contract is built
   - Why candidate_next_actions might be empty

## Dependencies

### Dependency Investigation
- Ollama model configuration: Check if `mio-qwen-code-6:latest` has tools schema loaded
- Tools schema injection: Verify TOOLS_SCHEMA is correctly passed to Ollama API
- Native tool mode configuration: Verify AGENTIC_PLANNER_NATIVE_TOOLS is enabled

## Testing

### Validation Strategy
1. Verify Ollama model supports tool calls: `curl http://127.0.0.1:11434/api/tags`
2. Check model tools capability: `curl http://127.0.0.1:11434/api/show -d '{"model": "mio-qwen-code-6:latest"}'`
3. Test native tool call emission with a simple prompt
4. Verify candidate_next_actions population in job context

### Test Cases
1. Send a tool-requiring prompt to Ollama and verify tool_calls response
2. Check if the issue is model-specific or configuration-specific
3. Verify disabling native mode allows fallback to JSON tool calls

## Implementation Order

1. **Step 1**: Investigate configuration - Read config/models.py, planner.py, check environment variables for native_tools settings
2. **Step 2**: Investigate Ollama model capability - Verify mio-qwen-code-6:latest has tools schema loaded and supports tool calls
3. **Step 3**: Investigate candidate_next_actions - Check why it's empty in the evidence contract
4. **Step 4**: Determine fix approach - Either:
   a. Disable native mode for this job/model combination
   b. Fix tools schema injection
   c. Add fallback handling for validator feedback JSON
5. **Step 5**: Implement fix - Apply configuration change or code fix
6. **Step 6**: Test with a new job - Verify the fix resolves the rejection loop
7. **Step 7**: Verify job completion - Confirm job can complete successfully