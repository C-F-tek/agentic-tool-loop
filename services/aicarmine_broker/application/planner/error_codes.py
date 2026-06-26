"""Structured error code registry and classification utilities.

This module provides:
- ERROR_CODES: Complete registry mapping error codes to metadata
- classify_error(): Returns metadata for a given error code
- is_retryable(): Checks if an error allows retry
"""
from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Error Code Registry
# ---------------------------------------------------------------------------

ERROR_CODES: dict[str, dict[str, Any]] = {
    # Evidence contract errors
    "EVIDENCE_CONTRACT_REFRESH_FAILED": {
        "code": "EVIDENCE_CONTRACT_REFRESH_FAILED",
        "category": "evidence_contract",
        "severity": "high",
        "retry_allowed": False,
        "description": "Evidence contract refresh failed during history update",
    },
    "EVIDENCE_CONTRACT_BUILD_ERROR": {
        "code": "EVIDENCE_CONTRACT_BUILD_ERROR",
        "category": "evidence_contract",
        "severity": "high",
        "retry_allowed": False,
        "description": "Failed to build evidence contract from history",
    },

    # Planner decision errors
    "PLANNER_DECISION_BLOCKED": {
        "code": "PLANNER_DECISION_BLOCKED",
        "category": "planner_decision",
        "severity": "critical",
        "retry_allowed": False,
        "description": "Planner decision blocked - requires attention",
    },
    "PLANNER_DECISION_INVALID": {
        "code": "PLANNER_DECISION_INVALID",
        "category": "planner_decision",
        "severity": "high",
        "retry_allowed": True,
        "description": "Planner decision failed validation",
    },
    "PLANNER_DECISION_VULKAN_REPAIR_FAILED": {
        "code": "PLANNER_DECISION_VULKAN_REPAIR_FAILED",
        "category": "planner_decision",
        "severity": "medium",
        "retry_allowed": True,
        "description": "Vulkan/GPU0 repair attempt failed",
    },

    # Validation errors
    "VALIDATION_VIOLATION_DETECTED": {
        "code": "VALIDATION_VIOLATION_DETECTED",
        "category": "validation",
        "severity": "medium",
        "retry_allowed": True,
        "description": "Validation violation detected in decision",
    },
    "VALIDATION_CUDA_REWRITE_REQUIRED": {
        "code": "VALIDATION_CUDA_REWRITE_REQUIRED",
        "category": "validation",
        "severity": "medium",
        "retry_allowed": True,
        "description": "CUDA rewrite required for rejected proposal",
    },
    "VALIDATION_FINAL_QUALITY_REJECTED": {
        "code": "VALIDATION_FINAL_QUALITY_REJECTED",
        "category": "validation",
        "severity": "high",
        "retry_allowed": True,
        "description": "Final quality check rejected the decision",
    },

    # Loop errors
    "LOOP_STEP_EXECUTION_FAILED": {
        "code": "LOOP_STEP_EXECUTION_FAILED",
        "category": "loop",
        "severity": "critical",
        "retry_allowed": False,
        "description": "Loop step execution failed unrecoverably",
    },
    "LOOP_MAX_STEPS_EXCEEDED": {
        "code": "LOOP_MAX_STEPS_EXCEEDED",
        "category": "loop",
        "severity": "medium",
        "retry_allowed": False,
        "description": "Maximum steps exceeded before completion",
    },
    "LOOP_GUARD_REJECTION": {
        "code": "LOOP_GUARD_REJECTION",
        "category": "loop",
        "severity": "medium",
        "retry_allowed": True,
        "description": "Guard evaluator rejected the decision",
    },

    # Tool execution errors
    "TOOL_EXECUTION_FAILED": {
        "code": "TOOL_EXECUTION_FAILED",
        "category": "tool_execution",
        "severity": "high",
        "retry_allowed": True,
        "description": "Tool execution failed with error",
    },
    "TOOL_CACHE_MISS": {
        "code": "TOOL_CACHE_MISS",
        "category": "tool_execution",
        "severity": "low",
        "retry_allowed": False,
        "description": "Tool cache miss - executing fresh",
    },
    "TOOL_APPROVAL_DENIED": {
        "code": "TOOL_APPROVAL_DENIED",
        "category": "tool_execution",
        "severity": "medium",
        "retry_allowed": False,
        "description": "Tool approval denied by user or policy",
    },

    # Memory errors
    "MEMORY_FALSE_UNAVAILABLE_CLAIM": {
        "code": "MEMORY_FALSE_UNAVAILABLE_CLAIM",
        "category": "memory",
        "severity": "high",
        "retry_allowed": True,
        "description": "Planner falsely claimed long-term memory unavailable",
    },
    "MEMORY_READ_FAILED": {
        "code": "MEMORY_READ_FAILED",
        "category": "memory",
        "severity": "medium",
        "retry_allowed": True,
        "description": "Failed to read from project memory",
    },

    # Output format errors
    "OUTPUT_INCOMPREHENSIBLE": {
        "code": "OUTPUT_INCOMPREHENSIBLE",
        "category": "output_format",
        "severity": "high",
        "retry_allowed": True,
        "description": "Planner output is incomprehensible - retry required",
    },
    "OUTPUT_UNRECOVERABLE": {
        "code": "OUTPUT_UNRECOVERABLE",
        "category": "output_format",
        "severity": "critical",
        "retry_allowed": False,
        "description": "Planner output is unrecoverable after max retries",
    },
    "OUTPUT_NON_JSON_PURE": {
        "code": "OUTPUT_NON_JSON_PURE",
        "category": "output_format",
        "severity": "high",
        "retry_allowed": True,
        "description": "Planner returned non-JSON text in native mode",
    },

    # Code product errors
    "CODE_PRODUCT_DUPLICATE_WRITE": {
        "code": "CODE_PRODUCT_DUPLICATE_WRITE",
        "category": "code_product",
        "severity": "medium",
        "retry_allowed": True,
        "description": "Duplicate write attempt detected for code product",
    },
    "CODE_PRODUCT_LOW_SIGNAL": {
        "code": "CODE_PRODUCT_LOW_SIGNAL",
        "category": "code_product",
        "severity": "low",
        "retry_allowed": False,
        "description": "Low signal target detected for code product work",
    },
    "CODE_PRODUCT_INVALID_SIGNATURE": {
        "code": "CODE_PRODUCT_INVALID_SIGNATURE",
        "category": "code_product",
        "severity": "high",
        "retry_allowed": True,
        "description": "Invalid code product decision signature",
    },

    # Judge lane errors
    "JUDGE_TERMINAL_BLOCK": {
        "code": "JUDGE_TERMINAL_BLOCK",
        "category": "judge_lane",
        "severity": "critical",
        "retry_allowed": False,
        "description": "Judge determined terminal block - insufficient evidence",
    },
    "JUDGE_REWRITE_REQUIRED": {
        "code": "JUDGE_REWRITE_REQUIRED",
        "category": "judge_lane",
        "severity": "medium",
        "retry_allowed": True,
        "description": "Judge determined rewrite required",
    },
    "JUDGE_FINAL_ALLOWED": {
        "code": "JUDGE_FINAL_ALLOWED",
        "category": "judge_lane",
        "severity": "low",
        "retry_allowed": False,
        "description": "Judge approved final - evidence sufficient",
    },

    # Coverage errors
    "COVERAGE_REQUIRED": {
        "code": "COVERAGE_REQUIRED",
        "category": "coverage",
        "severity": "high",
        "retry_allowed": False,
        "description": "Maximum steps reached before coverage satisfied",
    },
    "COVERAGE_NOT_SATISFIED": {
        "code": "COVERAGE_NOT_SATISFIED",
        "category": "coverage",
        "severity": "high",
        "retry_allowed": False,
        "description": "Planner failed to finalize with coverage satisfied",
    },
}


def classify_error(code: str) -> dict[str, Any]:
    """Return metadata for a given error code.
    
    Args:
        code: The error code string to look up.
        
    Returns:
        Dict with category, severity, retry_allowed, and description.
        Returns minimal dict if code not found.
    """
    if code in ERROR_CODES:
        return dict(ERROR_CODES[code])
    # Return minimal metadata for unknown codes
    return {
        "code": code,
        "category": "unknown",
        "severity": "medium",
        "retry_allowed": True,
        "description": f"Unknown error code: {code}",
    }


def is_retryable(code: str) -> bool:
    """Check whether an error code allows retry.
    
    Args:
        code: The error code string to check.
        
    Returns:
        True if retry is allowed, False otherwise.
    """
    metadata = classify_error(code)
    return bool(metadata.get("retry_allowed", True))


def get_category(code: str) -> str:
    """Extract the category from an error code.
    
    Args:
        code: The error code string.
        
    Returns:
        Category string (e.g., 'validation', 'planner_decision').
    """
    metadata = classify_error(code)
    return str(metadata.get("category", "unknown"))


def get_severity(code: str) -> str:
    """Extract the severity level from an error code.
    
    Args:
        code: The error code string.
        
    Returns:
        Severity string (e.g., 'high', 'medium', 'low', 'critical').
    """
    metadata = classify_error(code)
    return str(metadata.get("severity", "medium"))


def filter_by_category(category: str) -> list[str]:
    """Return all error codes in a given category.
    
    Args:
        category: The category to filter by.
        
    Returns:
        List of error code strings matching the category.
    """
    return [
        code for code, meta in ERROR_CODES.items()
        if meta.get("category") == category
    ]


def filter_by_severity(severity: str) -> list[str]:
    """Return all error codes with a given severity level.
    
    Args:
        severity: The severity level to filter by.
        
    Returns:
        List of error code strings matching the severity.
    """
    return [
        code for code, meta in ERROR_CODES.items()
        if meta.get("severity") == severity
    ]


def filter_retryable() -> list[str]:
    """Return all retryable error codes.
    
    Returns:
        List of error code strings that allow retry.
    """
    return [
        code for code, meta in ERROR_CODES.items()
        if meta.get("retry_allowed") is True
    ]


def filter_non_retryable() -> list[str]:
    """Return all non-retryable error codes.
    
    Returns:
        List of error code strings that do not allow retry.
    """
    return [
        code for code, meta in ERROR_CODES.items()
        if meta.get("retry_allowed") is False
    ]