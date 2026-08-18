# Planner Module - AICarmine Broker

## Overview

The `application/planner/` package implements the main controlled planner loop for the 11434 Ollama instance. It normalizes planner decisions, compacts tool results for model context, builds intrinsic pre-turn context, builds history ledgers, records Ollama turns, expands successful tool artifacts, validates finalization and calls final-quality and replan guidance lanes.

## Architecture

```
application/planner/
├── loop.py              # Main planner loop controller
├── state.py             # Planner state management
├── system_prompt.py     # System prompt templates
├── turn.py              # Turn management (turns/subturns)
├── validation_rejections.py  # Validation rejection handling
├── VALIDATION_REJECTIONS.md   # Contract documentation
└── SUBTURNS_EXPLORATION.md    # Subturns exploration docs
```

## Core Components

### Planner Loop (`loop.py`)

Main controlled planner loop. It normalizes planner decisions, compacts tool results for model context, builds intrinsic pre-turn context, builds history ledgers, records Ollama turns, expands successful tool artifacts, validates finalization, calls final-quality and replan guidance lanes, handles repair, dispatches tools and writes terminal job state.

**Planner-adjacent model lanes:**
- Preplanner RAG query-plan wiring calls `application/controller/rag_preseed.py` before the first turn
- Final-quality judge wiring calls `application/evidence/final_quality.py` request builders for repo and semantic-audit finals
- Planner replan specialist wiring handles selected validator rejections and repairs malformed specialist JSON

**Code-product vs apply intent separation:**
- Diff/refactoring/code-product goals require a successful `repo_propose_code_edit` proposal
- Apply/edit/fix/write goals still require `repo_apply_patch`

### Turn Management (`turn.py`)

Manages turns and subturns in the planner loop. Tracks turn boundaries, subturn sequencing and the transition between exploration and exploitation phases.

- Reads: current turn state, history ledger
- Writes: turn records, subturn markers
- Risk: must maintain strict turn ordering for replayability

### State Management (`state.py`)

Manages planner state transitions including queued, running, exploring, exploiting and terminal states. Tracks the current turn number, remaining budget and accumulated evidence.

- Reads: job state, history ledger
- Writes: state updates, event records
- Risk: state must remain consistent across crashes/restarts

### System Prompt (`system_prompt.py`)

Builds the system prompt for the 11434 planner instance. Includes tool registry, evidence contract rules, code-product vs apply separation policy and finalization gates.

- Reads: config, tool schema, evidence contract
- Writes: none (prompt generation only)
- Risk: changes affect all subsequent planning behavior

### Validation Rejections (`validation_rejections.py`)

Handles validation rejections from the validator contract. Routes rejected actions back through repair lanes or replan specialists based on rejection type and severity.

- Reads: validator rejection reason, current turn state
- Writes: repair requests, replan specialist calls
- Risk: must not mask code-product contract failures in GPU0/11435 repair

## Planner Contract Rules

1. **No semantic audit routing to GPU0**: Do not route semantic `repo_propose_code_edit` contract failures to GPU0/11435 repair lanes.

2. **Prompt compaction internal**: Prompt compaction must remain internal to 11434 planner calls and must not degrade OpenWebUI `tool_context_for_30b`.

3. **Code-product diff completeness**: Code-product results must include the full diff/operations inline, not only previews or summaries.

4. **Working-set chars bounded**: The required working set must be bounded to prevent context window overflow while maintaining evidence completeness.

## Verification

- Check that real job events show planner step, decision, tool result, turn memory and terminal status in expected order
- Verify code-product jobs show `repo_read -> repo_propose_code_edit -> final` flow with no `repo_apply_patch` unless goal asked to apply
- Confirm prompt events expose requested/capped/effective `num_ctx`, exact prompt chars, compact mode and required working-set chars