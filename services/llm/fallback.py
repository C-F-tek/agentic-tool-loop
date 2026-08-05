"""
services.llm.fallback - Centralized retry and fallback logic.

This module provides FallbackHandler for centralized retry/fallback logic
when calling Ollama API. It replaces scattered retry logic across multiple files.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from .ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class FallbackHandler:
    """Centralized retry and fallback logic for Ollama calls.
    
    Implements the strategy: try native tools → JSON-text → retry ×3 → block.
    """
    
    def __init__(self, client: OllamaClient, native_tools: bool = False, max_retries: int = 3):
        """Initialize FallbackHandler.
        
        Args:
            client: OllamaClient instance
            native_tools: Whether to try native tool calling first
            max_retries: Maximum number of retry attempts
        """
        self.client = client
        self.native_tools = native_tools
        self.max_retries = max_retries
    
    def try_with_fallback(self, payload: dict) -> dict:
        """Try with fallback strategy.
        
        Attempts native tools first (if enabled), then JSON-text mode,
        with retries up to max_retries times. Returns blocked response on failure.
        
        Args:
            payload: Chat request payload
            
        Returns:
            Response dict from successful attempt, or blocked response
        """
        for attempt in range(self.max_retries):
            logger.debug(f"Fallback attempt {attempt + 1}/{self.max_retries}")
            
            # Try native tools first if enabled
            if self.native_tools and attempt == 0:
                result = self._try_native_tools(payload)
                if result:
                    return result
            
            # Try JSON-text mode
            result = self._try_json_text(payload)
            if result:
                return result
            
            logger.warning(f"Fallback attempt {attempt + 1} failed, retrying...")
        
        # All attempts failed - return blocked response
        logger.error("All fallback attempts failed, returning blocked response")
        return self._block_response()
    
    def _try_native_tools(self, payload: dict) -> dict | None:
        """Try calling Ollama with native tool calling.
        
        Args:
            payload: Chat request payload
            
        Returns:
            Response dict if successful, None otherwise
        """
        try:
            logger.debug("Trying native tool calling")
            result = self.client.chat_with_tools(payload)
            
            # Check if response contains useful content
            if self._has_useful_content(result):
                logger.debug("Native tool call succeeded with useful content")
                return result
            else:
                logger.debug("Native tool call returned empty/useless content")
                return None
        except Exception as e:
            logger.warning(f"Native tool call failed: {e}")
            return None
    
    def _try_json_text(self, payload: dict) -> dict | None:
        """Try calling Ollama without tools, expecting JSON as text.
        
        Args:
            payload: Chat request payload
            
        Returns:
            Response dict if successful, None otherwise
        """
        try:
            logger.debug("Trying JSON-text mode")
            result = self.client.chat_json_text(payload)
            
            # Check if response contains useful content
            if self._has_useful_content(result):
                logger.debug("JSON-text call succeeded with useful content")
                return result
            else:
                logger.debug("JSON-text call returned empty/useless content")
                return None
        except Exception as e:
            logger.warning(f"JSON-text call failed: {e}")
            return None
    
    def _has_useful_content(self, response: dict) -> bool:
        """Check if response contains useful content.
        
        Args:
            response: Response dict from Ollama
            
        Returns:
            True if response has useful content, False otherwise
        """
        if not response:
            return False
        
        message = response.get("message", {})
        content = message.get("content", "") or ""
        
        # Check for non-empty content
        if not content.strip():
            return False
        
        # Check for meaningful content (not just whitespace)
        if len(content.strip()) < 10:
            return False
        
        return True
    
    def _block_response(self) -> dict:
        """Return blocked response when all attempts fail.
        
        Returns:
            Blocked response dict
        """
        return {
            "message": {
                "role": "assistant",
                "content": "BLOCKED: All Ollama attempts failed.",
            },
            "model": self.client.model,
            "done": True,
            "blocked": True,
        }