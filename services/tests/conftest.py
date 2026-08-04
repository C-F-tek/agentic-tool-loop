"""Shared pytest configuration and fixtures for aicarmine-broker tests."""

from __future__ import annotations

import json
import socket
import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import httpx


# ---------------------------------------------------------------------------
# Path fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def project_root() -> Path:
    """Return the services/ directory path."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture()
def broker_root(project_root: Path) -> Path:
    """Return the aicarmine_broker/ directory path."""
    return project_root / "aicarmine_broker"


@pytest.fixture()
def codex_bridge_root(project_root: Path) -> Path:
    """Return the codex_bridge/ directory path."""
    return project_root / "codex_bridge"


# ---------------------------------------------------------------------------
# Mock HTTP server fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_http_server() -> tuple[threading.Thread, list[str], Path]:
    """Start a local HTTP server that returns JSON responses.
    
    Returns a tuple of (thread, request_log, temp_dir).
    The thread must be joined after use.
    """
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    request_log: list[str] = []
    
    def _handler(request):
        request_log.append(str(request.path))
        return httpx.Response(200, json.dumps({"ok": True, "echo": "mock"}))
    
    app = httpx.MockTransport(_handler)
    server = threading.Thread(target=lambda: None)
    # Use MockTransport instead of real server for simplicity
    return server, request_log, tmp


# ---------------------------------------------------------------------------
# Mock external services
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_ollama_url() -> str:
    """Return a mock Ollama URL for testing."""
    return "http://127.0.0.1:11434/api/generate"


@pytest.fixture()
def mock_broker_url() -> str:
    """Return a mock broker URL for testing."""
    return "http://127.0.0.1:3572/vulkan/agent"


@pytest.fixture()
def mock_reranker_url() -> str:
    """Return a mock reranker URL for testing."""
    return "http://127.0.0.1:3550/v3/rerank"


# ---------------------------------------------------------------------------
# Helper fixtures for patching
# ---------------------------------------------------------------------------

@pytest.fixture()
def patch_httpx_post():
    """Create a fixture that patches httpx.post calls.
    
    Usage:
        def test_something(patch_httpx_post):
            with patch_httpx_post({"ok": True}) as mock:
                result = json_io.post_json(url, payload)
                mock.assert_called_once()
    """
    from unittest.mock import AsyncMock, MagicMock
    
    def _factory(response_data: dict[str, Any]) -> MagicMock:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps(response_data)
        mock_response.__iter__ = lambda self: iter([])
        
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        
        return mock_client
    
    return _factory


@pytest.fixture()
def patch_httpx_get():
    """Create a fixture that patches httpx.get calls."""
    from unittest.mock import MagicMock
    
    def _factory(response_data: dict[str, Any]) -> MagicMock:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps(response_data)
        
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        
        return mock_client


# ---------------------------------------------------------------------------
# Test utilities
# ---------------------------------------------------------------------------

class MockResponse:
    """Minimal mock for httpx response objects."""
    
    def __init__(self, status_code: int = 200, text: str = "{}", json_data: dict | None = None):
        self.status_code = status_code
        self.text = text
        self.json_data = json_data or json.loads(text)
        self.url = "http://test.example.com"
    
    def json(self) -> dict:
        return self.json_data
    
    def readline(self) -> str:
        return ""
    
    def close(self) -> None:
        pass


class StreamMockResponse:
    """Mock for streaming HTTP responses (SSE)."""
    
    def __init__(self, lines: list[str], done: bool = True):
        self._lines = lines
        self._index = 0
        self.done = done
    
    def __iter__(self):
        return self
    
    def __next__(self) -> str:
        if self._index >= len(self._lines):
            if self.done:
                raise StopIteration()
            raise TimeoutError("Stream timeout")
        line = self._lines[self._index]
        self._index += 1
        return line
    
    def close(self) -> None:
        pass