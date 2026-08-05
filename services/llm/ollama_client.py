"""
services.llm.ollama_client - Ollama HTTP client wrapper.

This module provides OllamaClient for all HTTP communication with Ollama endpoints.
It ensures response is always initialized to prevent UnboundLocalError.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)


class OllamaClient:
    """Handles all HTTP communication with Ollama endpoints.
    
    Centralizes HTTP calls to Ollama API with proper error handling
    and response initialization to prevent UnboundLocalError.
    """
    
    def __init__(self, url: str = "http://127.0.0.1:11434/api/chat", model: str = "qwen3coder:latest"):
        """Initialize OllamaClient with URL and model.
        
        Args:
            url: Ollama API endpoint URL
            model: Default model to use for requests
        """
        self.url = url
        self.model = model
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def chat(self, payload: dict) -> dict:
        """Raw chat call to Ollama, with response always initialized.
        
        Args:
            payload: Chat request payload
            
        Returns:
            Response dict, or empty response on failure
        """
        response = None  # Always initialize to prevent UnboundLocalError
        try:
            response = self._call_ollama(payload)
        except Exception as e:
            logger.error(f"Ollama chat failed: {e}")
            logger.debug(f"Failed payload: {payload.get('messages', [])[:1]}...")
        
        if response is None:
            return self._empty_response()
        return response
    
    def chat_with_tools(self, payload: dict) -> dict:
        """Chat with native tool calling enabled.
        
        Args:
            payload: Chat request payload with tools
            
        Returns:
            Response dict, or empty response on failure
        """
        payload["stream"] = False
        response = None
        try:
            response = self._call_ollama(payload)
        except Exception as e:
            logger.error(f"Ollama chat_with_tools failed: {e}")
        
        if response is None:
            return self._empty_response()
        return response
    
    def chat_json_text(self, payload: dict) -> dict:
        """Chat without tools, expects JSON as text response.
        
        Args:
            payload: Chat request payload
            
        Returns:
            Response dict, or empty response on failure
        """
        payload["stream"] = False
        response = None
        try:
            response = self._call_ollama(payload)
        except Exception as e:
            logger.error(f"Ollama chat_json_text failed: {e}")
        
        if response is None:
            return self._empty_response()
        return response
    
    def _call_ollama(self, payload: dict) -> dict:
        """Make raw HTTP call to Ollama API.
        
        Args:
            payload: Request payload
            
        Returns:
            Response dict from Ollama API
            
        Raises:
            requests.RequestException: If HTTP call fails
        """
        # Ensure model is set
        if "model" not in payload:
            payload["model"] = self.model
        
        logger.debug(f"Calling Ollama at {self.url} with model={payload['model']}")
        
        response = self.session.post(
            self.url,
            json=payload,
            timeout=3600,  # Long timeout for large responses
        )
        response.raise_for_status()
        
        result = response.json()
        logger.debug(f"Ollama response received: {type(result).__name__}")
        return result
    
    def _empty_response(self) -> dict:
        """Return empty/default response structure.
        
        Returns:
            Empty response dict
        """
        return {
            "message": {
                "role": "assistant",
                "content": "",
            },
            "model": self.model,
            "done": True,
        }
    
    def health_check(self) -> bool:
        """Check if Ollama service is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            response = self.session.get(
                "http://127.0.0.1:11434/api/tags",
                timeout=5,
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            return False