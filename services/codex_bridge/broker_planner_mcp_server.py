"""
AICarmine Broker Planner MCP Server

Provides MCP tools for the broker planner.
Follows MCP stdio protocol with proper initialize handshake.
"""

import json
import sys
import os
import urllib.request

SERVER_NAME = "aicarmine-broker-planner-mcp"
SERVER_VERSION = "1.0.0"

BROKER_URL = os.environ.get("BROKER_URL", "http://127.0.0.1:3572")

TOOL_SCHEMAS = [
    {
        "name": "planner_state_inspect",
        "description": "Inspect planner state",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "planner_decision_history",
        "description": "Get decision history",
        "inputSchema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
            "additionalProperties": True
        }
    },
    {
        "name": "planner_tool_selection",
        "description": "Inspect tool selection",
        "inputSchema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
            "additionalProperties": True
        }
    },
    {
        "name": "planner_validator_diagnostics",
        "description": "Get validator diagnostics",
        "inputSchema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
            "additionalProperties": True
        }
    },
    {
        "name": "planner_evidence_contract",
        "description": "Inspect evidence contract",
        "inputSchema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
            "additionalProperties": True
        }
    },
    {
        "name": "planner_loop_metrics",
        "description": "Get loop metrics",
        "inputSchema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
            "additionalProperties": True
        }
    },
    {
        "name": "planner_list_jobs",
        "description": "List planner jobs",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "planner_config_summary",
        "description": "Get config summary",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    }
]


def make_broker_request(path, data=None, timeout=30):
    url = f"{BROKER_URL}{path}"
    if data:
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def handle_planner_state_inspect(args):
    try:
        data = make_broker_request("/planner/state")
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "state": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_planner_decision_history(args):
    job_id = args.get("job_id", "")
    if not job_id:
        return {"content": [{"type": "text", "text": json.dumps({"error": "job_id is required"})}], "isError": True}
    try:
        data = make_broker_request(f"/planner/history/{job_id}")
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "history": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_planner_tool_selection(args):
    job_id = args.get("job_id", "")
    if not job_id:
        return {"content": [{"type": "text", "text": json.dumps({"error": "job_id is required"})}], "isError": True}
    try:
        data = make_broker_request(f"/planner/tools/{job_id}")
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "selections": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_planner_validator_diagnostics(args):
    job_id = args.get("job_id", "")
    if not job_id:
        return {"content": [{"type": "text", "text": json.dumps({"error": "job_id is required"})}], "isError": True}
    try:
        data = make_broker_request(f"/planner/diagnostics/{job_id}")
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "diagnostics": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_planner_evidence_contract(args):
    job_id = args.get("job_id", "")
    if not job_id:
        return {"content": [{"type": "text", "text": json.dumps({"error": "job_id is required"})}], "isError": True}
    try:
        data = make_broker_request(f"/planner/evidence/{job_id}")
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "contract": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_planner_loop_metrics(args):
    job_id = args.get("job_id", "")
    if not job_id:
        return {"content": [{"type": "text", "text": json.dumps({"error": "job_id is required"})}], "isError": True}
    try:
        data = make_broker_request(f"/planner/metrics/{job_id}")
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "metrics": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_planner_list_jobs(args):
    try:
        data = make_broker_request("/planner/jobs")
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "jobs": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_planner_config_summary(args):
    try:
        data = make_broker_request("/planner/config")
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "config": data})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


HANDLERS = {
    "planner_state_inspect": handle_planner_state_inspect,
    "planner_decision_history": handle_planner_decision_history,
    "planner_tool_selection": handle_planner_tool_selection,
    "planner_validator_diagnostics": handle_planner_validator_diagnostics,
    "planner_evidence_contract": handle_planner_evidence_contract,
    "planner_loop_metrics": handle_planner_loop_metrics,
    "planner_list_jobs": handle_planner_list_jobs,
    "planner_config_summary": handle_planner_config_summary,
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