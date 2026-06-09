import subprocess, json, sys, time, os

os.environ['AICARMINE_RAG_MCP_DEBUG'] = '1'

# Start the MCP server with standard pipe transport (JSONL mode)
proc = subprocess.Popen(
    [sys.executable, r'C:\Users\carmi\AI\services\codex_bridge\rag_mcp_server.py'],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    creationflags=subprocess.CREATE_NO_WINDOW,
    env={**os.environ, 'AICARMINE_RAG_MCP_STDIO_TRANSPORT': 'jsonl', 'AICARMINE_RAG_MCP_DEBUG': '1'}
)
time.sleep(0.5)

def send_jsonl(method, params=None, msg_id=1):
    payload = {'jsonrpc': '2.0', 'id': msg_id, 'method': method}
    if params is not None:
        payload['params'] = params
    raw = (json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
    proc.stdin.write(raw)
    proc.stdin.flush()
    line = proc.stdout.readline()
    return json.loads(line)

def tools_call(name, arguments, msg_id=2):
    payload = {
        'jsonrpc': '2.0',
        'id': msg_id,
        'method': 'tools/call',
        'params': {'name': name, 'arguments': arguments}
    }
    raw = (json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
    proc.stdin.write(raw)
    proc.stdin.flush()
    line = proc.stdout.readline()
    return json.loads(line)

def initialize(msg_id=1):
    payload = {
        'jsonrpc': '2.0',
        'id': msg_id,
        'method': 'initialize',
        'params': {
            'capabilities': {'roots': {'listChanged': True}, 'tools': {}},
            'protocolVersion': '2024-11-05',
            'processId': 9999
        }
    }
    raw = (json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
    proc.stdin.write(raw)
    proc.stdin.flush()
    line = proc.stdout.readline()
    return json.loads(line)

try:
    r1 = initialize()
    print('=== INIT ===')
    print(json.dumps(r1, indent=2, ensure_ascii=False))

    r2 = tools_call('aicarmine_rag_context', {'operation': 'reindex'})
    print('=== REINDEX ===')
    print(json.dumps(r2, indent=2, ensure_ascii=False))

    r3 = tools_call('aicarmine_rag_context', {'operation': 'inspect'})
    print('=== INSPECT ===')
    print(json.dumps(r3, indent=2, ensure_ascii=False))

except Exception as e:
    print(f'ERROR: {type(e).__name__}: {e}')
finally:
    proc.terminate()
    proc.wait(timeout=5)
    proc.stdin.close()
    proc.stdout.close()
    proc.stderr.close()
    stderr_out = proc.stderr.read().decode(errors='replace')
    if stderr_out.strip():
        print('=== STDERR ===')
        print(stderr_out)
