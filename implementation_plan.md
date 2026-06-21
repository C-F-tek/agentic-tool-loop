# Implementation Plan: Judge-RewriteConvergence Architecture

## Overview

This implementation plan addresses the infinite loop problem in the agentic planner loop by converging the `planner.cuda_rewrite` lane with the `judge.final_quality` lane into a unified judge authority pattern. The current system has `planner.cuda_rewrite` acting as an infinite retry mechanism that sends rejected decisions back to the same GPU1 planner model without true judgment authority. The goal is to create a single AI model that takes different roles (preplanner, planner, judge, repair) based on the current figure/context, with the judge having authority to accept final proposals or request continued discovery.

The existing lane catalog already defines 28 control lanes including `judge.final_quality`, `planner.cuda_rewrite`, `preplanner.semantic_query`, and `repair.vulkan_gpu0`. The implementation merges the rewritecuda retry logic into the judge authority pattern, so that when evidence is sufficient the judge approves final, and when evidence is insufficient the judge requests continued discovery with concrete suggestions.

## Types

```python
# Lane authority types that determine decision behavior
class LaneAuthority(str, Enum):
    PROPOSAL_ONLY = "proposal_only"      # planner.primary - proposes actions
    JUDGE_ONLY = "judge_only"            # judge.final_quality - accepts/rejects final
    ADVISORY_ONLY = "advisory_only"      # preplanner, replan - advisory only
    REPAIR_ONLY = "repair_only"          # repair.vulkan_gpu0 - fixes invalid states
    BOUNDED_SELECTION = "bounded_selection"  # orientation lanes - bounded selection

# Judge decision outcomes that control flow
class JudgeDecision(str, Enum):
    FINAL_ALLOWED = "final_allowed"           # Evidence sufficient → proceed to final
    CONTINUE_DISCOVERY = "continue_discovery" # Evidence insufficient → continue with suggestions
    TERMINAL_BLOCK = "terminal_block"         # Blocked state → terminate
    REWRITE_REQUIRED = "rewrite_required"     # Needs rewrite → cuda_rewrite lane

# Lane figure/role that the AI model takes
class AIFigure(str, Enum):
    PREPLANNER = "preplanner"      # Semantic query and RAG preseed
    PLANNER = "planner"            # Primary action proposal
    JUDGE = "judge"                # Quality gate and final decision
    REPAIR = "repair"              # Vulkan JSON/state repair
```

## Files

### New Files to Create

1. **`services/aicarmine_broker/application/planner/lane_authority.py`**
   - Defines `LaneAuthority` enum and judge decision logic
   - Provides `evaluate_judge_decision()` function that returns JudgeDecision based on evidence_contract

2. **`services/aicarmine_broker/application/planner/ai_figure.py`**
   - Defines `AIFigure` enum and figure-to-system prompt mapping
   - Provides `get_figure_instruction(figure, context)` that returns the appropriate system instruction

3. **`services/aicarmine_broker/application/planner/judge_lane.py`**
   - Implements `execute_judge_lane()` function that:
     - Takes evidence_contract and current history
     - Calls GPU1 planner with judge figure/system prompt
     - Returns JudgeDecision (FINAL_ALLOWED, CONTINUE_DISCOVERY, TERMINAL_BLOCK)
     - If CONTINUE_DISCOVERY, includes concrete suggestions for next actions

### Existing Files to Modify

4. **`services/aicarmine_broker/application/planner/loop.py`**
   - Replace `planner_cuda_rewrite_guard_for_validation` call with `execute_judge_lane()`
   - When judge returns FINAL_ALLOWED → allow planner to choose final
   - When judge returns CONTINUE_DISCOVERY → inject suggestions into planner prompt
   - When judge returns TERMINAL_BLOCK → block job
   - Remove `MAX_CUDA_REWRITE_ATTEMPTS` counter (replaced by judge authority)

5. **`services/aicarmine_broker/application/planner/validator.py`**
   - Update `_escalate_final_rewrite_retry_count()` to use judge decision instead of rewrite latch
   - Add `evaluate_for_judge()` function that prepares evidence_contract for judge evaluation

6. **`services/aicarmine_broker/application/planner/turn.py`**
   - Update `planner_role_override` to support figure-based system prompts
   - Add `get_figure_system_prompt(figure)` that returns appropriate instruction

7. **`services/aicarmine_broker/application/planner/lane_catalog.py`**
   - Update `planner.cuda_rewrite` description to reflect convergence with judge
   - Add `judge.final_quality` as the authoritative convergence point

## Functions

### New Functions

1. **`evaluate_judge_decision(evidence_contract, history) -> JudgeDecision`**
   - File: `lane_authority.py`
   - Purpose: Determine if evidence is sufficient for final or if discovery should continue
   - Logic: Check coverage_satisfied, missing_owner_paths, validation_rejections

2. **`execute_judge_lane(goal, history, evidence_contract) -> dict`**
   - File: `judge_lane.py`
   - Purpose: Call GPU1 planner with judge figure/system prompt
   - Returns: {decision, rationale, suggestions_if_continue}

3. **`get_figure_instruction(figure, context) -> str`**
   - File: `ai_figure.py`
   - Purpose: Return appropriate system instruction for the current figure
   - Maps: preplanner → semantic query instruction, judge → quality gate instruction

### Modified Functions

4. **`run_agentic_planner_job()` in loop.py**
   - Replace cuda_rewrite guard with judge_lane evaluation
   - When judge returns CONTINUE_DISCOVERY, inject suggestions into planner prompt

5. **`_escalate_final_rewrite_retry_count()` in validator.py**
   - Replace rewrite latch logic with judge decision logic
   - Use JudgeDecision instead of final_rewrite_latch

## Dependencies

No new external packages required. The implementation leverages:
- Existing GPU1 planner model (Qwen3.6-35B-coding-v5:latest)
- Existing evidence_contract schema
- Existing lane_catalog.py infrastructure

## Testing

1. Unit tests for `evaluate_judge_decision()` with various evidence_contract states
2. Integration test: judge_lane returns FINAL_ALLOWED when coverage_satisfied=True
3. Integration test: judge_lane returns CONTINUE_DISCOVERY with suggestions when missing_owner_paths
4. Regression test: existing loop behavior preserved when judge is not active

## Implementation Order

1. Create `lane_authority.py` with enums and evaluate_judge_decision()
2. Create `ai_figure.py` with figure-to-instruction mapping
3. Create `judge_lane.py` with execute_judge_lane()
4. Update `loop.py` to use judge_lane instead of cuda_rewrite guard
5. Update `validator.py` to use judge decision instead of rewrite latch
6. Update `turn.py` to support figure-based system prompts
7. Update `lane_catalog.py` descriptions
8. Run existing test suite to verify no regressions