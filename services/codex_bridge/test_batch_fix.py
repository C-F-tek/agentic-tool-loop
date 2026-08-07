#!/usr/bin/env python3
"""Quick test for batch proxy fix."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mcp_batch_proxy import SERVER_SCRIPTS, MCPBatchProxy


def test_single_tool():
    """Test a single tool call via batch proxy."""
    print("Testing single tool call via batch proxy...")
    
    proxy = MCPBatchProxy(max_concurrent=1, timeout_seconds=15.0)
    
    result = proxy._execute_single_tool(
        "aicarmine_repo_state",
        "aicarmine_repo_state_health",
        {}
    )
    
    print(json.dumps(result, indent=2, default=str))
    
    assert result.get("ok") or "result" in result, f"Unexpected result: {result}"
    print("✓ Single tool call succeeded!")


def test_batch_execute():
    """Test batch execution."""
    print("\nTesting batch execution...")
    
    operations = [
        {
            "server": "aicarmine_repo_state",
            "tool": "aicarmine_repo_state_health",
            "args": {}
        },
        {
            "server": "aicarmine_repo_state",
            "tool": "aicarmine_repo_state_status",
            "args": {}
        }
    ]
    
    proxy = MCPBatchProxy(max_concurrent=2, timeout_seconds=30.0)
    results = proxy.execute_batch(operations)
    
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    test_single_tool()
    test_batch_execute()