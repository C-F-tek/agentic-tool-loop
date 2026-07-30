#!/usr/bin/env python3
"""Test aicarmine_rag_reindex via subprocess."""
import subprocess
import json
import sys

python = r"C:\Users\sanit\AppData\Local\Programs\Python\Python314\python.exe"
server = r"C:\Users\sanit\agentic-tool-loop\services\codex_bridge\rag_mcp_server.py"
cwd = r"C:\Users\sanit\agentic-tool-loop"

# Step 1: Initialize
init_msg = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "processId": 1234,
        "rootUri": "file:///C:/Users/sanit/agentic-tool-loop",
        "clientInfo": {"name": "test", "version": "1.0"}
    }
}

# Step 2: Reindex
reindex_msg = {
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
        "name": "aicarmine_rag_reindex",
        "arguments": {
            "repo": "C:\\Users\\sanit\\agentic-tool-loop",
            "db": "C:\\Users\\sanit\\agentic-tool-loop\\state\\codex_rag\\code_rag.sqlite3",
            "source": "git",
            "mode": "full"
        }
    }
}

proc = subprocess.run(
    [python, "-u", server],
    input=(json.dumps(init_msg) + "\n" + json.dumps(reindex_msg) + "\n").encode("utf-8"),
    capture_output=True,
    cwd=cwd,
    timeout=120
)

print("STDOUT:")
print(proc.stdout.decode("utf-8", errors="replace"))
print("\nSTDERR:")
print(proc.stderr.decode("utf-8", errors="replace"))
print(f"\nReturn code: {proc.returncode}")