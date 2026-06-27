# Implementation Plan — Phase Manager Extraction

## Overview

Complete the refactoring of `loop.py` (CC=233, 2613 lines) and `turn.py` (CC=180, 1289 lines) by extracting inline helper functions into phase manager classes that already exist but have stub methods. The validator.py refactoring (CC=434→50) is complete and serves as the template pattern.

Phase manager classes are created at:
- `services/aicarmine_broker/application/planner/loop_phases.py` — PreseedPhaseManager, LoopPhaseManager, DecisionPhaseManager, FinalizationPhaseManager
- `services/aicarmine_broker/application/planner/turn_phases.py` — PayloadBuilderPhase, EvidenceContractPhase, ToolSurfacePhase, RuntimeRootsPhase, DecisionExecutionPhase

PreseedPhaseManager.execute_preseed() is already populated with full inline logic. All other methods are stubs awaiting extraction.

## Types

### Existing Phase Manager Classes (no changes needed)

```python
# loop_phases.py
class PreseedPhaseManager:
    def __init__(self, job_id, state, history, deps, config, root, loop_state) -> None
    def execute_preseed(self, preseed_plan, preseed_index, original_args, public_tool_name, dispatch_tool, sanitize_tool_args, write_json, job_id) -> tuple[dict, dict]  # ✅ POPULATED
    def execute_dynamic_initial_orientation(self, root_result, preseed_index, preplanner_query_plan) -> int  # ⏳ needs logic

class LoopPhaseManager:
    def __init__(self, job_id, state, history, deps, config, root, loop_state, max_steps) -> None
    def build_step_budget_guidance(self, semantic_step) -> dict  # ⏳ needs logic
    def execute_turn(self, step, goal_text) -> dict  # ⏳ needs logic

class DecisionPhaseManager:
    def __init__(self, job_id, state, deps, config) -> None
    def evaluate_decision(self, decision, history, contract) -> dict  # ⏳ needs logic

class FinalizationPhaseManager:
    def __init__(self, job_id, state, deps) -> None
    def finalize(self, status, message, extra) -> dict  # ⏳ stub only

# turn_phases.py
class PayloadBuilderPhase:
    def __init__(self, job_id, state, step, deps, config) -> None
    def build_native_payload(self, tool_names, history, evidence_contract, intrinsic_context, last_tool_result) -> tuple  # ✅ POPULATED

class EvidenceContractPhase:
    def __init__(self, deps, config) -> None
    def build_contract(self, goal, history, intrinsic_context) -> dict  # ⏳ needs logic

class ToolSurfacePhase:
    def __init__(self, deps) -> None
    def determine_turn_tool_names(self, goal, evidence_contract, intrinsic_context, prompt_context_continuation_required, known_tool_names) -> list  # ⏳ needs logic

class RuntimeRootsPhase:
    def __init__(self) -> None
    def validate_runtime_roots(self, runtime_roots, base_tool_names, native_tool_names) -> dict  # ⏳ POPULATED

class DecisionExecutionPhase:
    def __init__(self, deps) -> None
    def execute_decision(self, raw_decision, history) -> dict  # ⏳ stub only
```

## Files

### Files to Modify (not create)

1. **`services/aicarmine_broker/application/planner/loop_phases.py`**
   - Populate `LoopPhaseManager.execute_turn()` with ~500 lines of inline logic from loop.py
   - Populate `DecisionPhaseManager.evaluate_decision()` with guard evaluation logic (~800 lines across multiple guards)
   - Populate `PreseedPhaseManager.execute_dynamic_initial_orientation()` with ~200 lines
   - Add `LoopPhaseManager` methods for: coverage_satisfied, missing_owner_paths, support_subturn_decision, mark_support_subturn, force_terminal_decision_active, final_quality_guided_route_available, build_runtime_debug_packet, persist_turn_memory, append_cached_tool_result, get_semantic_step, enrich_validation_with_replan_specialist, match_micro_batch_action

2. **`services/aicarmine_broker/application/planner/turn_phases.py`**
   - Populate `EvidenceContractPhase.build_contract()` with evidence contract construction logic (~150 lines)
   - Populate `ToolSurfacePhase.determine_turn_tool_names()` with tool surface determination logic (~100 lines)
   - Populate `DecisionExecutionPhase.execute_decision()` with decision normalization logic

3. **`services/aicarmine_broker/application/planner/loop.py`**
   - Replace inline helper calls (`execute_controller_preseed()`, `execute_dynamic_initial_orientation()`) with phase manager method calls
   - Replace inline guard evaluator calls with `DecisionPhaseManager` methods
   - Replace inline finalization calls with `FinalizationPhaseManager.finalize()`
   - Remove the inline helper functions after extracting to phase managers

4. **`services/aicarmine_broker/application/planner/turn.py`**
   - Replace inline payload building with `PayloadBuilderPhase` method calls
   - Replace inline evidence contract construction with `EvidenceContractPhase` method calls
   - Replace inline tool surface determination with `ToolSurfacePhase` method calls
   - Remove inline helpers after extraction

## Functions

### loop_phases.py — Methods to Populate

```python
# PreseedPhaseManager (lines 66-76)
def execute_dynamic_initial_orientation(self, root_result, preseed_index, preplanner_query_plan) -> int:
    # Extract from loop.py inline helper ~line 950
    # Logic: doc_preseed_plan, area_list_plans, execute_controller_preseed for each
    # Returns updated preseed_index

# LoopPhaseManager (lines 106-124)
def build_step_budget_guidance(self, semantic_step) -> dict:
    # Extract from loop.py inline logic ~line 1050
    # Logic: check step budget, build guidance dict

def execute_turn(self, step, goal_text) -> dict:
    # Extract from loop.py main loop body ~line 1080-1300
    # Logic: load state, build contract snapshot, build memory snapshot, build working memory

def coverage_satisfied(self, contract) -> bool:
    # Extract guard helper

def missing_owner_paths(self, contract) -> list:
    # Extract guard helper

def support_subturn_decision(self, decision) -> bool:
    # Extract guard helper

def mark_support_subturn(self, row, semantic_step) -> None:
    # Extract guard helper

def force_terminal_decision_active(self, semantic_step, max_steps) -> bool:
    # Extract guard helper

def final_quality_guided_route_available(self, validation) -> bool:
    # Extract guard helper

def build_runtime_debug_packet(self, step_number, phase, planner_decision, validation, extra=None) -> dict:
    # Extract guard helper

def persist_turn_memory(self, row) -> None:
    # Extract guard helper

def append_cached_tool_result(self, step, decision, result_data) -> None:
    # Extract guard helper

def get_semantic_step(self, physical_step) -> int:
    # Extract guard helper

def enrich_validation_with_replan_specialist(self, step, decision, validation) -> dict:
    # Extract replan specialist logic

def match_micro_batch_action(self, micro_batch_contract, tool, internal_args) -> dict:
    # Extract micro batch matching logic

# DecisionPhaseManager (lines 142-149)
def evaluate_decision(self, decision, history, contract) -> dict:
    # Extract validate_planner_decision_against_evidence inline logic

# FinalizationPhaseManager (lines 166-175)
def finalize(self, status, message, extra) -> dict:
    # Already delegates to deps["finalize_agentic_job"] — needs no changes
```

### turn_phases.py — Methods to Populate

```python
# EvidenceContractPhase.build_contract()
def build_contract(self, goal, history, intrinsic_context) -> dict:
    # Extract from turn.py inline evidence contract construction
    # Logic: planner_evidence_contract call, apply_step_budget_guidance

# ToolSurfacePhase.determine_turn_tool_names()
def determine_turn_tool_names(self, goal, evidence_contract, intrinsic_context, prompt_context_continuation_required, known_tool_names) -> list:
    # Extract from turn.py inline tool surface determination
    # Logic: _tool_surface_names_for_turn, _post_final_reject_turn_tool_names

# DecisionExecutionPhase.execute_decision()
def execute_decision(self, raw_decision, history) -> dict:
    # Extract from turn.py inline decision normalization
    # Logic: _normalize_terminal_planner_decision
```

## Dependencies

No new external dependencies. All refactoring uses existing imports and injected deps from the calling functions.

## Testing

### Verification steps (⏳ Pending)

1. Run ruff on all modified files after each batch
2. Re-run `ast_top_functions` to confirm complexity reduction
3. Verify loop.py and turn.py still import and instantiate correctly
4. Check that phase manager methods receive correct arguments from call sites

## Implementation Order

### Batch 1: LoopPhaseManager methods (highest impact)

1. Add `coverage_satisfied`, `missing_owner_paths`, `support_subturn_decision`, `mark_support_subturn`, `force_terminal_decision_active`, `final_quality_guided_route_available`, `build_runtime_debug_packet`, `persist_turn_memory`, `append_cached_tool_result`, `get_semantic_step`, `enrich_validation_with_replan_specialist`, `match_micro_batch_action` to LoopPhaseManager class
2. Extract inline logic from loop.py for each method
3. Update loop.py call sites to use phase manager methods instead of inline helpers

### Batch 2: DecisionPhaseManager + FinalizationPhaseManager

4. Populate `DecisionPhaseManager.evaluate_decision()` with guard evaluation logic
5. Populate `FinalizationPhaseManager.finalize()` (already delegates — verify)
6. Update loop.py to use `DecisionPhaseManager` and `FinalizationPhaseManager` methods

### Batch 3: turn_phases.py population

7. Populate `EvidenceContractPhase.build_contract()` with evidence contract logic
8. Populate `ToolSurfacePhase.determine_turn_tool_names()` with tool surface logic
9. Populate `DecisionExecutionPhase.execute_decision()` with decision normalization
10. Update turn.py call sites

### Batch 4: Cleanup and verification

11. Remove inline helper functions from loop.py that are now in phase managers
12. Remove inline helper functions from turn.py that are now in phase managers
13. Run ruff on all files
14. Re-run ast_top_functions to confirm complexity reduction