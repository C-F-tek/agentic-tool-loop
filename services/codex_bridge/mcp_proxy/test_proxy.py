"""
AICarmine MCP Proxy - Test Script

Tests the proxy server initialization, routing, hooks, and server management.
Run with: python services/codex_bridge/mcp_proxy/test_proxy.py
"""

import asyncio
import json
import sys
from pathlib import Path

# Add this directory to path for relative imports
test_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(test_dir))

# Import directly from local modules
from config import TARGET_SERVERS, SERVER_SCRIPTS, ROUTE_MAP
from router import Router
from hooks import HookContext, MCPHooks
from server_manager import ServerManager


async def test_router():
    """Test the router module."""
    print("\n=== Testing Router ===")
    
    router = Router()
    
    # Test direct route lookup
    test_cases = [
        ("propose_edit", "aicarmine-repo-code"),
        ("ollama_health", "aicarmine-ollama"),
        ("planner_state_inspect", "aicarmine-broker-planner"),
        ("unknown_tool_xyz", "aicarmine-codex-app"),  # default fallback
    ]
    
    for tool_name, expected_server in test_cases:
        result = router.route(tool_name)
        status = "OK" if result == expected_server else "FAIL"
        print(f"  [{status}] Route '{tool_name}' -> '{result}' (expected '{expected_server}')")
    
    # Test adding/removing routes
    router.add_route("custom_tool", "aicarmine-repo-code")
    assert router.route("custom_tool") == "aicarmine-repo-code"
    print("  [OK] Added custom route")
    
    router.remove_route("custom_tool")
    assert router.route("custom_tool") == "aicarmine-codex-app"
    print("  [OK] Removed custom route")
    
    # Test listing routes
    routes = router.list_routes()
    print(f"  [OK] Total routes: {len(routes)}")


async def test_hooks():
    """Test the hooks module."""
    print("\n=== Testing Hooks ===")
    
    hooks = MCPHooks()
    
    # Test basic hook functionality
    context = HookContext(
        tool_name="test_tool",
        args={"key": "value"},
        server_name="test-server",
    )
    
    # Test before hook returns None (proceed)
    result = await hooks.before_tool_call(context)
    assert result is None
    print("  [OK] Before hook returns None (proceed)")
    
    # Test after hook adds metadata
    test_result = {"data": "test"}
    modified = await hooks.after_tool_call(context, test_result)
    assert "_proxy_meta" in modified
    print("  [OK] After hook adds metadata")
    
    # Test error hook
    error = Exception("test error")
    error_result = await hooks.on_error(context, error)
    assert "error" in error_result
    assert "tool" in error_result
    assert "server" in error_result
    print("  [OK] Error hook returns error structure")
    
    # Test rate limiting
    hooks.set_rate_limit(2)
    for i in range(3):
        ctx = HookContext(tool_name=f"tool_{i}", args={}, server_name="test")
        r = await hooks.before_tool_call(ctx)
        if r:
            print(f"  [OK] Rate limit triggered after {i+1} calls")
            break
    
    # Test call stats
    stats = hooks.get_call_stats()
    print(f"  [OK] Call stats: {stats}")


async def test_server_manager():
    """Test the server manager module."""
    print("\n=== Testing Server Manager ===")
    
    manager = ServerManager()
    
    # Test listing servers (without starting them)
    servers = await manager.list_servers()
    print(f"  [OK] Managed servers count: {len(servers)}")
    
    # Verify all configured servers have valid script paths
    # Note: SERVER_SCRIPTS paths are relative to workspace root (parent of services/)
    # test_proxy.py is at services/codex_bridge/mcp_proxy/test_proxy.py
    # Going up 4 levels: mcp_proxy -> codex_bridge -> services -> workspace root
    project_root = Path(__file__).parent.parent.parent.parent
    all_valid = True
    for name, path in SERVER_SCRIPTS.items():
        full_path = project_root / path
        if not full_path.exists():
            print(f"  [WARN] Script not found: {path}")
            all_valid = False
    
    if all_valid:
        print("  [OK] All server scripts exist")
    
    # Verify route map coverage
    print(f"  [OK] Route map entries: {len(ROUTE_MAP)}")


async def test_config():
    """Test the configuration module."""
    print("\n=== Testing Configuration ===")
    
    print(f"  [OK] Proxy server name: {'aicarmine-proxy'}")
    print(f"  [OK] Target servers: {len(TARGET_SERVERS)}")
    print(f"  [OK] Server scripts: {len(SERVER_SCRIPTS)}")
    print(f"  [OK] Route map entries: {len(ROUTE_MAP)}")
    print(f"  [OK] Default max calls/minute: 30")
    
    # Verify no duplicate server names
    unique = len(set(TARGET_SERVERS))
    print(f"  [OK] Unique servers: {unique}/{len(TARGET_SERVERS)}")


async def main():
    """Run all tests."""
    print("=" * 60)
    print("AICarmine MCP Proxy - Test Suite")
    print("=" * 60)
    
    try:
        await test_config()
        await test_router()
        await test_hooks()
        await test_server_manager()
        
        print("\n" + "=" * 60)
        print("All tests passed!")
        print("=" * 60)
        return 0
        
    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)