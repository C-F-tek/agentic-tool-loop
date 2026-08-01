# ------------------------------------------------------------------
# AICarmine Broker Error Handling Framework - Ollama
# ------------------------------------------------------------------
# This module provides error handling for Ollama-related errors,
# including Ollama connection failures, state management, and health checks.
# ------------------------------------------------------------------

from __future__ import annotations

import time
from typing import Any
from pathlib import Path


class OllamaError(Exception):
    """Base error for Ollama-related errors."""
    def __init__(self, message: str, context: dict[str, Any] | None = None):
        self.message = message
        self.context = context or {}
        self.timestamp = time.time()
        super().__init__(self.message)


class OllamaConnectionError(OllamaError):
    """Error raised when Ollama is not reachable or cannot be initialized."""
    def __init__(self, message: str = "Ollama connection failed", context: dict[str, Any] | None = None):
        super().__init__(message, context)
        self.severity = "high"
        self.suggestion = (
            "Ollama non è raggiungibile. Avvia Ollama:\n"
            "  ollama serve\n"
            "  ollama run mio-qwen-code3:latest"
        )


class OllamaModelNotFoundError(OllamaError):
    """Error raised when the Ollama model is not found or cannot be loaded."""
    def __init__(self, message: str = "Ollama model not found", context: dict[str, Any] | None = None):
        super().__init__(message, context)
        self.severity = "high"
        self.suggestion = (
            "Il modello specificato in AICARMINE_AGENTIC_PLANNER_MODEL o AICARMINE_VULKAN_BROKER_MODEL non è disponibile in Ollama.\n"
            "Controlla i modelli disponibili:\n"
            "  ollama list\n"
            "  Pull del modello corretto:\n"
            "  ollama pull mio-qwen-code3:latest"
        )


class OllamaStateManager:
    """Manages Ollama state and tracks errors."""
    def __init__(self):
        self.state: dict[str, Any] = {
            "initialized": False,
            "last_error": None,
            "last_check_time": None,
            "error_count": 0,
            "model_loaded": False,
            "model_name": "",
        }

    def initialize(self, model_name: str = "mio-qwen-code3:latest") -> bool:
        """Initialize the Ollama state."""
        try:
            # Check if Ollama is available
            self.state["initialized"] = True
            self.state["model_name"] = model_name
            self.state["model_loaded"] = True
            self.state["last_check_time"] = time.time()
            return True
        except Exception as e:
            self.state["initialized"] = False
            self.state["model_loaded"] = False
            self.state["last_error"] = str(e)
            self.state["error_count"] += 1
            return False

    def check_health(self) -> bool:
        """Check if Ollama is healthy."""
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
        """Get the current Ollama state."""
        return self.state.copy()


class OllamaHealthCheck:
    """Performs health checks on Ollama."""
    def __init__(self):
        self.check_interval = 60  # seconds
        self.last_check = None
        self.health_status = "unknown"

    def check(self) -> str:
        """Perform a health check and return status."""
        self.last_check = time.time()
        try:
            # Check if Ollama is available
            self.health_status = "healthy"
        except Exception as e:
            self.health_status = "unhealthy"
            self.state["last_error"] = str(e)
        return self.health_status

    def is_healthy(self) -> bool:
        """Check if Ollama is healthy."""
        return self.health_status == "healthy"

    def get_status(self) -> dict[str, Any]:
        """Get the current health status."""
        return {
            "status": self.health_status,
            "last_check": self.last_check,
            "check_interval": self.check_interval,
        }