"""
AICarmine Ollama MCP Server

Provides MCP tools for Ollama service.
Follows MCP stdio protocol with proper initialize handshake.
"""

import json
import sys
import os
import urllib.request

SERVER_NAME = "aicarmine-ollama-mcp"
SERVER_VERSION = "1.0.0"

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")

TOOL_SCHEMAS = [
    {
        "name": "ollama_health",
        "description": "Check Ollama service health",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "ollama_list_models",
        "description": "List available models",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "ollama_show_model",
        "description": "Show model details",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": True
        }
    },
    {
        "name": "ollama_pull_model",
        "description": "Pull a model from registry",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": True
        }
    },
    {
        "name": "ollama_delete_model",
        "description": "Delete a model",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": True
        }
    },
    {
        "name": "ollama_chat",
        "description": "Chat with a model",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "messages": {"type": "array", "items": {"type": "object"}}
            },
            "required": ["model", "messages"],
            "additionalProperties": True
        }
    },
    {
        "name": "ollama_generate",
        "description": "Generate text from a model",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "prompt": {"type": "string"}
            },
            "required": ["model", "prompt"],
            "additionalProperties": True
        }
    },
    {
        "name": "ollama_create_model",
        "description": "Create a new model",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "config": {"type": "object"}
            },
            "required": ["name"],
            "additionalProperties": True
        }
    },
    {
        "name": "ollama_copy_model",
        "description": "Copy a model",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "destination": {"type": "string"}
            },
            "required": ["source", "destination"],
            "additionalProperties": True
        }
    },
    {
        "name": "ollama_ps",
        "description": "List running models",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "ollama_tags",
        "description": "List model tags",
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


def handle_ollama_health(args):
    try:
        data = make_ollama_request("/version", timeout=5)
        return {"content": [{"type": "text", "text": json.dumps({"status": "healthy", "version": data.get("version", "unknown")})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"status": "unhealthy", "error": str(e)})}], "isError": True}


def handle_ollama_list_models(args):
    try:
        data = make_ollama_request("/tags")
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "models": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_ollama_show_model(args):
    name = args.get("name", "")
    if not name:
        return {"content": [{"type": "text", "text": json.dumps({"error": "name is required"})}], "isError": True}
    try:
        data = make_ollama_request(f"/show/{name}")
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "model": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_ollama_pull_model(args):
    name = args.get("name", "")
    if not name:
        return {"content": [{"type": "text", "text": json.dumps({"error": "name is required"})}], "isError": True}
    try:
        data = make_ollama_request(f"/pull/{name}")
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "result": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_ollama_delete_model(args):
    name = args.get("name", "")
    if not name:
        return {"content": [{"type": "text", "text": json.dumps({"error": "name is required"})}], "isError": True}
    try:
        data = make_ollama_request(f"/delete/{name}")
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "result": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_ollama_chat(args):
    model = args.get("model", "")
    messages = args.get("messages", [])
    if not model or not messages:
        return {"content": [{"type": "text", "text": json.dumps({"error": "model and messages are required"})}], "isError": True}
    try:
        data = make_ollama_request("/chat", {"model": model, "messages": messages})
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "result": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_ollama_generate(args):
    model = args.get("model", "")
    prompt = args.get("prompt", "")
    if not model or not prompt:
        return {"content": [{"type": "text", "text": json.dumps({"error": "model and prompt are required"})}], "isError": True}
    try:
        data = make_ollama_request("/generate", {"model": model, "prompt": prompt})
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "result": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_ollama_create_model(args):
    name = args.get("name", "")
    config = args.get("config", {})
    if not name:
        return {"content": [{"type": "text", "text": json.dumps({"error": "name is required"})}], "isError": True}
    try:
        data = make_ollama_request("/create", {"name": name, "config": config})
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "result": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_ollama_copy_model(args):
    source = args.get("source", "")
    destination = args.get("destination", "")
    if not source or not destination:
        return {"content": [{"type": "text", "text": json.dumps({"error": "source and destination are required"})}], "isError": True}
    try:
        data = make_ollama_request("/copy", {"source": source, "destination": destination})
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "result": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_ollama_ps(args):
    try:
        data = make_ollama_request("/ps")
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "models": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_ollama_tags(args):
    try:
        data = make_ollama_request("/tags")
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "tags": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


HANDLERS = {
    "ollama_health": handle_ollama_health,
    "ollama_list_models": handle_ollama_list_models,
    "ollama_show_model": handle_ollama_show_model,
    "ollama_pull_model": handle_ollama_pull_model,
    "ollama_delete_model": handle_ollama_delete_model,
    "ollama_chat": handle_ollama_chat,
    "ollama_generate": handle_ollama_generate,
    "ollama_create_model": handle_ollama_create_model,
    "ollama_copy_model": handle_ollama_copy_model,
    "ollama_ps": handle_ollama_ps,
    "ollama_tags": handle_ollama_tags,
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