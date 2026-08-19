import json
import os
import subprocess
import sys
import time

import mcp.types


if len(sys.argv) != 2:
    print("Uso: probe_mcp_raw.py <server.py>")
    raise SystemExit(2)

python_exe = r"C:\Users\someo\agentic-tool-loop\.venv-py147\Scripts\python.exe"
server_script = os.path.abspath(sys.argv[1])

env = os.environ.copy()
env.update(
    {
        "AICARMINE_CODEX_MCP_REPO_ROOT": r"C:\Users\someo\agentic-tool-loop",
        "AICARMINE_LAB_REPO": r"C:\Users\someo\agentic-tool-loop",
        "AICARMINE_USEFUL_TOOLS_ROOT": r"C:\Users\someo\agentic-tool-loop\services\useful_tools",
        "AICARMINE_REPO_MCP_MAX_TEXT_CHARS": "24000",
    }
)

protocol = getattr(
    mcp.types,
    "LATEST_PROTOCOL_VERSION",
    "2024-11-05",
)

request = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": protocol,
        "capabilities": {},
        "clientInfo": {
            "name": "aicarmine-raw-probe",
            "version": "1.0",
        },
    },
}

print("PYTHON   :", python_exe)
print("SERVER   :", server_script)
print("PROTOCOL :", protocol)
print("REQUEST  :", json.dumps(request, ensure_ascii=False))
print()

process = subprocess.Popen(
    [python_exe, "-u", server_script],
    cwd=r"C:\Users\someo\agentic-tool-loop",
    env=env,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    encoding="utf-8",
    errors="replace",
)

try:
    stdout, stderr = process.communicate(
        json.dumps(request, separators=(",", ":")) + "\n",
        timeout=10,
    )
except subprocess.TimeoutExpired:
    process.kill()
    stdout, stderr = process.communicate()
    print("[TIMEOUT] Il server non ha risposto entro 10 secondi")

print("EXIT CODE:", process.returncode)
print()
print("===== STDOUT =====")
print(stdout if stdout else "<vuoto>")
print("===== STDERR =====")
print(stderr if stderr else "<vuoto>")
