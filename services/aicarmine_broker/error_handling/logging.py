# ------------------------------------------------------------------
# AICarmine Broker Error Handling Framework - Logging
# ------------------------------------------------------------------
# This module provides comprehensive error logging to ensure errors
# are NOT silently swallowed. All errors must be logged before
# being handled or re-raised.
# ------------------------------------------------------------------

from __future__ import annotations

import os
import sys
import time
import json
from typing import Any
from pathlib import Path
from datetime import datetime


class ErrorLogger:
    """Comprehensive error logger that ensures errors are never silently swallowed."""
    
    def __init__(self, log_dir: str = "services/aicarmine_broker/logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self.error_count = 0
    
    def log_error(self, error: Exception, context: dict[str, Any] | None = None, 
                  severity: str = "high", component: str = "unknown") -> str:
        """
        Log an error with full details. This method NEVER silently swallows errors.
        
        Args:
            error: The exception that occurred
            context: Additional context about what was happening
            severity: Error severity (critical, high, medium, low)
            component: Which component failed (planner, reranker, ollama, etc.)
        
        Returns:
            The log file path where the error was written
        """
        timestamp = datetime.now().isoformat()
        error_entry = {
            "timestamp": timestamp,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "severity": severity,
            "component": component,
            "context": context or {},
            "traceback": self._extract_traceback(error),
            "error_count": self.error_count + 1,
        }
        
        # Write to log file
        log_entry = json.dumps(error_entry, default=str, ensure_ascii=False, indent=2)
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"[{timestamp}] ERROR #{error_entry['error_count']} - {component}\n")
                f.write(f"{'='*80}\n")
                f.write(log_entry + "\n")
        except Exception as write_error:
            # If we can't write to file, print to stderr
            print(f"ERROR: Failed to write to log file: {write_error}", file=sys.stderr)
            print(f"ERROR: {error_entry}", file=sys.stderr)
        
        # Always print to stderr to ensure the error is visible
        print(f"\n[ERROR] [{severity.upper()}] Component: {component}", file=sys.stderr)
        print(f"[ERROR] Type: {error_entry['error_type']}", file=sys.stderr)
        print(f"[ERROR] Message: {error_entry['error_message']}", file=sys.stderr)
        if context:
            print(f"[ERROR] Context: {context}", file=sys.stderr)
        
        self.error_count += 1
        return str(self.log_file)
    
    def _extract_traceback(self, error: Exception) -> str:
        """Extract traceback information from an exception."""
        import traceback
        try:
            return "".join(traceback.format_stack())
        except Exception as exc:
            return "Traceback unavailable"


class SilentErrorGuard:
    """
    Guard against silent errors. This decorator/context manager ensures
    that errors are never silently swallowed.
    """
    
    def __init__(self, component: str = "unknown"):
        self.component = component
        self.logger = ErrorLogger()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # NEVER silently swallow errors
            self.logger.log_error(
                exc_val,
                context={"component": self.component},
                severity="high",
                component=self.component
            )
            # Re-raise the error
            raise exc_val
        return True


def ensure_error_not_silent(func):
    """
    Decorator that ensures errors from the decorated function are never silently swallowed.
    All errors will be logged and re-raised.
    """
    from functools import wraps
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger = ErrorLogger()
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Log the error with full details
            logger.log_error(
                e,
                context={"function": func.__name__, "args": str(args), "kwargs": str(kwargs)},
                severity="high",
                component=func.__module__
            )
            # Re-raise the error - NEVER silently swallow
            raise
    
    return wrapper


# Global error logger instance
_global_logger = ErrorLogger()


def get_global_logger() -> ErrorLogger:
    """Get the global error logger instance."""
    return _global_logger


def log_critical_error(error: Exception, message: str = "") -> None:
    """
    Log a critical error. This is the simplest way to ensure errors are never silently swallowed.
    
    Usage:
        try:
            do_something()
        except Exception as e:
            log_critical_error(e, "Something went wrong")
    """
    logger = get_global_logger()
    logger.log_error(
        error,
        context={"message": message},
        severity="critical",
        component="critical"
    )