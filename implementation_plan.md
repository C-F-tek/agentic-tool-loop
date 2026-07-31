# Implementation Plan

## Overview
Extract the remaining ~102 CC from `validate_planner_decision_against_evidence` in validator.py into dedicated pipeline stages (`StageQualityGate` and `StageDuplicateRecovery`), wire them into the existing `ValidatorPipeline`, and remove ~1400 lines of nested function definitions. This completes Phase 5 of the validator complexity reduction effort, building on the 211 CC already extracted into 8 new modules across Phases 1-5.

## Types
- `PipelineState` (already exists): dataclass with `goal`, `decision`, `history`, `config`, `deps`, `action`, `tool`, `args`, `contract`, `violations`, `result`, `coverage_required`, `coverage_satisfied`, `missing_owner_paths`
- `QualityGateResult`: new TypedDict with `reject_count`, `final_rewrite_latch`, `required_next_tool_call`, `required_next_progress`, `finalization_contract`
- `DuplicateRecoveryResult`: new TypedDict with `forbidden_paths`, `recovery_count`, `required_next_progress`

## Files

### New Files to Create
1. `services/aicarmine_broker/application/planner/validator_quality_gate.py` (replace scaffold)
   - Purpose: Final quality gate evaluation, rewrite latch state transitions
   - Contains: `StageQualityGate` class with full `_apply_final_quality_route` logic (~72 CC)
   - Extracts: reject count tracking, required-next tool call generation, deterministic proof validation, candidate-next-actions population, finalization contract updates

2. `services/aicarmine_broker/application/planner/validator_duplicate_recovery.py`
   - Purpose: Duplicate repo read recovery contract logic
   - Contains: `StageDuplicateRecovery` class
   - Extracts: `_apply_duplicate_repo_read_path_recovery_contract` (~30 CC)
   - Handles: forbidden path tracking, recovery count thresholds, evidence consumption routes

### Existing Files to Modify
1. `services/aicarmine_broker/application/planner/validator.py`
   - Replace inline nested helper functions with calls to pipeline stages
   - Wire `ValidatorPipeline.run()` as the main entry point
   - Remove ~1400 lines of nested function definitions
   - Keep backward-compat aliases for existing callers

2. `services/aicarmine_broker/application/planner/validator_pipeline.py`
   - Import `StageQualityGate` (replace scaffold) and `StageDuplicateRecovery`
   - Add stages to `ValidatorPipeline.__init__`
   - Wire stages into `ValidatorPipeline.run()` with early-return logic

## Functions

### New Functions to Create
1. `StageQualityGate.run(self, state: PipelineState) -> PipelineState`
   - File: validator_quality_gate.py
   - Purpose: Full `_apply_final_quality_route` logic extraction

2. `StageDuplicateRecovery.run(self, state: PipelineState) -> PipelineState`
   - File: validator_duplicate_recovery.py
   - Purpose: Full `_apply_duplicate_repo_read_path_recovery_contract` logic extraction

### Modified Functions
1. `ValidatorPipeline.__init__()` in validator_pipeline.py
   - Add `self.quality_gate = StageQualityGate()`
   - Add `self.duplicate_recovery = StageDuplicateRecovery()`

2. `ValidatorPipeline.run()` in validator_pipeline.py
   - Add stage 9 execution: quality gate
   - Add stage 10 execution: duplicate recovery
   - Add early-return logic after each stage

### Removed Functions (from validator.py)
1. `_apply_final_quality_route` (~72 CC) — moved to StageQualityGate
2. `_apply_duplicate_repo_read_path_recovery_contract` (~30 CC) — moved to StageDuplicateRecovery
3. Supporting nested helpers: `_required_gap_paths_from_quality`, `_coalesce_required_next_missing_paths`, `_verified_required_next_missing_paths`, `_successful_read_paths_for_final_route`, `_stale_required_next_repo_read_paths`, `_path_allowed_by_missing_evidence`, `_required_next_tool_from_missing_evidences`, `_coalesce_required_next_tool_tool`, `_coerce_final_rewrite_latch`

## Dependencies
- No new external package dependencies required
- Internal imports only between planner submodules
- Existing deps/config injection pattern preserved through PipelineState

## Testing
- Unit tests for StageQualityGate in `tests/test_validator_quality_gate.py`
- Unit tests for StageDuplicateRecovery in `tests/test_validator_duplicate_recovery.py`
- Integration test: verify `ValidatorPipeline.run()` produces identical results to original `validate_planner_decision_against_evidence`
- Regression test: verify existing callers of `validate_planner_decision_against_evidence` produce identical results
- Complexity verification: run wily report to confirm validator.py CC < 200

## Implementation Order
1. Replace scaffold in `validator_quality_gate.py` with full `_apply_final_quality_route` extraction (~72 CC)
2. Create `validator_duplicate_recovery.py` with `StageDuplicateRecovery` (~30 CC)
3. Update `validator_pipeline.py` to import and wire both new stages
4. Refactor `validator.py` to delegate to `ValidatorPipeline.run()` and remove ~1400 lines of nested functions
5. Run wily report to verify validator.py CC < 200
6. Run existing test suite to verify regression compliance