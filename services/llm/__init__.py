"""
services.llm - LLM client modules for Ollama communication.

This module provides:
- OllamaClient: HTTP client wrapper for Ollama API calls
- FallbackHandler: Centralized retry and fallback logic
"""
from __future__ import annotations

from .ollama_client import OllamaClient
from .fallback import FallbackHandler

__all__ = [
    "OllamaClient",
    "FallbackHandler",
]