# Implementation Plan

## Overview

Add structured error codes to critical planner decision paths so that every rejection, repair attempt, and validation failure returns a consistent dict with `error_code`, `summary`, and diagnostic fields instead of plain strings or ad-hoc dicts. This enables reliable monitoring, alerting, and automated decision routing based on error classification.

The current system already uses structured dicts for validation results (`validate_planner_decision_against_evidence` returns `{"ok": bool, "violations": list, "evidence_contract": dict}`), but many helper functions and guard evaluators return plain strings, simple booleans, or inconsistent dict shapes. The plan standardizes all error-returning paths to use the error code schema defined in `error_handling_audit.py`.

## Types

### Error Result Dict Schema
All error-returning functions must return a consistent dict:
```python
{
    "ok": False,  # True for success, False for error
    "error_code": "PLANNER_DECISION_BLOCKED",  # Constant from error_handling_audit.py
    "summary": "Human-readable summary of the error",
    "diagnostic": {
        "error_type": "ValidationError",  # Optional exception type
        "error": "Detailed error message (truncated to 1000 chars)",
        "step": 5,  # Current step number
        "job_id": "abc123",  # Current job ID
        "context": {...}  # Additional context specific to this error
    },
    "retry_allowed": True,  # Whether retry is possible
    "fallback_action": None,  # Optional fallback action dict
}
```

### Error Code Registry
Extend `error_handling_audit.py` with a complete registry:
- `ERROR_CODES`: Dict mapping code strings to metadata (severity, retry_allowed, category)
- `classify_error(code)`: Returns metadata for a given error code
- `is_retryable(code)`: Returns whether the error allows retry

## Files

### New Files
- `services/aicarmine_broker/application/planner/error_codes.py` - Error code registry and classification utilities
- `services/aicarmine_broker/application/planner/error_result.py` - Standardized error result builder functions

### Modified Files
- `services/aicarmine_broker/application/planner/decision.py` - Update `validate_planner_decision_against_evidence` to return structured error dicts instead of stub
- `services/aicarmine_broker/application/planner/decision_normalizer.py` - Update normalization functions to propagate error codes
- `services/aicarmine_broker/application/planner/planner_validation.py` - Update validation helpers to return structured errors
- `services/aicarmine_broker/application/planner/validator.py` - Update validator functions to use structured error results
- `services/aicarmine_broker/application/planner/loop.py` - Update error handling in `run_agentic_planner_job` to use structured error codes
- `services/aicarmine_broker/application/planner/error_handling_audit.py` - Extend with complete error code registry

## Functions

### New Functions
- `build_error_result(error_code: str, summary: str, *, step: int = 0, job_id: str = "", context: dict | None = None) -> dict` - Standardized error result builder
- `classify_error(code: str) -> dict` - Returns error metadata from registry
- `is_retryable(code: str) -> bool` - Checks if error allows retry
- `propagate_error(current_result: dict, new_error_code: str) -> dict` - Chains errors while preserving original context

### Modified Functions
- `validate_planner_decision_against_evidence()` in `decision.py` - Replace stub with full validation logic returning structured error dicts
- `_normalize_terminal_planner_decision()` in `decision_normalizer.py` - Add error code propagation
- `controller_guard_result_for_validation()` in `planner_validation.py` - Return structured error dicts instead of ad-hoc dicts
- `evaluate_memory_claim_guard()` in `guard_evaluator.py` - Use structured error results
- `execute_judge_lane()` in `judge_lane.py` - Return structured error codes for terminal_block/rewrite_required decisions

## Classes

No new classes required. Existing `PlannerLoopState`, `GuardEvaluator`, `PlannerLoopController` will use the new error result functions directly.

## Dependencies

No new package dependencies required. All changes use existing stdlib (`json`, `logging`) and existing project modules. The `error_handling_audit.py` module already provides the foundation; `error_codes.py` extends it with the full registry.

## Testing

### Test Requirements
1. Unit tests for `build_error_result()` with various parameters
2. Unit tests for `classify_error()` and `is_retryable()` with all defined error codes
3. Integration tests for `validate_planner_decision_against_evidence()` returning structured errors on validation failures
4. Regression tests confirming existing loop behavior is preserved (no functional changes to decision flow)
5. Tests verifying error code propagation through guard evaluators

### Validation Strategy
- Run existing pytest suite: `pytest services/aicarmine_broker/ -v`
- Verify no regression in planner decision outcomes
- Confirm new error codes appear in agent event logs

## Implementation Order

1. Create `error_codes.py` with complete error code registry
2. Create `error_result.py` with standardized builder functions
3. Update `error_handling_audit.py` to reference the new modules
4. Modify `decision.py` to use structured error results in validation
5. Update `planner_validation.py` and `validator.py` to propagate error codes
6. Modify `loop.py` to handle structured error codes in decision flow
7. Add tests for all new functions and integration points
8. Run full test suite and verify no regressions