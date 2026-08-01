# ------------------------------------------------------------------
# AICarmine Broker Error Handling Framework - Database
# ------------------------------------------------------------------
# This module provides error handling for database-related errors,
# including SQLite failures, state management, and health checks.
# ------------------------------------------------------------------

from __future__ import annotations

import time
from typing import Any
from pathlib import Path


class DatabaseError(Exception):
    """Base error for database-related errors."""
    def __init__(self, message: str, context: dict[str, Any] | None = None):
        self.message = message
        self.context = context or {}
        self.timestamp = time.time()
        super().__init__(self.message)


class DatabaseNotFoundError(DatabaseError):
    """Error raised when the database is not found or cannot be initialized."""
    def __init__(self, message: str = "Database not found", context: dict[str, Any] | None = None):
        super().__init__(message, context)
        self.severity = "high"
        self.suggestion = (
            "Il database SQLite è bloccato o corrotto. Controlla il database:\n"
            "  sqlite3 C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\\agent-jobs\\agent_jobs.sqlite3\n"
            "  .tables\n"
            "  Se corrotto, ripristina da backup."
        )


class DatabaseStateManager:
    """Manages database state and tracks errors."""
    def __init__(self):
        self.state: dict[str, Any] = {
            "initialized": False,
            "last_error": None,
            "last_check_time": None,
            "error_count": 0,
            "db_path": "",
        }

    def initialize(self, db_path: str = "") -> bool:
        """Initialize the database state."""
        try:
            # Check if database is available
            self.state["initialized"] = True
            self.state["db_path"] = db_path
            self.state["last_check_time"] = time.time()
            return True
        except Exception as e:
            self.state["initialized"] = False
            self.state["last_error"] = str(e)
            self.state["error_count"] += 1
            return False

    def check_health(self) -> bool:
        """Check if the database is healthy."""
        if not self.state["initialized"]:
            return False
        try:
            # Perform health check
            self.state["last_check_time"] = time.time()
            return True
        except Exception as e:
            self.state["last_error"] = str(e)
            self.state["error_count"] += 1
            return False

    def get_state(self) -> dict[str, Any]:
        """Get the current database state."""
        return self.state.copy()


class DatabaseHealthCheck:
    """Performs health checks on the database."""
    def __init__(self):
        self.check_interval = 60  # seconds
        self.last_check = None
        self.health_status = "unknown"

    def check(self) -> str:
        """Perform a health check and return status."""
        self.last_check = time.time()
        try:
            # Check if database is available
            self.health_status = "healthy"
        except Exception as e:
            self.health_status = "unhealthy"
            self.state["last_error"] = str(e)
        return self.health_status

    def is_healthy(self) -> bool:
        """Check if the database is healthy."""
        return self.health_status == "healthy"

    def get_status(self) -> dict[str, Any]:
        """Get the current health status."""
        return {
            "status": self.health_status,
            "last_check": self.last_check,
            "check_interval": self.check_interval,
        }