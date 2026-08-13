"""Tests for RegistryToolDispatcher."""

import logging
from pathlib import Path

import pytest


def _get_module():
    """Import dispatcher.py properly using importlib."""
    import importlib.util
    import sys

    _app_dir = Path(__file__).resolve().parent
    _module_name = "dispatcher_test"
    _spec = importlib.util.spec_from_file_location(
        _module_name, _app_dir / ".." / "dispatcher.py"
    )
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_module_name] = _module
    _spec.loader.exec_module(_module)
    return _module


_m = _get_module()
RegistryToolDispatcher = _m.RegistryToolDispatcher


class TestRegistryToolDispatcherInit:
    """Tests for __init__."""

    def test_empty_registry(self):
        dispatcher = RegistryToolDispatcher()
        assert dispatcher._tools == {}

    def test_registry_is_dict(self):
        dispatcher = RegistryToolDispatcher()
        assert isinstance(dispatcher._tools, dict)


class TestRegister:
    """Tests for register method."""

    def test_register_basic(self):
        dispatcher = RegistryToolDispatcher()
        handler = lambda args, **kwargs: {"result": "ok"}
        dispatcher.register("read_file", handler)
        assert "read_file" in dispatcher._tools

    def test_register_lowercase(self):
        dispatcher = RegistryToolDispatcher()
        handler = lambda args, **kwargs: {"result": "ok"}
        dispatcher.register("ReadFile", handler)
        assert "readfile" in dispatcher._tools
        assert "ReadFile" not in dispatcher._tools

    def test_register_strips_whitespace(self):
        dispatcher = RegistryToolDispatcher()
        handler = lambda args, **kwargs: {"result": "ok"}
        dispatcher.register("  read_file  ", handler)
        assert "read_file" in dispatcher._tools

    def test_register_overwrites(self):
        dispatcher = RegistryToolDispatcher()
        handler1 = lambda args, **kwargs: {"result": "first"}
        handler2 = lambda args, **kwargs: {"result": "second"}
        dispatcher.register("test", handler1)
        dispatcher.register("test", handler2)
        assert dispatcher._tools["test"] == handler2

    def test_logger_called(self, caplog):
        dispatcher = RegistryToolDispatcher()
        handler = lambda args, **kwargs: None
        with caplog.at_level(logging.INFO):
            dispatcher.register("test_tool", handler)
        assert "Registered tool: test_tool" in caplog.text


class TestDispatch:
    """Tests for dispatch method."""

    def test_dispatch_known_tool(self):
        dispatcher = RegistryToolDispatcher()
        handler = lambda args, **kwargs: {"ok": True, "data": "result"}
        dispatcher.register("read_file", handler)
        result = dispatcher.dispatch("read_file", {})
        assert result == {"ok": True, "data": "result"}

    def test_dispatch_unknown_tool(self):
        dispatcher = RegistryToolDispatcher()
        result = dispatcher.dispatch("unknown_tool", {})
        assert result["ok"] is False
        assert result["tool"] == "unknown_tool"
        assert result["error"] == "unknown internal tool"

    def test_dispatch_case_insensitive(self):
        dispatcher = RegistryToolDispatcher()
        handler = lambda args, **kwargs: {"ok": True}
        dispatcher.register("ReadFile", handler)
        result = dispatcher.dispatch("readfile", {})
        assert result["ok"] is True

    def test_dispatch_with_kwargs(self):
        dispatcher = RegistryToolDispatcher()
        def handler(args, **kwargs):
            return {"args": args, "kwargs": kwargs}
        dispatcher.register("test", handler)
        result = dispatcher.dispatch("test", {"key": "value"}, extra="data")
        assert result["args"] == {"key": "value"}
        assert result["kwargs"]["extra"] == "data"

    def test_dispatch_exception_handled(self):
        dispatcher = RegistryToolDispatcher()
        def handler(args, **kwargs):
            raise ValueError("something broke")
        dispatcher.register("failing_tool", handler)
        result = dispatcher.dispatch("failing_tool", {})
        assert result["ok"] is False
        assert result["tool"] == "failing_tool"
        assert result["error"] == "tool execution failed"
        assert result["error_type"] == "ValueError"

    def test_dispatch_strips_name(self):
        dispatcher = RegistryToolDispatcher()
        handler = lambda args, **kwargs: {"ok": True}
        dispatcher.register("  spaced_tool  ", handler)
        result = dispatcher.dispatch("spaced_tool", {})
        assert result["ok"] is True


class TestListTools:
    """Tests for list_tools method."""

    def test_empty_list(self):
        dispatcher = RegistryToolDispatcher()
        tools = dispatcher.list_tools()
        assert tools == ()

    def test_sorted_list(self):
        dispatcher = RegistryToolDispatcher()
        dispatcher.register("zebra", lambda *a, **k: None)
        dispatcher.register("alpha", lambda *a, **k: None)
        dispatcher.register("middle", lambda *a, **k: None)
        tools = dispatcher.list_tools()
        assert tools == ("alpha", "middle", "zebra")

    def test_returns_tuple(self):
        dispatcher = RegistryToolDispatcher()
        dispatcher.register("test", lambda *a, **k: None)
        tools = dispatcher.list_tools()
        assert isinstance(tools, tuple)

    def test_list_reflects_current_tools(self):
        dispatcher = RegistryToolDispatcher()
        dispatcher.register("first", lambda *a, **k: None)
        tools1 = dispatcher.list_tools()
        dispatcher.register("second", lambda *a, **k: None)
        tools2 = dispatcher.list_tools()
        assert len(tools1) == 1
        assert len(tools2) == 2
        assert "second" in tools2