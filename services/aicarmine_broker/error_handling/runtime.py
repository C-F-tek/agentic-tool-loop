# ------------------------------------------------------------------
# AICarmine Broker Error Handling Framework - Runtime
# ------------------------------------------------------------------
# This module provides runtime error tracking and context management
# for the broker error handling framework.
# ------------------------------------------------------------------

from __future__ import annotations

import time
import json
from typing import Any
from pathlib import Path
from contextlib import contextmanager


class ErrorContext:
    """Context for error handling with metadata."""
    def __init__(self, request_id: str = "", job_id: str = "", user_id: str = ""):
        self.request_id = request_id
        self.job_id = job_id
        self.user_id = user_id
        self.timestamp = time.time()
        self.metadata: dict[str, Any] = {}

    def to_dict(self) -> dict[str, Any]:
        """Convert error context to dictionary."""
        return {
            "request_id": self.request_id,
            "job_id": self.job_id,
            "user_id": self.user_id,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class ErrorContextManager:
    """Context manager for error handling."""
    def __init__(self, context: ErrorContext):
        self.context = context
        self.errors: list[Any] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.errors.append((exc_type, exc_val, exc_tb))
            return False
        return True

    def get_errors(self) -> list[Any]:
        """Get all errors captured in this context."""
        return self.errors


class RuntimeErrorTracker:
    """Tracks runtime errors and provides metrics."""
    def __init__(self):
        self.errors: list[dict[str, Any]] = []
        self.start_time = time.time()
        self.error_counts: dict[str, int] = {}
        self.error_severities: dict[str, int] = {}

    def record_error(self, error: Exception, category: str, severity: str, details: dict[str, Any] | None = None):
        """Record an error with metadata."""
        error_data = {
            "timestamp": time.time(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "category": category,
            "severity": severity,
            "details": details or {},
        }
        self.errors.append(error_data)
        self.error_counts[category] = self.error_counts.get(category, 0) + 1
        self.error_severities[severity] = self.error_severities.get(severity, 0) + 1

    def get_metrics(self) -> dict[str, Any]:
        """Get error metrics."""
        return {
            "total_errors": len(self.errors),
            "error_counts": self.error_counts,
            "error_severities": self.error_severities,
            "uptime_seconds": time.time() - self.start_time,
        }

    def get_recent_errors(self, count: int = 10) -> list[dict[str, Any]]:
        """Get recent errors."""
        return self.errors[-count:]


class ErrorMiddleware:
    """Middleware for catching and handling errors."""
    def __init__(self, tracker: RuntimeErrorTracker):
        self.tracker = tracker

    def catch_and_record(self, func, *args, **kwargs):
        """Catch and record errors from a function call."""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            self.tracker.record_error(e, "middleware", "medium", {"function": func.__name__})
            raise

    def with_error_handling(self, func, *args, **kwargs):
        """Wrap a function with error handling."""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            self.tracker.record_error(e, "middleware", "high", {"function": func.__name__})
            return None