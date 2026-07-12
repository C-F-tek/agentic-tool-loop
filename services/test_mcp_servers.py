"""Test all codex_bridge MCP server files for importability."""
import sys
import os

# Simulate the exact environment Cline uses:
# cwd = C:\Users\CarmineFaiola\AI
# args = -u C:\Users\CarmineFaiola\AI\services\codex_bridge\<server>.py
# PYTHONPATH = C:\Users\CarmineFaiola\AI\services;C:\Users\CarmineFaiola\AI

REPO_ROOT = r"C:\Users\CarmineFaiola\AI"
CODEx_BRIDGE = os.path.join(REPO_ROOT, "services", "codex_bridge")

# Add both services/ and services/codex_bridge/ to path (simulating PYTHONPATH)
sys.path.insert(0, CODEx_BRIDGE)  # For repo_mcp_common, rag_index_repo, etc.
sys.path.insert(0, os.path.join(REPO_ROOT, "services"))  # For aicarmine_broker imports
sys.path.insert(0, REPO_ROOT)  # For top-level modules

SERVERS = [
    ("repo_state_mcp_server", "repo_mcp_common"),
    ("repo_search_det_mcp_server", "repo_mcp_common"),
    ("rag_mcp_server", "rag_index_repo"),
    ("repo_validate_mcp_server", "repo_mcp_common"),
    ("git_readonly_mcp_server", "repo_mcp_common"),
    ("sqlite_readonly_mcp_server", "repo_mcp_common"),
    ("job_artifact_mcp_server", "repo_mcp_common"),
    ("job_view_mcp_server", "repo_mcp_common"),
    ("project_memory_mcp_server", "repo_mcp_common"),
    ("local_subagent_mcp_server", "agentic_loop_client_mcp_server"),
    ("agentic_loop_client_mcp_server", "repo_mcp_common"),
    ("repo_code_mcp_server", "repo_mcp_common"),
    ("ops_mcp_server", "repo_mcp_common"),
    ("mcp_server", None),
]

ok = 0
fail = 0
missing = []

for mod, dep in SERVERS:
    try:
        __import__(mod)
        print(f"OK: {mod}")
        ok += 1
    except Exception as e:
        print(f"FAIL: {mod} — {type(e).__name__}: {e}")
        fail += 1
        missing.append(mod)

print(f"\n{ok}/{ok+fail} servers imported OK. Missing/failing: {missing}")