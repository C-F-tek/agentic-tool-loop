# Test RAG MCP - query planner from project
$pythonPath = "python"
$serverScript = "services/codex_bridge/rag_mcp_server.py"
$repoRoot = "c:\Users\someo\agentic-tool-loop"

# Step 1: Reindex first (filesystem mode)
Write-Host "=== STEP 1: Build/rebuild RAG index ===" 
$jsonReindex = @{
    jsonrpc = "2.0"
    id = 1
    method = "tools/call"
    params = @{
        name = "aicarmine_rag_reindex"
        arguments = @{
            search_path = $repoRoot
            source = "filesystem"
            mode = "full"
        }
    }
} | ConvertTo-Json -Depth 5

Write-Host $jsonReindex
$jsonReindex | Out-File -FilePath "$env:TEMP\rag_request.json" -Encoding UTF8

# Use Python to communicate with stdio MCP server
$pyCode = @"
import sys, json, subprocess

def send_msg(proc, msg):
    data = json.dumps(msg).encode('utf-8') + b'\n'
    proc.stdin.write(data)
    proc.stdin.flush()
    print(f"Sent: {data.decode()}")

def recv_msg(proc):
    line = proc.stdout.readline()
    if not line:
        return None
    return json.loads(line.strip())

proc = subprocess.Popen(
    ["python", "-u", r"$serverScript"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True
)

try:
    # Initialize
    send_msg(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    resp = recv_msg(proc)
    print(f"Init response: {json.dumps(resp, indent=2)}")

    # Call reindex
    send_msg(proc, {{
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {{
            "name": "aicarmine_rag_reindex",
            "arguments": {{
                "search_path": r"$repoRoot",
                "source": "filesystem",
                "mode": "full"
            }}
        }}
    }})
    resp = recv_msg(proc)
    print(f"\nReindex response:\n{json.dumps(resp.get('result', {}), indent=2)}")

except Exception as e:
    print(f"Error: {{e}}")
finally:
    proc.terminate()
"@

python -c $pyCode
