"""Standardized error result builder functions.

This module provides utilities for building and manipulating structured error
results that conform to the error code schema defined in error_codes.py.

Functions:
- build_error_result(): Create a standardized error result dict
- build_success_result(): Create a standardized success result dict
- propagate_error(): Chain errors while preserving original context
"""
from __future__ import annotations

import logging
from typing import Any

from .error_codes import (
    ERROR_CODES,
    classify_error as _classify_error,
    is_retryable as _is_retryable,
)

logger = logging.getLogger(__name__)


def build_error_result(
    error_code: str,
    summary: str,
    *,
    step: int = 0,
    job_id: str = "",
    context: dict[str, Any] | None = None,
    error_type: str = "",
    error_message: str = "",
    fallback_action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a standardized error result dict.
    
    All error-returning functions should use this builder to ensure consistent
    dict shape across the planner decision flow.
    
    Args:
        error_code: Structured error code from ERROR_CODES registry.
        summary: Human-readable summary of the error.
        step: Current loop step number (default 0).
        job_id: Current job ID (default empty string).
        context: Additional context specific to this error.
        error_type: Optional exception type name.
        error_message: Optional truncated error message.
        fallback_action: Optional fallback action dict.
        
    Returns:
        Dict with ok=False, error_code, summary, diagnostic, retry_allowed,
        and optional fallback_action fields.
    """
    metadata = _classify_error(error_code)
    retry_allowed = bool(metadata.get("retry_allowed", True))
    
    diagnostic: dict[str, Any] = {
        "error_code": error_code,
        "step": step,
        "job_id": job_id,
    }
    
    if error_type:
        diagnostic["error_type"] = error_type
    if error_message:
        diagnostic["error"] = str(error_message)[:1000]
    if context:
        diagnostic["context"] = {
            k: v for k, v in context.items()
            if isinstance(v, (str, int, float, bool, list, dict))
        }
    
    result: dict[str, Any] = {
        "ok": False,
        "error_code": error_code,
        "summary": summary,
        "diagnostic": diagnostic,
        "retry_allowed": retry_allowed,
    }
    
    if fallback_action is not None:
        result["fallback_action"] = fallback_action
    
    return result


def build_success_result(
    *,
    step: int = 0,
    job_id: str = "",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a standardized success result dict.
    
    Args:
        step: Current loop step number (default 0).
        job_id: Current job ID (default empty string).
        context: Additional context specific to this success.
        
    Returns:
        Dict with ok=True, error_code="", summary, diagnostic fields.
    """
    diagnostic: dict[str, Any] = {
        "error_code": "",
        "step": step,
        "job_id": job_id,
    }
    
    if context:
        diagnostic["context"] = {
            k: v for k, v in context.items()
            if isinstance(v, (str, int, float, bool, list, dict))
        }
    
    return {
        "ok": True,
        "error_code": "",
        "summary": "Success",
        "diagnostic": diagnostic,
        "retry_allowed": False,
    }


def propagate_error(
    current_result: dict[str, Any],
    new_error_code: str,
    *,
    preserve_summary: bool = True,
) -> dict[str, Any]:
    """Chain errors while preserving original context.
    
    When a new error occurs during error handling, this function creates a
    chained error result that preserves the original error code while
    recording the new error code.
    
    Args:
        current_result: The current result dict (may be error or success).
        new_error_code: The new error code to record.
        preserve_summary: Whether to preserve the original summary.
        
    Returns:
        New error result dict with chained error information.
    """
    original_code = current_result.get("error_code", "")
    original_summary = current_result.get("summary", "")
    original_diagnostic = current_result.get("diagnostic", {})
    
    new_summary = f"Chained: {original_summary}" if preserve_summary and original_summary else f"Error code: {new_error_code}"
    
    diagnostic: dict[str, Any] = {
        "error_code": new_error_code,
        "original_error_code": original_code,
        "step": original_diagnostic.get("step", 0),
        "job_id": original_diagnostic.get("job_id", ""),
    }
    
    metadata = _classify_error(new_error_code)
    diagnostic["retry_allowed"] = bool(metadata.get("retry_allowed", True))
    
    return {
        "ok": False,
        "error_code": new_error_code,
        "summary": new_summary,
        "diagnostic": diagnostic,
        "retry_allowed": diagnostic.get("retry_allowed", True),
    }