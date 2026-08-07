# Implementation Plan: Fix Repeated Identical Planner Rejection Loop

## Overview

Fix the agentic loop planner getting stuck in a repeated cycle where it tries `repo_list_files` → `repo_read` → `block`, gets rejected by controller, then repeats the exact same pattern instead of trying alternative actions. This causes `repeated_identical_planner_rejection` blocking after 8 steps instead of completing with useful evidence.

## Problem Analysis

### Symptom
Job events show this pattern:
- Step 1: `repo_list_files` → ok=True
- Step 2: `repo_read` → ok=True
- Step 3: `block` decision → rejected (`block_not_allowed_by_evidence_contract`)
- Step 4: `repo_list_files` → ok=True (same as step 1)
- Step 5: `repo_read` → ok=True (same as step 2)
- Step 6: `block` decision → rejected again
- Step 7: `block` decision → rejected again
- Step 8: `block` decision → rejected → triggers `repeated_identical_planner_rejection`

### Root Cause
The validator rejection feedback (`required_next_progress`) is included in the evidence contract but the planner system prompt doesn't clearly guide the model toward trying different tool actions after rejection. The planner keeps cycling through the same tools because:

1. The system prompt doesn't emphasize that after rejection, it MUST try a different action
2. The candidate_actions alternative generation isn't being properly surfaced to the planner
3. The loop control flow doesn't explicitly track and flag repeated identical patterns early enough
4. The rejection guidance text is too technical and doesn't give clear actionable direction

## Types

### New State Tracking
```python
# In PlannerLoopState or contract state
rejection_history: list[dict]  # Track recent rejection patterns
identical_rejection_count: int  # Count consecutive identical rejections
alternative_action_suggested: bool  # Whether alternative action was suggested
```

### Enhanced Rejection Signature
```python
# In validation_rejections.py - add function for block decisions
def canonical_block_rejection_signature(decision, violations) -> dict
# Returns signature identifying block rejection pattern for dedup detection
```

## Files

### Modified Files

1. **services/aicarmine_broker/application/planner/validator.py**
   - Lines ~1680-1693: Enhance `required_next_progress` guidance for block rejections
   - Add explicit instruction to try different tool actions after rejection
   - Include concrete alternative tool suggestions based on evidence

2. **services/aicarmine_broker/application/planner/system_prompt.py**
   - Add section about handling validator rejection feedback
   - Clear instruction: "After rejection, you MUST try a different action, not repeat the same tools"
   - Surface candidate_actions alternatives prominently in prompt

3. **services/aicarmine_broker/application/planner/loop.py**
   - Lines ~200-500: Enhance loop control flow to track repeated patterns
   - Add early detection of identical tool sequences (before hitting max_steps)
   - Pass rejection history to planner more explicitly

4. **services/aicarmine_broker/application/planner/validation_rejections.py**
   - Lines 1-100: Add function to detect repeated identical tool sequences
   - Track `(tool_sequence, action)` patterns across steps
   - Trigger enhanced guidance when pattern repeats

5. **services/aicarmine_broker/application/tool_surface/candidate_actions.py**
   - Ensure alternative actions are properly generated and surfaced
   - After N rejections, force suggestion of different tool category

6. **services/aicarmine_broker/application/planner/state.py**
   - Add `rejection_history` field to track pattern
   - Add `consecutive_identical_tool_sequence_count` counter

### New Files

1. **services/aicarmine_broker/application/planner/repeated_pattern_detector.py** (NEW)
   - Core logic for detecting repeated identical tool sequences
   - Function: `detect_repeated_pattern(rejection_history) -> dict`
   - Returns pattern type, count, and suggested alternative actions

## Functions

### New Functions

1. **`detect_repeated_identical_sequence(rejection_history: list) -> dict`**
   - File: `repeated_pattern_detector.py`
   - Detects when same tool sequence repeats after rejection
   - Returns: `{pattern_type: "identical_sequence", count: int, suggested_alternatives: list}`

2. **`enhance_block_rejection_guidance(contract: dict) -> str`**
   - File: `validator.py`
   - Generates clearer, more actionable guidance for block rejections
   - Includes explicit instruction to try different tools

3. **`surface_alternative_actions(contract: dict) -> list`**
   - File: `candidate_actions.py`
   - After N rejections, returns different category of actions
   - Prioritize actions not yet tried in recent history

4. **`update_rejection_tracking(state: PlannerLoopState, decision: dict) -> None`**
   - File: `loop.py`
   - Tracks rejection patterns in state
   - Updates consecutive identical sequence counter

5. **`inject_rejection_guidance_into_prompt(system_prompt: str, rejection_history: list) -> str`**
   - File: `system_prompt.py`
   - Adds explicit rejection handling instructions to planner prompt
   - Emphasizes trying different actions after rejection

## Classes

### New Class

1. **`RepeatedPatternDetector`**
   - File: `repeated_pattern_detector.py`
   - Core detection logic for pattern analysis
   - Methods:
     - `track_pattern(decision, tool_sequence)` - track new decision
     - `get_pattern_info() -> dict` - return current pattern info
     - `should_suggest_alternatives() -> bool` - check if alternatives needed
     - `get_alternative_suggestions() -> list` - return suggested different actions

### Modified Classes

1. **`PlannerLoopState`**
   - File: `state.py`
   - Add fields:
     - `rejection_history: list[dict]`
     - `consecutive_identical_tool_sequence_count: int`
     - `pattern_detector: RepeatedPatternDetector | None`

## Dependencies

No new external dependencies required. All changes use existing Python stdlib and project internals.

## Testing

### Test Requirements

1. **Unit tests for `detect_repeated_identical_sequence`**
   - Verify detection of identical tool sequences
   - Verify correct counting of repetitions
   - Verify alternative suggestion generation

2. **Integration test for loop flow**
   - Simulate rejection cycle and verify early termination
   - Verify guidance injection into prompt
   - Verify state tracking updates

3. **Validation test**
   - Verify enhanced rejection guidance is actionable
   - Verify system prompt includes rejection handling instructions

### Validation Strategy

Run existing agentic loop self-test:
```powershell
python services/test_agentic_loop_selftest.py
```

Verify jobs complete with useful evidence instead of hitting repeated_rejection block.

## Implementation Order

1. **Create `repeated_pattern_detector.py`** - Core detection logic
2. **Update `state.py`** - Add rejection tracking fields to PlannerLoopState
3. **Update `validator.py`** - Enhance block rejection guidance text
4. **Update `system_prompt.py`** - Add rejection handling instructions
5. **Update `loop.py`** - Integrate pattern detection into loop flow
6. **Update `candidate_actions.py`** - Ensure alternatives are surfaced after rejections
7. **Update `validation_rejections.py`** - Add pattern signature detection
8. **Test and validate** - Run self-test, verify job completion

## Key Design Decisions

### Decision 1: Early Detection Threshold
- Current: Triggers at repeated rejection (step 8+)
- Target: Trigger enhanced guidance at step 4-5 (after 2 identical sequences)
- Rationale: Give planner chance to try alternatives before exhausting steps

### Decision 2: Alternative Action Generation
- After 2 identical rejections, force suggestion of different tool category
- Example: If sequence is `[repo_list_files, repo_read, block]`, suggest `planner_scratchpad_write` or `repo_semantic_search`
- Rationale: Break the cycle by explicitly suggesting untried actions

### Decision 3: Guidance Injection Method
- Inject rejection handling instructions directly into system prompt
- Not just in evidence contract - make it prominent in planner instructions
- Rationale: LLM responds better to explicit instructions than implicit contract fields

### Decision 4: Pattern Tracking Scope
- Track last 4-6 steps for pattern detection
- Compare `(tool_sequence, action)` tuples across steps
- Rationale: Balance between detecting real patterns vs false positives