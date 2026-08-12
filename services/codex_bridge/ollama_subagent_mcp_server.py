"""
AICarmine Ollama Subagent MCP Server

Provides MCP tools for Ollama subagent operations.
Follows MCP stdio protocol with proper initialize handshake.
"""

import json
import sys
import os
import urllib.request

SERVER_NAME = "aicarmine-ollama-subagent-mcp"
SERVER_VERSION = "1.0.0"

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")

TOOL_SCHEMAS = [
    {
        "name": "aicarmine_ollama_subagent_health",
        "description": "Check Ollama subagent health",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "aicarmine_ollama_subagent_generate",
        "description": "Generate text via Ollama subagent",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "prompt": {"type": "string"},
                "system": {"type": "string"}
            },
            "required": ["model", "prompt"],
            "additionalProperties": True
        }
    },
    {
        "name": "aicarmine_ollama_subagent_generate_stream",
        "description": "Stream generation via Ollama subagent",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "prompt": {"type": "string"},
                "stream": {"type": "boolean"}
            },
            "required": ["model", "prompt"],
            "additionalProperties": True
        }
    },
    {
        "name": "aicarmine_ollama_subagent_list_models",
        "description": "List available Ollama models",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    }
]


def make_ollama_request(path, data=None, timeout=60):
    url = f"{OLLAMA_URL}{path}"
    if data:
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def handle_aicarmine_ollama_subagent_health(args):
    try:
        data = make_ollama_request("/version", timeout=5)
        return {"content": [{"type": "text", "text": json.dumps({"status": "healthy", "version": data.get("version", "unknown"), "server": SERVER_NAME})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"status": "unhealthy", "error": str(e)})}], "isError": True}


def handle_aicarmine_ollama_subagent_generate(args):
    model = args.get("model", "")
    prompt = args.get("prompt", "")
    system = args.get("system", "")
    if not model or not prompt:
        return {"content": [{"type": "text", "text": json.dumps({"error": "model and prompt are required"})}], "isError": True}
    try:
        data = make_ollama_request("/generate", {"model": model, "prompt": prompt, "system": system})
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "result": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_aicarmine_ollama_subagent_generate_stream(args):
    model = args.get("model", "")
    prompt = args.get("prompt", "")
    stream = args.get("stream", True)
    if not model or not prompt:
        return {"content": [{"type": "text", "text": json.dumps({"error": "model and prompt are required"})}], "isError": True}
    try:
        data = make_ollama_request("/generate", {"model": model, "prompt": prompt, "stream": stream})
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "result": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_aicarmine_ollama_subagent_list_models(args):
    try:
        data = make_ollama_request("/tags")
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "models": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


HANDLERS = {
    "aicarmine_ollama_subagent_health": handle_aicarmine_ollama_subagent_health,
    "aicarmine_ollama_subagent_generate": handle_aicarmine_ollama_subagent_generate,
    "aicarmine_ollama_subagent_generate_stream": handle_aicarmine_ollama_subagent_generate_stream,
    "aicarmine_ollama_subagent_list_models": handle_aicarmine_ollama_subagent_list_models,
}


def main():
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    while True:
        line = stdin.readline()
        if not line:
            break
        message = json.loads(line.decode("utf-8-sig", errors="replace"))
        msg_id = message.get("id")
        method = message.get("method", "")
        params = message.get("params", {}) if isinstance(message.get("params"), dict) else {}

        if method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                        "prompts": {"listChanged": False},
                        "roots": {"listChanged": False},
                    },
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            }
            stdout.write(json.dumps(response).encode("utf-8") + b"\n")
            stdout.flush()
            continue

        if method == "tools/list":
            response = {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOL_SCHEMAS}}
            stdout.write(json.dumps(response).encode("utf-8") + b"\n")
            stdout.flush()
            continue

        if method == "tools/call":
            name = params.get("name", "")
            arguments = params.get("arguments", {}) if isinstance(params.get("arguments"), dict) else {}
            handler = HANDLERS.get(name)
            if handler:
                try:
                    result = handler(arguments)
                except Exception as e:
                    result = {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}
                response = {"jsonrpc": "2.0", "id": msg_id, "result": result}
            else:
                response = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Unknown tool: {name}"}}
            stdout.write(json.dumps(response).encode("utf-8") + b"\n")
            stdout.flush()
            continue

        if method.startswith("notifications/"):
            continue

    return 0


if __name__ == "__main__":
    raise SystemExit(main())