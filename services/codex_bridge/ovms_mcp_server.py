"""
AICarmine OVMS (OpenVINO Model Server) MCP Server

Provides MCP tools for managing OVMS reranker service.
Follows MCP stdio protocol with proper initialize handshake.
"""

import json
import sys
import os
import urllib.request

SERVER_NAME = "aicarmine-ovms-reranker-mcp"
SERVER_VERSION = "1.0.0"

TOOL_SCHEMAS = [
    {
        "name": "ovms_health",
        "description": "Check OVMS service health",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": True
        }
    },
    {
        "name": "ovms_start",
        "description": "Start OVMS service",
        "inputSchema": {
            "type": "object",
            "properties": {
                "config_path": {"type": "string"}
            },
            "additionalProperties": True
        }
    },
    {
        "name": "ovms_stop",
        "description": "Stop OVMS service",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": True
        }
    },
    {
        "name": "ovms_restart",
        "description": "Restart OVMS service",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": True
        }
    },
    {
        "name": "ovms_rerank",
        "description": "Perform reranking using OVMS",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "documents": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["query", "documents"],
            "additionalProperties": True
        }
    },
    {
        "name": "ovms_list_models",
        "description": "List available models",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": True
        }
    },
    {
        "name": "ovms_get_config",
        "description": "Get OVMS configuration",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": True
        }
    },
    {
        "name": "ovms_set_config",
        "description": "Set OVMS configuration",
        "inputSchema": {
            "type": "object",
            "properties": {
                "config": {"type": "object"}
            },
            "required": ["config"],
            "additionalProperties": True
        }
    },
    {
        "name": "ovms_embed",
        "description": "Generate embeddings for text/documents using OVMS embedding service on port 3551",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Input text to embed"},
                "port": {"type": "integer", "default": 3551, "description": "OVMS embedding service port"}
            },
            "required": ["text"],
            "additionalProperties": True
        }
    },
    {
        "name": "ovms_embed_batch",
        "description": "Generate embeddings for multiple documents using OVMS embedding service",
        "inputSchema": {
            "type": "object",
            "properties": {
                "texts": {"type": "array", "items": {"type": "string"}, "description": "List of input texts to embed"},
                "port": {"type": "integer", "default": 3551, "description": "OVMS embedding service port"}
            },
            "required": ["texts"],
            "additionalProperties": True
        }
    },
    {
        "name": "ovms_embed_health",
        "description": "Check OVMS embedding service health on port 3551",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port": {"type": "integer", "default": 3551, "description": "OVMS embedding service port"}
            },
            "additionalProperties": True
        }
    }
]

OVMS_REST_PORT = int(os.environ.get("OVMS_REST_PORT", "3550"))
OVMS_EMBED_PORT = int(os.environ.get("OVMS_EMBED_PORT", "3551"))
OVMS_CONFIG_PATH = os.environ.get("OVMS_CONFIG_PATH", "")
OVMS_EXE_PATH = os.environ.get("OVMS_EXE_PATH", "")


def make_json_response(msg_id, result):
    return json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result})


def make_error(msg_id, code, message):
    return json.dumps({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}})


def handle_ovms_health():
    try:
        url = f"http://127.0.0.1:{OVMS_REST_PORT}/info"
        req = urllib.request.urlopen(url, timeout=5)
        data = json.loads(req.read())
        return {"content": [{"type": "text", "text": json.dumps({"status": "healthy", "port": OVMS_REST_PORT, "response": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"status": "unhealthy", "error": str(e)})}], "isError": True}


def handle_ovms_start(args):
    config_path = args.get("config_path", OVMS_CONFIG_PATH)
    if not config_path:
        return {"content": [{"type": "text", "text": json.dumps({"error": "config_path is required"})}], "isError": True}
    return {"content": [{"type": "text", "text": json.dumps({"status": "started", "config": config_path})}]}


def handle_ovms_stop(args):
    try:
        url = f"http://127.0.0.1:{OVMS_REST_PORT}/shutdown"
        req = urllib.request.urlopen(url, timeout=5)
        data = json.loads(req.read())
        return {"content": [{"type": "text", "text": json.dumps({"status": "stopped", "response": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"status": "stop_failed", "error": str(e)})}], "isError": True}


def handle_ovms_restart(args):
    return {"content": [{"type": "text", "text": json.dumps({"status": "restart", "message": "Use stop + start separately"})}]}


def handle_ovms_rerank(args):
    query = args.get("query", "")
    documents = args.get("documents", [])
    if not query or not documents:
        return {"content": [{"type": "text", "text": json.dumps({"error": "query and documents are required"})}], "isError": True}
    try:
        url = f"http://127.0.0.1:{OVMS_REST_PORT}/rerank"
        payload = json.dumps({"query": query, "documents": documents}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "result": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_ovms_list_models(args):
    try:
        url = f"http://127.0.0.1:{OVMS_REST_PORT}/models"
        req = urllib.request.urlopen(url, timeout=5)
        data = json.loads(req.read())
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "models": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_ovms_get_config(args):
    config_path = OVMS_CONFIG_PATH
    if not config_path:
        return {"content": [{"type": "text", "text": json.dumps({"error": "OVMS_CONFIG_PATH not set"})}], "isError": True}
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "config": config})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_ovms_set_config(args):
    config = args.get("config", {})
    config_path = OVMS_CONFIG_PATH
    if not config_path:
        return {"content": [{"type": "text", "text": json.dumps({"error": "OVMS_CONFIG_PATH not set"})}], "isError": True}
    try:
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "message": "Configuration updated"})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_ovms_embed(args):
    text = args.get("text", "")
    port = args.get("port", OVMS_EMBED_PORT)
    if not text:
        return {"content": [{"type": "text", "text": json.dumps({"error": "text is required"})}], "isError": True}
    try:
        url = f"http://127.0.0.1:{port}/get"
        payload = json.dumps({"model_name": "BAAI/bge-small-en-v1.5", "texts": [text]}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "embedding": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_ovms_embed_batch(args):
    texts = args.get("texts", [])
    port = args.get("port", OVMS_EMBED_PORT)
    if not texts:
        return {"content": [{"type": "text", "text": json.dumps({"error": "texts array is required"})}], "isError": True}
    try:
        url = f"http://127.0.0.1:{port}/get"
        payload = json.dumps({"model_name": "BAAI/bge-small-en-v1.5", "texts": texts}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "embeddings": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_ovms_embed_health(args):
    port = args.get("port", OVMS_EMBED_PORT)
    try:
        url = f"http://127.0.0.1:{port}/get"
        req = urllib.request.urlopen(url, timeout=5)
        data = json.loads(req.read())
        return {"content": [{"type": "text", "text": json.dumps({"status": "healthy", "port": port, "response": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"status": "unhealthy", "error": str(e)})}], "isError": True}


HANDLERS = {
    "ovms_health": handle_ovms_health,
    "ovms_start": handle_ovms_start,
    "ovms_stop": handle_ovms_stop,
    "ovms_restart": handle_ovms_restart,
    "ovms_rerank": handle_ovms_rerank,
    "ovms_list_models": handle_ovms_list_models,
    "ovms_get_config": handle_ovms_get_config,
    "ovms_set_config": handle_ovms_set_config,
    "ovms_embed": handle_ovms_embed,
    "ovms_embed_batch": handle_ovms_embed_batch,
    "ovms_embed_health": handle_ovms_embed_health,
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