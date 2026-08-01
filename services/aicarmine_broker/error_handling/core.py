# ------------------------------------------------------------------
# AICarmine Broker Error Handling Framework - Core
# ------------------------------------------------------------------
# This module provides the core error classes and utilities for the
# broker error handling framework.
# ------------------------------------------------------------------

from __future__ import annotations

import time
from enum import Enum
from typing import Any
from pathlib import Path


class ErrorSeverity(Enum):
    """Error severity levels."""
    CRITICAL = "critical"  # System is broken, immediate action required
    HIGH = "high"          # Major functionality broken
    MEDIUM = "medium"      # Minor functionality broken
    LOW = "low"            # Minor issue, non-blocking


class ErrorCategory(Enum):
    """Error categories for grouping errors."""
    CONFIGURATION = "configuration"
    NETWORK = "network"
    DATABASE = "database"
    MODEL = "model"
    PLANNER = "planner"
    PREPLANNER = "preplanner"
    VALIDATOR = "validator"
    EVIDENCE = "evidence"
    TOOLS = "tools"
    OLLAMA = "ollama"
    RERANKER = "reranker"
    WEBUI = "webui"
    JOB = "job"
    REGRESSION = "regression"
    RUNTIME = "runtime"


class BrokerError(Exception):
    """Base error class for all broker errors."""
    def __init__(self, message: str, context: dict[str, Any] | None = None):
        self.message = message
        self.context = context or {}
        self.timestamp = time.time()
        self.category = ErrorCategory.RUNTIME
        self.severity = ErrorSeverity.MEDIUM
        super().__init__(self.message)


class PlannerError(BrokerError):
    """Error class for planner-related errors."""
    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message, context)
        self.category = ErrorCategory.PLANNER


class PreplannerError(BrokerError):
    """Error class for preplanner-related errors."""
    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message, context)
        self.category = ErrorCategory.PREPLANNER


class ValidatorError(BrokerError):
    """Error class for validator-related errors."""
    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message, context)
        self.category = ErrorCategory.VALIDATOR


class OllamaError(BrokerError):
    """Error class for Ollama-related errors."""
    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message, context)
        self.category = ErrorCategory.OLLAMA


class RerankerError(BrokerError):
    """Error class for reranker-related errors."""
    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message, context)
        self.category = ErrorCategory.RERANKER


class DatabaseError(BrokerError):
    """Error class for database-related errors."""
    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message, context)
        self.category = ErrorCategory.DATABASE


class ValidationError(BrokerError):
    """Error class for validation-related errors."""
    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message, context)
        self.category = ErrorCategory.VALIDATOR


class ConfigurationError(BrokerError):
    """Error class for configuration-related errors."""
    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message, context)
        self.category = ErrorCategory.CONFIGURATION


class RuntimeError(BrokerError):
    """Error class for runtime-related errors."""
    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message, context)
        self.category = ErrorCategory.RUNTIME


class RegressionError(BrokerError):
    """Error class for regression-related errors (code changes that broke functionality)."""
    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message, context)
        self.category = ErrorCategory.REGRESSION


class ErrorReport:
    """Error report containing error details and context."""
    def __init__(self, error: BrokerError, traceback: str = ""):
        self.error = error
        self.traceback = traceback
        self.timestamp = time.time()
        self.report_id = f"ERR-{int(self.timestamp)}"

    def to_dict(self) -> dict[str, Any]:
        """Convert error report to dictionary."""
        return {
            "report_id": self.report_id,
            "timestamp": self.timestamp,
            "error_type": type(self.error).__name__,
            "error_message": str(self.error),
            "error_category": self.error.category.value,
            "error_severity": self.error.severity.value,
            "error_context": self.error.context,
            "traceback": self.traceback,
        }


class ErrorSummary:
    """Summary of errors for display."""
    def __init__(self):
        self.errors: list[ErrorReport] = []
        self.critical_count = 0
        self.high_count = 0
        self.medium_count = 0
        self.low_count = 0

    def add_error(self, report: ErrorReport):
        """Add an error report to the summary."""
        self.errors.append(report)
        if report.error.severity == ErrorSeverity.CRITICAL:
            self.critical_count += 1
        elif report.error.severity == ErrorSeverity.HIGH:
            self.high_count += 1
        elif report.error.severity == ErrorSeverity.MEDIUM:
            self.medium_count += 1
        else:
            self.low_count += 1

    def to_dict(self) -> dict[str, Any]:
        """Convert error summary to dictionary."""
        return {
            "total_errors": len(self.errors),
            "critical": self.critical_count,
            "high": self.high_count,
            "medium": self.medium_count,
            "low": self.low_count,
            "errors": [report.to_dict() for report in self.errors],
        }


class ErrorRegistry:
    """Registry for error classes and their handlers."""
    def __init__(self):
        self.handlers: dict[str, Any] = {}

    def register(self, error_class: type[BrokerError], handler: Any):
        """Register a handler for an error class."""
        self.handlers[error_class.__name__] = handler

    def get_handler(self, error_class: type[BrokerError]) -> Any:
        """Get the handler for an error class."""
        return self.handlers.get(error_class.__name__)

    def handle_error(self, error: BrokerError) -> str:
        """Handle an error using the registered handler."""
        handler = self.get_handler(type(error))
        if handler:
            return handler(error)
        return f"Unknown error: {error.message}"