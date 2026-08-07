"""
Security MCP Server - Integrates all security monitoring tools
Provides MCP-compatible interface for file integrity, log anomaly detection,
and network monitoring tools.

Usage:
    echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "security_file_baseline", "arguments": {}}}' | python -u services\codex_bridge\security_mcp_server.py
"""

import json
import subprocess
import sys
import os
from datetime import datetime
from typing import Dict, Any, Optional

# Paths
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "useful_tools")
FILE_INTEGRITY_SCRIPT = os.path.join(SCRIPTS_DIR, "file_integrity_monitor.ps1")
LOG_ANOMALY_SCRIPT = os.path.join(SCRIPTS_DIR, "log_anomaly_detection.ps1")
NETWORK_MONITOR_SCRIPT = os.path.join(SCRIPTS_DIR, "..", "codex_bridge", "network_monitor_mcp_server.py")
OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "agentic-tool-loop", "output", "security")

SECURITY_TOOLS = [
    {
        "name": "security_file_baseline",
        "description": "Create file integrity baseline for critical system files",
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": True
        }
    },
    {
        "name": "security_file_check",
        "description": "Check file integrity against baseline",
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": True
        }
    },
    {
        "name": "security_security_report",
        "description": "Generate comprehensive security report",
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": True
        }
    },
    {
        "name": "security_log_baseline",
        "description": "Create anomaly detection baseline for security logs",
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": True
        }
    },
    {
        "name": "security_log_analyze",
        "description": "Analyze Windows security logs with local AI (Ollama)",
        "input_schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "default": "phi3:mini"},
                "ollama_url": {"type": "string", "default": "http://127.0.0.1:11434"}
            },
            "additionalProperties": True
        }
    },
    {
        "name": "security_network_capture",
        "description": "Start network packet capture with threat detection",
        "input_schema": {
            "type": "object",
            "properties": {
                "interface": {"type": "string"},
                "duration": {"type": "integer"},
                "threshold": {"type": "integer"}
            },
            "additionalProperties": True
        }
    },
    {
        "name": "security_threat_list",
        "description": "List detected threats from network monitoring",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"}
            },
            "additionalProperties": True
        }
    },
    {
        "name": "security_firewall_block",
        "description": "Block IP via Windows firewall (120 days)",
        "input_schema": {
            "type": "object",
            "properties": {
                "ip": {"type": "string"},
                "reason": {"type": "string"}
            },
            "additionalProperties": True
        }
    },
    {
        "name": "security_firewall_list_rules",
        "description": "List active firewall block rules",
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": True
        }
    },
    {
        "name": "security_full_scan",
        "description": "Run complete security scan (file integrity + log analysis + network)",
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": True
        }
    }
]


def run_powershell_script(script_path: str, action: str, extra_args: Optional[Dict] = None) -> Dict[str, Any]:
    """Run a PowerShell security script and return results."""
    if not os.path.exists(script_path):
        return {"error": f"Script not found: {script_path}"}
    
    cmd = ["powershell", "-Command", f"Set-Location 'C:\\Users\\sanit\\agentic-tool-loop'; & '{script_path}' -Action {action}"]
    if extra_args:
        for key, value in extra_args.items():
            cmd.extend([f"-{key}", str(value)])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        
        output = result.stdout or result.stderr or ""
        
        # Try to parse as JSON if possible
        try:
            json_output = json.loads(output)
            return {"powerShell_output": output, "json_result": json_output}
        except json.JSONDecodeError:
            return {"powerShell_output": output, "parsed": False}
    except Exception as e:
        return {"error": str(e)}


def call_network_mcp(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Call network monitor MCP server."""
    if not os.path.exists(NETWORK_MONITOR_SCRIPT):
        return {"error": "Network monitor script not found"}
    
    request = {
        "jsonrpc": "2.0",
        "id": 999,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }
    
    json_request = json.dumps(request)
    
    try:
        proc = subprocess.Popen(
            ["python", "-u", NETWORK_MONITOR_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        stdout, stderr = proc.communicate(input=json_request, timeout=30)
        
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"error": "Failed to parse network monitor response", "raw_output": stdout}
    except Exception as e:
        return {"error": f"Network monitor call failed: {str(e)}"}


def handle_security_file_baseline(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle file integrity baseline creation."""
    result = run_powershell_script(FILE_INTEGRITY_SCRIPT, "baseline")
    return result


def handle_security_file_check(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle file integrity check."""
    result = run_powershell_script(FILE_INTEGRITY_SCRIPT, "check")
    return result


def handle_security_security_report(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle security report generation."""
    result = run_powershell_script(FILE_INTEGRITY_SCRIPT, "report")
    return result


def handle_security_log_baseline(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle log anomaly baseline creation."""
    result = run_powershell_script(LOG_ANOMALY_SCRIPT, "baseline")
    return result


def handle_security_log_analyze(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle log anomaly analysis with Ollama."""
    model = arguments.get("model", "phi3:mini")
    ollama_url = arguments.get("ollama_url", "http://127.0.0.1:11434")
    result = run_powershell_script(LOG_ANOMALY_SCRIPT, "analyze")
    return result


def handle_security_network_capture(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle network capture start."""
    interface = arguments.get("interface", "Wi-Fi")
    duration = arguments.get("duration", 60)
    threshold = arguments.get("threshold", 2)
    
    return call_network_mcp("network_capture_start", {
        "interface": interface,
        "duration": duration,
        "threshold": threshold
    })


def handle_security_threat_list(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle threat list retrieval."""
    limit = arguments.get("limit", 50)
    return call_network_mcp("network_threat_list", {"limit": limit})


def handle_security_firewall_block(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle firewall IP blocking."""
    ip = arguments.get("ip", "")
    reason = arguments.get("reason", "Manual block")
    
    if not ip:
        return {"error": "IP address required"}
    
    return call_network_mcp("network_firewall_block", {
        "ip": ip,
        "reason": reason
    })


def handle_security_firewall_list_rules(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle firewall rules listing."""
    return call_network_mcp("network_firewall_list_rules", {})


def handle_security_full_scan(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Run complete security scan."""
    file_result = run_powershell_script(FILE_INTEGRITY_SCRIPT, "check")
    log_result = run_powershell_script(LOG_ANOMALY_SCRIPT, "analyze")
    network_result = call_network_mcp("network_threat_list", {"limit": 10})
    
    results = {
        "scan_time": datetime.now().isoformat(),
        "file_integrity": file_result,
        "log_analysis": log_result,
        "network_status": network_result
    }
    
    # Save full scan result
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, f"full_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    
    results["output_file"] = output_path
    return results


def handle_tools_call(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle tools/call method."""
    tool_name = arguments.get("name", "")
    tool_args = arguments.get("arguments", {})
    
    handlers = {
        "security_file_baseline": handle_security_file_baseline,
        "security_file_check": handle_security_file_check,
        "security_security_report": handle_security_security_report,
        "security_log_baseline": handle_security_log_baseline,
        "security_log_analyze": handle_security_log_analyze,
        "security_network_capture": handle_security_network_capture,
        "security_threat_list": handle_security_threat_list,
        "security_firewall_block": handle_security_firewall_block,
        "security_firewall_list_rules": handle_security_firewall_list_rules,
        "security_full_scan": handle_security_full_scan
    }
    
    handler = handlers.get(tool_name)
    if not handler:
        return {
            "error": f"Unknown tool: {tool_name}",
            "available_tools": list(handlers.keys())
        }
    
    result = handler(tool_args)
    return result


def main():
    """Main MCP server entry point."""
    try:
        input_data = sys.stdin.read()
        request = json.loads(input_data)
        
        method = request.get("method", "")
        tool_params = request.get("params", {})
        
        if method == "tools/call":
            tool_name = tool_params.get("name", "")
            tool_args = tool_params.get("arguments", {})
            
            if tool_name == "list":
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id", 1),
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(SECURITY_TOOLS)}]
                    }
                }
            else:
                result = handle_tools_call(tool_args)
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id", 1),
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, default=str)}]
                    }
                }
        elif method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": request.get("id", 1),
                "result": {
                    "protocolVersion": "2.0",
                    "capabilities": {},
                    "serverInfo": {
                        "name": "security-monitor",
                        "version": "1.0.0"
                    }
                }
            }
        else:
            response = {
                "jsonrpc": "2.0",
                "id": request.get("id", 1),
                "error": {"code": -32601, "message": "Method not found: " + method}
            }
        
        print(json.dumps(response))
        sys.stdout.flush()
        
    except Exception as e:
        error_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32700, "message": str(e)}
        }
        print(json.dumps(error_response))
        sys.stdout.flush()


if __name__ == "__main__":
    main()
