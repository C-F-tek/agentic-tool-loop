# ------------------------------------------------------------------
# AICarmine Broker Error Handling Framework - Display
# ------------------------------------------------------------------
# This module provides user-friendly error display formatting for the
# broker error handling framework.
# ------------------------------------------------------------------

from __future__ import annotations

import json
import time
from typing import Any
from pathlib import Path


class ErrorDisplayFormatter:
    """Formatter for error display."""
    def __init__(self):
        self.formatters: dict[str, Any] = {}

    def register_formatter(self, error_type: str, formatter):
        """Register a formatter for an error type."""
        self.formatters[error_type] = formatter

    def format_error(self, error: Exception, format_type: str = "user_friendly") -> str:
        """Format an error for display."""
        formatter = self.formatters.get(format_type)
        if formatter:
            return formatter(error)
        return str(error)


class UserFriendlyErrorDisplay:
    """Display errors in a user-friendly format."""
    def __init__(self):
        self.formatter = ErrorDisplayFormatter()
        self.formatter.register_formatter("user_friendly", self._user_friendly_formatter)

    def _user_friendly_formatter(self, error: Exception) -> str:
        """Format an error in a user-friendly way."""
        error_type = type(error).__name__
        error_message = str(error)

        # Map common error types to user-friendly messages
        friendly_messages = {
            "PreplannerNotFoundError": "Il preplanner non è stato trovato. Questo potrebbe essere dovuto a:\n1. Ollama non è rispondente\n2. Il modello non è caricato\n3. L'indice RAG è vuoto\nControlla l'indice RAG e assicurati che abbia voci.",
            "PlannerNotFoundError": "Il planner non è stato trovato. Questo potrebbe essere dovuto a:\n1. Ollama non è rispondente\n2. Il modello non è caricato\n3. Il prompt è troppo grande\nControlla i log di Ollama e assicurati che il modello sia caricato.",
            "OllamaConnectionError": "Ollama non è raggiungibile. Avvia Ollama:\n  ollama serve\n  ollama run mio-qwen-code3:latest",
            "DatabaseError": "Il database SQLite è bloccato o corrotto. Controlla il database:\n  sqlite3 C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\\agent-jobs\\agent_jobs.sqlite3\n  .tables\n  Se corrotto, ripristina da backup.",
            "ValidationError": "La decisione del planner è stata rifiutata dal validator. Questo potrebbe essere dovuto a:\n1. La decisione non corrisponde all'evidenza\n2. Lo strumento non è permesso\n3. I parametri non sono validi\nControlla i log del validator e regola il prompt del planner.",
            "ConfigurationError": "La configurazione non è valida. Controlla le variabili d'ambiente:\n  $env:AICARMINE_LAB_REPO = \"C:\\Users\\sanit\\AI\\lab-worktrees\\blender-audio-project-lab\"\n  $env:AICARMINE_VULKAN_WORKSPACE = \"C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\"\n  $env:AICARMINE_AGENT_JOB_ROOT = \"C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\\agent-jobs\"\n  $env:AICARMINE_AGENT_JOB_DB = \"C:\\Users\\sanit\\AI\\qwen-agent-workspace\\vulkan-broker\\agent-jobs\\agent_jobs.sqlite3\"\n  $env:AICARMINE_AGENTIC_PLANNER_MODEL = \"mio-qwen-code3:latest\"\n  $env:AICARMINE_AGENTIC_PLANNER_NUM_CTX = \"262144\"",
            "RuntimeError": "Errore runtime. Questo potrebbe essere dovuto a:\n1. Il codice Python non è valido\n2. Una dipendenza manca\n3. Un file non esiste\nControlla il traceback per il file e il numero di riga.",
            "RegressionError": "Regressione rilevata. Questo potrebbe essere dovuto a:\n1. Un cambiamento nel codice ha rotto la funzionalità\n2. Una dipendenza è stata aggiornata\n3. Un file è stato modificato\nControlla il git diff e ripristina il codice precedente.",
        }

        # Try to find a matching friendly message
        for error_key, friendly_msg in friendly_messages.items():
            if error_key in error_type:
                return friendly_msg

        # Default: return a generic user-friendly message
        return f"Errore: {error_type}\n{error_message}\n\nSuggerimento: Controlla i log del broker per maggiori dettagli."

    def display_error(self, error: Exception) -> str:
        """Display an error in a user-friendly way."""
        return self._user_friendly_formatter(error)


class TerminalErrorDisplay:
    """Display errors in a terminal-friendly format."""
    def __init__(self):
        self.colors = {
            "CRITICAL": "\033[91m",  # Red
            "HIGH": "\033[93m",      # Yellow
            "MEDIUM": "\033[33m",    # Orange
            "LOW": "\033[36m",       # Cyan
            "RESET": "\033[0m",      # Reset
        }

    def format_error(self, error: Exception, severity: str = "MEDIUM") -> str:
        """Format an error for terminal display."""
        color = self.colors.get(severity, "")
        reset = self.colors.get("RESET", "")

        return (
            f"{color}[{severity}] {type(error).__name__}: {str(error)}{reset}"
        )

    def display_error(self, error: Exception, severity: str = "MEDIUM") -> str:
        """Display an error in the terminal."""
        return self.format_error(error, severity)


class JSONErrorDisplay:
    """Display errors in JSON format."""
    def __init__(self):
        pass

    def format_error(self, error: Exception) -> str:
        """Format an error in JSON format."""
        error_data = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "timestamp": time.time(),
        }
        return json.dumps(error_data, indent=2)

    def display_error(self, error: Exception) -> str:
        """Display an error in JSON format."""
        return self.format_error(error)