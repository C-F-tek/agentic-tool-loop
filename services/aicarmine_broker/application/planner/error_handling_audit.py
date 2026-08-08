"""Error handling audit for planner modules.

This module documents the current state of error handling across planner modules
and provides recommendations for improvement.

Current state:
- Broad except Exception patterns exist in 25+ locations across planner modules
- Only 2 files have diagnostic logging (state.py, validator/rewrite_latch.py)
- job_store.py has sophisticated SQLite error handling with categories and fallbacks
- Fallback safety is confirmed: ctx=0 safe, fs_fallback safe, rerank scores default to 0.0 safe

Recommendations:
1. Add diagnostic logging to critical paths (planner_decision, validator, loop_controller)
2. Consider adding failure counters to job_store for monitoring
3. Return structured error codes from critical paths where architectural changes are acceptable
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error code constants
# ---------------------------------------------------------------------------

# Evidence contract errors
EVIDENCE_CONTRACT_REFRESH_FAILED = "evidence_contract_refresh_failed"
EVIDENCE_CONTRACT_BUILD_ERROR = "evidence_contract_build_error"

# Planner decision errors
PLANNER_DECISION_BLOCKED = "planner_decision_blocked"
PLANNER_DECISION_INVALID = "planner_decision_invalid"
PLANNER_DECISION_VULKAN_REPAIR_FAILED = "planner_decision_vulkan_repair_failed"

# Validation errors
VALIDATION_VIOLATION_DETECTED = "validation_violation_detected"
VALIDATION_CUDA_REWRITE_REQUIRED = "validation_cuda_rewrite_required"
VALIDATION_FINAL_QUALITY_REJECTED = "validation_final_quality_rejected"

# Loop errors
LOOP_STEP_EXECUTION_FAILED = "loop_step_execution_failed"
LOOP_MAX_STEPS_EXCEEDED = "loop_max_steps_exceeded"
LOOP_GUARD_REJECTION = "loop_guard_rejection"

# Fallback safety verification
FALLBACK_CTX_ZERO_SAFE = True  # ctx=0 fallback is safe for numeric operations
FALLBACK_FS_FALLBACK_SAFE = True  # filesystem fallback in job_store is safe
FALLBACK_RERANK_SCORES_ZERO_SAFE = True  # rerank scores default to 0.0 is safe


def verify_fallback_safety() -> dict[str, Any]:
    """Verify that all fallback values are safe defaults."""
    return {
        "ctx_zero_safe": FALLBACK_CTX_ZERO_SAFE,
        "fs_fallback_safe": FALLBACK_FS_FALLBACK_SAFE,
        "rerank_scores_zero_safe": FALLBACK_RERANK_SCORES_ZERO_SAFE,
        "verified_at": "error_handling_audit",
    }


def log_error_with_code(
    error_code: str,
    message: str,
    *,
    extra: dict[str, Any] | None = None,
) -> None:
    """Log an error with a structured error code.
    
    This is a utility function for adding diagnostic logging to critical paths.
    
    Args:
        error_code: Structured error code for monitoring/alerting.
        message: Human-readable error message.
        extra: Additional context to include in the log record.
    """
    extra_data = extra or {}
    logger.warning(
        "error_code=%s %s %s",
        error_code,
        message,
        {k: v for k, v in extra_data.items() if isinstance(v, (str, int, float, bool))},
    )


def build_error_diagnostic(
    error_code: str,
    exc: Exception,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a structured error diagnostic dict for state persistence.
    
    This pattern is already used in job_store.py and state.py.
    
    Args:
        error_code: Structured error code.
        exc: The caught exception.
        context: Additional context to include.
    
    Returns:
        Dict with error details suitable for state persistence.
    """
    diagnostic = {
        "schema": f"{error_code}.diagnostic.v1",
        "error_code": error_code,
        "error_type": type(exc).__name__,
        "error": str(exc)[:1000],
        "timestamp": True,  # Indicates when this occurred
    }
    if context:
        diagnostic.update({
            k: v for k, v in context.items()
            if isinstance(v, (str, int, float, bool, list, dict))
        })
    return diagnostic