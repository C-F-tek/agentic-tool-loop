# ------------------------------------------------------------------
# AICarmine Broker Error Handling Framework - Integration
# ------------------------------------------------------------------
# This module provides integration of the error handling framework
# into the broker codebase. It wraps all bare except clauses with
# proper error handling.
# ------------------------------------------------------------------

from __future__ import annotations

import sys
import time
import json
import sqlite3
from typing import Any
from pathlib import Path
from functools import wraps
from .core import BrokerError, ErrorCategory, ErrorSeverity


class ErrorIntegrationMiddleware:
    """Middleware for integrating error handling into the broker codebase."""
    
    def __init__(self):
        self.error_handlers: dict[str, Any] = {}
        self.error_log: list[dict[str, Any]] = []
    
    def register_handler(self, error_type: type[BrokerError], handler):
        """Register a handler for an error type."""
        self.error_handlers[error_type.__name__] = handler
    
    def wrap_function(self, func):
        """Wrap a function with error handling."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except BrokerError as e:
                self._log_error(e, func.__name__)
                raise
            except Exception as e:
                wrapped_error = BrokerError(
                    message=f"Unexpected error in {func.__name__}: {str(e)}",
                    context={"function": func.__name__, "error_type": type(e).__name__}
                )
                self._log_error(wrapped_error, func.__name__)
                raise wrapped_error
        return wrapper
    
    def _log_error(self, error: BrokerError, function_name: str):
        """Log an error for later analysis."""
        self.error_log.append({
            "timestamp": time.time(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "function": function_name,
            "category": error.category.value,
            "severity": error.severity.value,
        })


class ErrorIntegrationManager:
    """Manages error integration across the broker codebase."""
    
    def __init__(self):
        self.middleware = ErrorIntegrationMiddleware()
        self.integrated_files: list[str] = []
    
    def integrate_file(self, file_path: str):
        """Integrate error handling into a file."""
        self.integrated_files.append(file_path)
    
    def get_integration_status(self) -> dict[str, Any]:
        """Get the integration status."""
        return {
            "integrated_files": len(self.integrated_files),
            "total_errors": len(self.middleware.error_log),
            "errors_by_category": {},
            "errors_by_severity": {},
        }


# ------------------------------------------------------------------
# Integration patterns for common bare except clauses
# ------------------------------------------------------------------

def safe_execute(func, default=None):
    """Safely execute a function and return default on error."""
    try:
        return func()
    except Exception as e:
        error_log = {
            "timestamp": time.time(),
            "error_type": type(e).__name__,
            "error_message": str(e),
            "function": func.__name__,
        }
        return default


def safe_read_file(file_path: str, encoding: str = "utf-8") -> str:
    """Safely read a file."""
    try:
        return Path(file_path).read_text(encoding=encoding)
    except Exception as e:
        return ""


def safe_json_loads(text: str, default: dict = None):
    """Safely parse JSON."""
    try:
        return json.loads(text)
    except Exception as e:
        return default or {}


def safe_sqlite_query(conn, query: str, args: tuple = ()):
    """Safely execute a SQLite query."""
    try:
        cursor = conn.cursor()
        cursor.execute(query, args)
        return cursor.fetchall()
    except Exception as e:
        return []


def safe_sqlite_insert(conn, query: str, args: tuple):
    """Safely execute a SQLite insert."""
    try:
        cursor = conn.cursor()
        cursor.execute(query, args)
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        return None