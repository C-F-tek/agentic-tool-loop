"""Tests for the MCP server module."""

from __future__ import annotations

import json
import pytest
from ..mcp.tools import TOOL_SCHEMAS


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
