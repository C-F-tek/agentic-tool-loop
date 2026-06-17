# Implementation Plan

## [Overview]

Fix S3 (terminal judge) issues in `judge_blocked_job()` to ensure non-blocking failure handling and proper artifact separation.

This implementation addresses three critical issues in the terminal judge flow:
1. **Artifact separation**: `terminal_judge_report` should contain the report directly, not the envelope with persistence path
2. **Non-blocking persistence**: Writing `terminal-judge.json` must not block job finalization if it fails
3. **Non-blocking event emission**: Both `terminal_judge_completed` and fallback `terminal_judge_failed` events must be wrapped in try/except

The fix ensures that job finalization always completes successfully, even when artifact persistence or event emission fails. The terminal judge artifact is written separately from the result, keeping the report consumable without requiring file reload.

## [Types]

No new types are introduced. Existing types are reused:
- `terminal_judge_blocked.v1` - Schema for judge report (existing)
- `terminal_judge_artifact.v1` - Schema for persistence artifact (existing)

The artifact envelope structure remains:
```python
{
    "schema": "terminal_judge_artifact.v1",
    "job_id": str,
    "root_path": str,
    "status": str,
    "report": dict  # Direct report, not envelope
}
```

## [Files]

- **Modified**: `services/aicarmine_broker/planner.py`
  - Function `judge_blocked_job()` (lines 5477-5589)
  - Changes:
    1. Separate `terminal_judge_report` from `terminal_judge_artifact`
    2. Wrap `write_json()` in try/except with non-blocking fallback
    3. Update `terminal_judge_report` to contain `judge_report` directly
    4. Update `terminal_judge_artifact` to contain path string instead of full envelope
    5. Wrap `terminal_judge_completed` event emission in try/except with fallback to `terminal_judge_failed`

## [Functions]

- **Modified**: `judge_blocked_job()` in `services/aicarmine_broker/planner.py`
  - Current signature: `judge_blocked_job(job_id, root, state, status, result, tool_context)`
  - Changes:
    1. Line 5532: Change `result["terminal_judge_report"] = judge_artifact` to `result["terminal_judge_report"] = judge_report`
    2. Line 5537: Wrap `write_json(judge_path, judge_artifact)` in try/except
    3. Lines 5540-5551: Update failed write handler to set `judge_report["persistence_ok"] = False` and error details
    4. Line 5568: Change event payload from `{..., "judge_report": judge_artifact}` to `{..., "judge_report": judge_artifact}` (keep as is, but artifact now has path string)
    5. Lines 5571-5587: Wrap `terminal_judge_completed` emit in try/except, fallback to `terminal_judge_failed`

## [Classes]

No classes are modified or created.

## [Dependencies]

No new dependencies. Uses existing:
- `write_json()` from `job_store`
- `append_agent_event()` from `job_store`

## [Testing]

No test files are created per the ban on unrequested tests. Verification is done via:
- Static code review of the unified diff
- `git diff --check` after patch application
- Manual inspection of the modified function

## [Implementation Order]

1. Read current `judge_blocked_job()` implementation to confirm exact old text
2. Create SEARCH/REPLACE block with all required changes
3. Validate unified diff with `aicarmine_repo_code_unidiff_validate`
4. Check git apply with `aicarmine_repo_code_git_apply_check`
5. Apply patch with `aicarmine_repo_code_apply_patch`
6. Verify modified file line count matches expected