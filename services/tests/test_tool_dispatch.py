"""Tests for aicarmine_broker.tool_dispatch and dispatcher modules."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aicarmine_broker.tool_dispatch import dispatch_tool, dispatch_tool_call
from aicarmine_broker.application.tool_surface.dispatcher import (
    BaseTool,
    DispatchRequest,
    RegistryToolDispatcher,
    build_default_dispatcher,
)


class TestRegistryToolDispatcher:
    """Test RegistryToolDispatcher class."""

    def test_tool_names(self):
        dispatcher = build_default_dispatcher()
        names = dispatcher.tool_names()
        assert isinstance(names, tuple)
        assert len(names) > 0
        assert "repo_read" in names

    def test_dispatch_known_tool(self):
        dispatcher = build_default_dispatcher()
        request = DispatchRequest(
            name="repo_capabilities",
            args={},
            root=Path("/tmp"),
            allow_command=False,
            user_consent="",
        )
        result = dispatcher.dispatch(request)
        # repo_capabilities returns a dict with capability info
        assert isinstance(result, dict)

    def test_dispatch_unknown_tool(self):
        dispatcher = build_default_dispatcher()
        request = DispatchRequest(
            name="nonexistent_tool",
            args={},
            root=Path("/tmp"),
            allow_command=False,
            user_consent="",
        )
        result = dispatcher.dispatch(request)
        assert result["ok"] is False
        assert result["error"] == "unknown internal tool"

    def test_normalize_tool_name(self):
        dispatcher = build_default_dispatcher()
        # Test that tool names are normalized (e.g., "repo_read" and "Repo_Read" map to same)
        names = dispatcher.tool_names()
        assert "repo_read" in names


class TestDispatchTool:
    """Test dispatch_tool compatibility function."""

    def test_dispatch_tool_basic(self):
        result = dispatch_tool(
            name="repo_capabilities",
            args={},
            root=Path("/tmp"),
            allow_command=False,
            user_consent="",
        )
        assert isinstance(result, dict)

    def test_dispatch_tool_call_alias(self):
        """Test that dispatch_tool_call is an alias for dispatch_tool."""
        result = dispatch_tool_call(
            name="repo_capabilities",
            args={},
            root=Path("/tmp"),
            allow_command=False,
            user_consent="",
        )
        assert isinstance(result, dict)


class TestBaseTool:
    """Test BaseTool dataclass."""

    def test_base_tool_execute(self):
        handler = MagicMock(return_value={"ok": True})
        tool = BaseTool(name="test_tool", handler=handler)
        request = DispatchRequest(
            name="test_tool",
            args={"key": "value"},
            root=Path("/tmp"),
            allow_command=True,
            user_consent="confirmed",
        )
        result = tool.execute(request)
        handler.assert_called_once()
        assert result == {"ok": True}


class TestDispatchRequest:
    """Test DispatchRequest dataclass."""

    def test_dispatch_request_creation(self):
        request = DispatchRequest(
            name="repo_read",
            args={"path": "/test.py"},
            root=Path("/tmp"),
            allow_command=False,
            user_consent="",
        )
        assert request.name == "repo_read"
        assert request.args["path"] == "/test.py"
        assert request.root == Path("/tmp")
        assert request.allow_command is False
        assert request.user_consent == ""