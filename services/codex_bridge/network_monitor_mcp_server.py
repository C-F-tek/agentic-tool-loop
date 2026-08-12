"""
AICarmine Network Monitor MCP Server

Provides MCP tools for network monitoring operations.
Follows MCP stdio protocol with proper initialize handshake.
"""

import json
import sys
import os

SERVER_NAME = "aicarmine-network-monitor-mcp"
SERVER_VERSION = "1.0.0"

TOOL_SCHEMAS = [
    {
        "name": "network_monitor_health",
        "description": "Check network monitor health",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "network_list_interfaces",
        "description": "List network interfaces",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "network_capture_start",
        "description": "Start network capture",
        "inputSchema": {
            "type": "object",
            "properties": {
                "interface": {"type": "string"},
                "filter": {"type": "string"}
            },
            "additionalProperties": True
        }
    },
    {
        "name": "network_capture_stop",
        "description": "Stop network capture",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "network_capture_status",
        "description": "Get network capture status",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "network_threat_list",
        "description": "List network threats",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "network_threat_get",
        "description": "Get network threat details",
        "inputSchema": {
            "type": "object",
            "properties": {"threat_id": {"type": "string"}},
            "additionalProperties": True
        }
    },
    {
        "name": "network_firewall_block",
        "description": "Add firewall block rule",
        "inputSchema": {
            "type": "object",
            "properties": {"address": {"type": "string"}, "port": {"type": "integer"}},
            "additionalProperties": True
        }
    },
    {
        "name": "network_firewall_unblock",
        "description": "Remove firewall block rule",
        "inputSchema": {
            "type": "object",
            "properties": {"address": {"type": "string"}, "port": {"type": "integer"}},
            "additionalProperties": True
        }
    },
    {
        "name": "network_firewall_list_rules",
        "description": "List firewall rules",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}
    },
    {
        "name": "network_firewall_remove_rule",
        "description": "Remove firewall rule",
        "inputSchema": {
            "type": "object",
            "properties": {"rule_id": {"type": "string"}},
            "additionalProperties": True
        }
    }
]


def handle_network_monitor_health(args):
    return {"content": [{"type": "text", "text": json.dumps({"status": "healthy", "server": SERVER_NAME})}]}


def handle_network_list_interfaces(args):
    try:
        import subprocess
        result = subprocess.run(
            ["ip", "addr"],
            capture_output=True,
            text=True
        )
        interfaces = result.stdout if result.returncode == 0 else ""
        return {"content": [{"type": "text", "text": json.dumps({"status": "success", "interfaces": interfaces})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}


def handle_network_capture_start(args):
    interface = args.get("interface", "")
    filter_text = args.get("filter", "")
    return {"content": [{"type": "text", "text": json.dumps({"status": "simulated", "interface": interface, "filter": filter_text})}]}


def handle_network_capture_stop(args):
    return {"content": [{"type": "text", "text": json.dumps({"status": "simulated", "capture_stopped": True})}]}


def handle_network_capture_status(args):
    return {"content": [{"type": "text", "text": json.dumps({"status": "simulated", "running": False})}]}


def handle_network_threat_list(args):
    return {"content": [{"type": "text", "text": json.dumps({"status": "simulated", "threats": []})}]}


def handle_network_threat_get(args):
    threat_id = args.get("threat_id", "")
    return {"content": [{"type": "text", "text": json.dumps({"status": "simulated", "threat_id": threat_id})}]}


def handle_network_firewall_block(args):
    address = args.get("address", "")
    port = args.get("port", 0)
    return {"content": [{"type": "text", "text": json.dumps({"status": "simulated", "blocked": f"{address}:{port}"})}]}


def handle_network_firewall_unblock(args):
    address = args.get("address", "")
    port = args.get("port", 0)
    return {"content": [{"type": "text", "text": json.dumps({"status": "simulated", "unblocked": f"{address}:{port}"})}]}


def handle_network_firewall_list_rules(args):
    return {"content": [{"type": "text", "text": json.dumps({"status": "simulated", "rules": []})}]}


def handle_network_firewall_remove_rule(args):
    rule_id = args.get("rule_id", "")
    return {"content": [{"type": "text", "text": json.dumps({"status": "simulated", "removed": rule_id})}]}


HANDLERS = {
    "network_monitor_health": handle_network_monitor_health,
    "network_list_interfaces": handle_network_list_interfaces,
    "network_capture_start": handle_network_capture_start,
    "network_capture_stop": handle_network_capture_stop,
    "network_capture_status": handle_network_capture_status,
    "network_threat_list": handle_network_threat_list,
    "network_threat_get": handle_network_threat_get,
    "network_firewall_block": handle_network_firewall_block,
    "network_firewall_unblock": handle_network_firewall_unblock,
    "network_firewall_list_rules": handle_network_firewall_list_rules,
    "network_firewall_remove_rule": handle_network_firewall_remove_rule,
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