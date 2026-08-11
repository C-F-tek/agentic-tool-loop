"""Tests for the MCP server module."""

from __future__ import annotations

import json
import pytest
from mcp.server import _handle_rpc, TOOL_SCHEMAS


class TestMCPTools:
    """Test suite for MCP tool definitions."""
    
    def test_tool_schemas_exist(self):
        """Test that tool schemas are defined."""
        assert len(TOOL_SCHEMAS) > 0
    
    def test_query_tool_schema(self):
        """Test query tool schema."""
        query_tool = [t for t in TOOL_SCHEMAS if t.get("name") == "aicarmine_data_rag_query"]
        assert len(query_tool) == 1
        assert "question" in query_tool[0]["inputSchema"]["properties"]
    
    def test_build_index_tool_schema(self):
        """Test build_index tool schema."""
        build_tool = [t for t in TOOL_SCHEMAS if t.get("name") == "aicarmine_data_rag_build_index"]
        assert len(build_tool) == 1
        assert "source_path" in build_tool[0]["inputSchema"]["properties"]


class TestRPCHandlers:
    """Test suite for RPC message handling."""
    
    def test_initialize_message(self):
        """Test initialize RPC response."""
        msg = {"id": 1, "method": "initialize", "params": {}}
        result = _handle_rpc(msg)
        assert result is not None
        assert result.get("result") is not None
        assert result["result"].get("serverInfo") is not None
    
    def test_ping_message(self):
        """Test ping RPC response."""
        msg = {"id": 2, "method": "ping"}
        result = _handle_rpc(msg)
        assert result is not None
        assert result.get("result") == {}
    
    def test_tools_list_message(self):
        """Test tools/list RPC response."""
        msg = {"id": 3, "method": "tools/list"}
        result = _handle_rpc(msg)
        assert result is not None
        assert result.get("result") is not None
        assert result["result"].get("tools") is not None
    
    def test_unknown_method(self):
        """Test unknown method handling."""
        msg = {"id": 4, "method": "unknown/method"}
        result = _handle_rpc(msg)
        assert result is not None
        assert result.get("error") is not None