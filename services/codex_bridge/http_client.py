"""HTTP client utilities for agentic loop MCP server.

This module extracts common HTTP operations from agentic_loop_client_mcp_server.py
into a reusable, testable HTTP client layer.
"""

from __future__ import annotations

import json
import socket
import time
from typing import Any

import httpx
import urllib.error


class HttpClientError(Exception):
    """Base exception for HTTP client errors."""
    pass


class HttpTimeoutError(HttpClientError):
    """Exception raised when HTTP request times out."""
    pass


class HttpUnreachableError(HttpClientError):
    """Exception raised when HTTP backend is unreachable."""
    pass


class AgenticLoopHttpClient:
    """HTTP client for agentic loop broker and reranker communication.
    
    Provides bounded, validated HTTP operations with structured error responses.
    """
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
    
    def post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Post JSON to URL with timeout handling.
        
        Returns structured dict with ok field indicating success/failure.
        """
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            response = httpx.post(url, data=data, headers={"Content-Type": "application/json"}, timeout=self.timeout)
            raw = response.text
        except (socket.timeout, TimeoutError) as exc:
            return {
                "ok": False,
                "backend_timeout": True,
                "backend_unreachable": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "timeout_seconds": self.timeout,
            }
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", None)
            reason_text = str(reason or exc)
            is_timeout = isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in reason_text.lower()
            return {
                "ok": False,
                "backend_timeout": is_timeout,
                "backend_unreachable": not is_timeout,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "network_reason_type": type(reason).__name__ if reason is not None else None,
                "timeout_seconds": self.timeout,
            }
        except OSError as exc:
            is_timeout = "timed out" in str(exc).lower()
            return {
                "ok": False,
                "backend_timeout": is_timeout,
                "backend_unreachable": not is_timeout,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "timeout_seconds": self.timeout,
            }
        try:
            decoded = json.loads(raw)
            return decoded if isinstance(decoded, dict) else {"ok": True, "data": decoded}
        except Exception as exc:
            return {"ok": False, "error_type": type(exc).__name__,
                    "error": str(exc), "raw": raw[:4000]}
    
    def get_health(self, endpoint: str) -> dict[str, Any]:
        """GET health check endpoint.
        
        Returns structured dict with ok field.
        """
        return self._http_json(method="GET", url=endpoint)
    
    def _http_json(self, method: str, url: str) -> dict[str, Any]:
        """Internal HTTP JSON request handler."""
        body = None
        headers = {"User-Agent": "agentic-loop-client", "Accept": "application/json"}
        request = httpx.Client(timeout=30).post(url, data=body, headers=headers, method=method)
        try:
            with httpx.Client(timeout=30).get(request, timeout=self.timeout) as response:
                raw = response.read()
                text = raw.decode("utf-8", errors="replace")
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = {"_raw_text": text}
                return {
                    "ok": True,
                    "http_status": response.status,
                    "url": url,
                    "payload": parsed,
                }
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            text = raw.decode("utf-8", errors="replace")
            return {
                "ok": False,
                "error": "http_error",
                "http_status": exc.code,
                "url": url,
                "body": text[:4000],
            }
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            return {
                "ok": False,
                "error": "request_failed",
                "url": url,
                "error_type": type(exc).__name__,
                "message": str(exc)[:2000],
            }