"""
AICarmine Planner Components MCP Server

Exposes individual planner loop components as MCP tools for testing:
1. orientation_shadow - Initial orientation evaluation
2. vulkan_repair - Planner decision repair
3. replan_specialist - Replan specialist
4. guard_rejection - Guard rejection signatures
5. incomprehensible_retry - Incomprehensible output retry

Each component has a dedicated tool call that simulates a call to that component.
Follows MCP stdio protocol with proper initialize handshake.
"""

import json
import sys
import os
import httpx

SERVER_NAME = "aicarmine-planner-components-mcp"
SERVER_VERSION = "1.0.0"

BROKER_URL = os.environ.get("BROKER_URL", "http://127.0.0.1:3572")

TOOL_SCHEMAS = [
    {
        "name": "orientation_shadow",
        "description": "Test orientation shadow component - initial orientation evaluation",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "semantic_intent": {"type": "object"},
                "doc_plan": {"type": "object"},
                "area_plans": {"type": "object"}
            },
            "required": ["goal"],
            "additionalProperties": True
        }
    },
    {
        "name": "vulkan_repair",
        "description": "Test vulkan_repair component - planner decision repair",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "decision": {"type": "object"},
                "validation": {"type": "object"}
            },
            "required": ["job_id", "decision"],
            "additionalProperties": True
        }
    },
    {
        "name": "replan_specialist",
        "description": "Test replan_specialist component - replan specialist for validation rejection",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "goal": {"type": "string"},
                "decision": {"type": "object"},
                "validation": {"type": "object"}
            },
            "required": ["job_id", "goal", "decision", "validation"],
            "additionalProperties": True
        }
    },
    {
        "name": "guard_rejection",
        "description": "Test guard_rejection component - guard rejection signatures",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "signature": {"type": "object"},
                "count": {"type": "integer"}
            },
            "required": ["job_id"],
            "additionalProperties": True
        }
    },
    {
        "name": "incomprehensible_retry",
        "description": "Test incomprehensible_retry component - retry for incomprehensible planner output",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "output": {"type": "string"},
                "retry_count": {"type": "integer"}
            },
            "required": ["job_id", "output"],
            "additionalProperties": True
        }
    }
]


def make_broker_request(path, data=None, timeout=30):
    url = f"{BROKER_URL}{path}"
    if data:
        payload = json.dumps(data).encode("utf-8")
        req = httpx.Client(timeout=30).post(url, data=payload, headers={"Content-Type": "application/json"})
    else:
        req = httpx.Client(timeout=30).post(url)
    with httpx.Client(timeout=30).get(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def handle_orientation_shadow(args):
    goal = args.get("goal", "")
    if not goal:
        return {"content": [{"type": "text", "text": json.dumps({"error": "goal is required"})}], "isError": True}
    try:
        result = {
            "component": "orientation_shadow",
            "status": "simulated",
            "goal": goal,
            "effective_mode": "shadow",
            "candidate_count": 0,
            "legacy_selected_candidate_ids": [],
            "model_selected_candidate_ids": [],
            "selection_metrics": {
                "legacy_count": 0,
                "model_count": 0,
                "selection_overlap": [],
                "selection_overlap_count": 0,
                "top1_match": False,
                "exact_match": True,
                "would_change_selection": False,
            },
            "model_summary": {
                "ok": True,
                "status": "ready",
                "rationale": "Orientation shadow simulation successful",
                "confidence": 1.0,
                "unknown_candidate_ids": [],
                "duplicate_candidate_ids": [],
                "duplicate_input_candidate_ids": [],
                "error_type": "",
                "error": "",
            },
        }
        return {"content": [{"type": "text", "text": json.dumps(result)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_vulkan_repair(args):
    job_id = args.get("job_id", "")
    decision = args.get("decision", {})
    if not job_id or not decision:
        return {"content": [{"type": "text", "text": json.dumps({"error": "job_id and decision are required"})}], "isError": True}
    try:
        result = {
            "component": "vulkan_repair",
            "status": "simulated",
            "job_id": job_id,
            "original_decision": decision,
            "repaired_decision": decision,
            "repair_applied": False,
            "reason": "No repair needed - decision valid",
        }
        return {"content": [{"type": "text", "text": json.dumps(result)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_replan_specialist(args):
    job_id = args.get("job_id", "")
    goal = args.get("goal", "")
    decision = args.get("decision", {})
    validation = args.get("validation", {})
    if not job_id or not goal or not decision or not validation:
        return {"content": [{"type": "text", "text": json.dumps({"error": "All fields required: job_id, goal, decision, validation"})}], "isError": True}
    try:
        result = {
            "component": "replan_specialist",
            "status": "simulated",
            "job_id": job_id,
            "goal": goal,
            "decision": decision,
            "validation": validation,
            "available": True,
            "ok": True,
            "decision": "continue",
            "required_next_progress": "",
            "required_next_tool_call": {},
        }
        return {"content": [{"type": "text", "text": json.dumps(result)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_guard_rejection(args):
    job_id = args.get("job_id", "")
    if not job_id:
        return {"content": [{"type": "text", "text": json.dumps({"error": "job_id is required"})}], "isError": True}
    try:
        result = {
            "component": "guard_rejection",
            "status": "simulated",
            "job_id": job_id,
            "guard_count": 0,
            "guard_result": True,
            "rejection_signature": [],
            "rejection_signature_count": 0,
        }
        return {"content": [{"type": "text", "text": json.dumps(result)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_incomprehensible_retry(args):
    job_id = args.get("job_id", "")
    output = args.get("output", "")
    if not job_id or not output:
        return {"content": [{"type": "text", "text": json.dumps({"error": "job_id and output are required"})}], "isError": True}
    try:
        result = {
            "component": "incomprehensible_retry",
            "status": "simulated",
            "job_id": job_id,
            "output": output,
            "retry_count": 0,
            "should_retry": False,
            "is_unrecoverable": False,
        }
        return {"content": [{"type": "text", "text": json.dumps(result)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


HANDLERS = {
    "orientation_shadow": handle_orientation_shadow,
    "vulkan_repair": handle_vulkan_repair,
    "replan_specialist": handle_replan_specialist,
    "guard_rejection": handle_guard_rejection,
    "incomprehensible_retry": handle_incomprehensible_retry,
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