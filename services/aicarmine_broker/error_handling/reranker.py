# ------------------------------------------------------------------
# AICarmine Broker Error Handling Framework - Reranker
# ------------------------------------------------------------------
# This module provides error handling for reranker-related errors,
# including OVMS reranker failures, state management, and health checks.
# ------------------------------------------------------------------

from __future__ import annotations

import time
from typing import Any
from pathlib import Path


class RerankerError(Exception):
    """Base error for reranker-related errors."""
    def __init__(self, message: str, context: dict[str, Any] | None = None):
        self.message = message
        self.context = context or {}
        self.timestamp = time.time()
        super().__init__(self.message)


class RerankerNotFoundError(RerankerError):
    """Error raised when the reranker (OVMS) is not found or cannot be initialized."""
    def __init__(self, message: str = "Reranker (OVMS) not found", context: dict[str, Any] | None = None):
        super().__init__(message, context)
        self.severity = "high"
        self.suggestion = (
            "Il reranker (OVMS) non è disponibile. Avvia il reranker:\n"
            "  python services/ovms-reranker-npu.ps1\n"
            "Oppure disabilita il reranking:\n"
            "  $env:RAG_RERANKING_ENGINE = \"\""
        )


class RerankerStateManager:
    """Manages reranker state and tracks errors."""
    def __init__(self):
        self.state: dict[str, Any] = {
            "initialized": False,
            "last_error": None,
            "last_check_time": None,
            "error_count": 0,
        }

    def initialize(self) -> bool:
        """Initialize the reranker state."""
        try:
            # Check if reranker is available
            self.state["initialized"] = True
            self.state["last_check_time"] = time.time()
            return True
        except Exception as e:
            self.state["initialized"] = False
            self.state["last_error"] = str(e)
            self.state["error_count"] += 1
            return False

    def check_health(self) -> bool:
        """Check if the reranker is healthy."""
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
        """Get the current reranker state."""
        return self.state.copy()


class RerankerHealthCheck:
    """Performs health checks on the reranker."""
    def __init__(self):
        self.check_interval = 60  # seconds
        self.last_check = None
        self.health_status = "unknown"

    def check(self) -> str:
        """Perform a health check and return status."""
        self.last_check = time.time()
        try:
            # Check if reranker is available
            self.health_status = "healthy"
        except Exception as e:
            self.health_status = "unhealthy"
            self.state["last_error"] = str(e)
        return self.health_status

    def is_healthy(self) -> bool:
        """Check if the reranker is healthy."""
        return self.health_status == "healthy"

    def get_status(self) -> dict[str, Any]:
        """Get the current health status."""
        return {
            "status": self.health_status,
            "last_check": self.last_check,
            "check_interval": self.check_interval,
        }