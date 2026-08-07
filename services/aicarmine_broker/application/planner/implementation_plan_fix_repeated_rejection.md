# Implementation Plan: Fix Repeated Final Rejection Deadlock

## Overview

This plan addresses the agentic loop deadlock where `final_rewrite_latch` reaches `"terminal_block_required"` after 2+ final-quality rejections, then permanently blocks ALL `action=final` decisions even when substantively valid final answers are produced with concrete evidence paths. The loop terminates as `blocked_needs_attention` instead of accepting valid final answers.

## Problem Analysis

### Symptom
- Agentic loop produces `status=blocked_needs_attention` with `blocker=terminal_block_required_final_disallowed`
- Job history shows 3 controller guard events followed by terminal block
- 9 successful `repo_read` calls with concrete content evidence exist but are ignored

### Evidence
1. **validator.py lines 1410-1432**: Terminal block check happens BEFORE quality evaluation
   ```python
   if (final_rewrite_latch == "terminal_block_required" and planner_may_choose_block) or planner_forced_terminal_block:
       violations.append("terminal_block_required_final_disallowed")
       ...
       return {"ok": False, "violations": violations, "evidence_contract": contract}
   ```

2. **validator.py lines 1561-1562**: `_clear_final_terminal_block_state` is called AFTER violations check
   ```python
   if not violations:
       contract = _clear_final_terminal_block_state(contract)
   ```

3. **Job artifact job-4a86cf08**: Shows 9 successful repo_read paths with concrete content, but final rejected due to latch blocking

4. **validator.py lines 104-124**: `_next_final_rewrite_latch` logic allows one retry, then blocks at count >= 2

### Confirmed Cause
The terminal block check at line 1413 executes before substantive quality evaluation (lines 1508-1548). When `final_rewrite_latch == "terminal_block_required"`, the validator returns early with `ok=False` without evaluating whether the current final answer has substantive evidence. This creates a deadlock where valid final answers are permanently blocked after initial quality rejections.

### Minimal Fix
Add an early evidence-aware reset of the terminal block latch within the `action in {"final", "done", "complete", "completed"}` block, BEFORE the terminal block check at line 1413. The reset should trigger when:
- The final answer contains concrete evidence paths (`successful_repo_read_paths` with verified content)
- No missing coverage remains (`coverage_satisfied=True`)
- The final answer is substantively complete (non-empty, addresses goal)

### Verification
- Valid final answers with evidence should pass validation even when latch was `"terminal_block_required"`
- Invalid final answers (empty, missing coverage) should still be rejected
- Existing rewrite lane logic preserved for cases without evidence

### Residual Risk
- Lowering the threshold too much could allow premature finals
- Need to ensure evidence verification is strict enough to prevent false positives

## Types

### Terminal Block Reset Contract
```python
# New field in evidence contract
{
    "evidence_aware_final_reset": {
        "enabled": True,
        "min_evidence_paths": 3,
        "require_coverage_satisfied": True,
        "require_non_empty_answer": True,
        "schema": "terminal_block_reset.v1"
    }
}
```

### Evidence Verification Schema
```python
def _verify_evidence_aware_final_reset(final_answer: str, contract: dict) -> dict:
    """Returns True if final answer has substantive evidence warranting latch reset."""
    return {
        "ok": bool(ok),
        "evidence_path_count": int(count),
        "coverage_satisfied": bool(satisfied),
        "answer_non_empty": bool(non_empty),
        "reset_reason": str(reason)
    }
```

## Files

### Modified Files
1. **`services/aicarmine_broker/application/planner/validator.py`** (2227 lines)
   - Add `_evaluate_evidence_aware_final_reset` function (~50 lines)
   - Modify `validate_planner_decision_against_evidence` to call early reset before terminal block check (~10 lines)
   - Result: ~60 new lines, no existing line changes except insertion

## Functions

### New Function
- **`_evaluate_evidence_aware_final_reset(contract: dict[str, Any]) -> dict[str, Any]`**
  - Path: `services/aicarmine_broker/application/planner/validator.py`
  - Purpose: Evaluate whether a final answer has sufficient evidence to warrant resetting the terminal block latch
  - Returns: `{"ok": bool, "reset_latch": bool, "reason": str}`

### Modified Logic
- **Inside `validate_planner_decision_against_evidence`** (line ~1391)
  - Current: Terminal block check at line 1413 happens immediately
  - New: Evidence-aware reset evaluated BEFORE terminal block check
  - If evidence_aware_reset returns `reset_latch=True`, clear terminal block state and allow final

## Classes

No class modifications required. All changes are within `validate_planner_decision_against_evidence` function.

## Dependencies

### No External Dependencies
- All logic uses existing internal functions: `_clear_final_terminal_block_state`, `_minimum_read_coverage_satisfied`, `_successful_read_paths_for_final_route`
- No new package requirements

## Testing

### Test Requirements
1. **Evidence-aware reset test**: Create a scenario where `final_rewrite_latch == "terminal_block_required"` but `successful_repo_read_paths` contains 3+ verified paths with content
   - Expected: Validation passes with `ok=True`, latch reset to `"inactive"`

2. **Invalid final still rejected**: Final answer with no evidence or missing coverage
   - Expected: Validation fails with appropriate violation

3. **Existing rewrite lane preserved**: Cases without evidence should still follow rewrite lane logic
   - Expected: `final_rewrite_latch` transitions through `"rewrite_required"` → `"required_gap_only"` → `"terminal_block_required"` as before

4. **Regression test**: Existing valid finals without prior rejection
   - Expected: Behavior unchanged, passes validation

### Validation Strategies
- Unit tests for `_evaluate_evidence_aware_final_reset` with various contract states
- Integration test simulating the job-4a86cf08 scenario (9 repo_reads, final rejected)
- Verify final accepted after fix

## Implementation Order

1. **Step 1**: Add `_evaluate_evidence_aware_final_reset` function after line ~530 (after `_answer_chunk_misuses_terminal_payload_shape`)
   - Implement evidence verification logic
   - Check `successful_repo_read_paths`, `coverage_satisfied`, `final_answer` non-empty

2. **Step 2**: Modify terminal block check in `validate_planner_decision_against_evidence` (around line 1410)
   - Insert evidence-aware reset evaluation BEFORE the terminal block check
   - If reset triggers, call `_clear_final_terminal_block_state` and continue to quality evaluation

3. **Step 3**: Update `final_rewrite_latch` state when reset occurs
   - Set `final_rewrite_latch = "inactive"`
   - Set `planner_may_choose_final = True`
   - Clear `planner_forced_terminal_block` flags

4. **Step 4**: Add unit tests in existing test file or new test module
   - Test evidence_aware_reset with sufficient paths
   - Test rejection when evidence insufficient
   - Test regression cases

5. **Step 5**: Verify with job artifact replay
   - Load job-4a86cf08 events
   - Replay validation logic with fix applied
   - Confirm final accepted instead of blocked