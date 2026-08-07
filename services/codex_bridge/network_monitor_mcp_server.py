#!/usr/bin/env python3
"""Network Monitor & Firewall MCP Server

Provides tools for real-time network packet capture, threat detection,
and automatic Windows firewall rule creation.

Tools:
- network_monitor_health: Report server health
- network_list_interfaces: List available network interfaces
- network_capture_start: Start packet capture with threat detection
- network_capture_stop: Stop active capture
- network_capture_status: Get capture status
- network_threat_list: List detected threats
- network_threat_get: Get details on a specific threat
- network_firewall_block: Block an IP address via firewall rule
- network_firewall_unblock: Remove a firewall block rule
- network_firewall_list_rules: List all firewall block rules
- network_firewall_remove_rule: Remove a specific firewall rule
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, BinaryIO, Callable

try:
    from scapy.all import (
        ARP,
        DNS,
        Ether,
        IP,
        Packet,
        TCP,
        UDP,
        ICMP,
        sniff,
        ls,
        conf,
    )
except ImportError:
    print("WARNING: scapy not installed. Install with: pip install scapy")

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    handle_request,
    serve,
)


def _string_prop(default: str = "") -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default:
        schema["default"] = default
    return schema


def _integer_prop(default: int, minimum: int = 0) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum}


def _boolean_prop(default: bool) -> dict[str, Any]:
    return {"type": "boolean", "default": default}

# ============================================================================
# Configuration
# ============================================================================

SERVER_NAME = "aicarmine-network-monitor-mcp"
SERVER_VERSION = "0.1.0"

DEFAULT_DURATION = 60
DEFAULT_THRESHOLD = 20
BLOCK_DAYS = 120

# Detection thresholds
THRESHOLD_SYN_PER_SEC = 50
THRESHOLD_UNIQUE_PORTS = 10
THRESHOLD_TIME_WINDOW = 10

# ============================================================================
# Global State
# ============================================================================

class CaptureState:
    """Manages packet capture state."""
    def __init__(self):
        self.lock = Lock()
        self.running = False
        self.stop_event = Event()
        self.interface = ""
        self.duration = 0
        self.threshold = DEFAULT_THRESHOLD
        self.packets_count = 0
        self.threats_detected = []
        self.blocked_ips = []
        self.start_time = 0

capture_state = CaptureState()

# ============================================================================
# Network Interface Tools
# ============================================================================

def list_interfaces_handler(arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    """List available network interfaces."""
    try:
        # Use PowerShell to get network interfaces
        ps_script = '''
Get-NetIPAddress | Where-Object {$_.AddressFamily -eq 2} | Select-Object InterfaceAlias, IPAddress | Format-Table -AutoSize
'''
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=15,
        )
        
        # Parse output
        lines = result.stdout.strip().split('\n')
        interfaces = []
        header_found = False
        for line in lines:
            if 'InterfaceAlias' in line and '---' in line:
                header_found = True
                continue
            if header_found and line.strip():
                parts = line.split()
                if len(parts) >= 2:
                    interfaces.append({
                        "name": parts[0],
                        "ip": parts[1] if len(parts) > 1 else "",
                    })
        
        return {
            "ok": True,
            "interfaces": interfaces,
            "count": len(interfaces),
            "selected": capture_state.interface if capture_state.running else None,
            "ps_output": result.stdout,
            "ps_error": result.stderr if result.stderr else None,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "tool": "network_list_interfaces",
        }

# ============================================================================
# Capture Tools
# ============================================================================

def capture_start_handler(arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    """Start packet capture with threat detection."""
    interface = arguments.get("interface", "")
    duration = int(arguments.get("duration", DEFAULT_DURATION))
    threshold = int(arguments.get("threshold", DEFAULT_THRESHOLD))
    
    if not interface:
        return {
            "ok": False,
            "error": "missing_required_argument",
            "tool": "network_capture_start",
            "message": "interface is required",
            "required": ["interface"],
        }
    
    # Check if already running
    with capture_state.lock:
        if capture_state.running:
            return {
                "ok": False,
                "error": "capture_already_running",
                "tool": "network_capture_start",
                "message": f"Capture already running on interface '{capture_state.interface}'",
            }
    
    # Verify interface exists using PowerShell
    try:
        ps_script = f'''
Get-NetIPAddress | Where-Object {{$_.InterfaceAlias -like "{interface}*"}} | Select-Object InterfaceAlias | Format-Table -AutoSize
'''
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=15,
        )
        
        # Check if interface is valid by looking for it in output
        if "Wi-Fi" in result.stdout or interface in result.stdout:
            pass  # Interface exists
        elif "No matching" in result.stdout or "not found" in result.stdout.lower():
            return {
                "ok": False,
                "error": "interface_not_found",
                "tool": "network_capture_start",
                "message": f"Interface '{interface}' not found",
                "ps_output": result.stdout,
            }
    except Exception as e:
        return {
            "ok": False,
            "error": "interface_check_failed",
            "tool": "network_capture_start",
            "message": str(e),
        }
    
    # Use scapy-compatible interface name
    scapy_interface = interface
    
    # Start capture in background thread
    capture_state.interface = interface
    capture_state.duration = duration
    capture_state.threshold = threshold
    capture_state.stop_event.clear()
    
    def capture_thread():
        """Background thread for packet capture."""
        stats = {
            "packets_total": 0,
            "bytes_total": 0,
            "tcp_count": 0,
            "udp_count": 0,
            "dns_count": 0,
            "arp_count": 0,
            "icmp_count": 0,
            "syn_count": 0,
            "ack_count": 0,
            "per_src_ip": {},
            "per_port": {},
        }
        
        ip_stats = {}
        
        def packet_callback(pkt):
            if capture_state.stop_event.is_set():
                return
            
            stats["packets_total"] += 1
            stats["bytes_total"] += len(pkt)
            
            if pkt.haslayer(TCP):
                stats["tcp_count"] += 1
                flags = pkt[TCP].flags
                if flags & 0x02:
                    stats["syn_count"] += 1
                if flags & 0x10:
                    stats["ack_count"] += 1
                
                src_ip = pkt[IP].src if pkt.haslayer(IP) else ""
                dst_port = pkt[TCP].dport if pkt.haslayer(TCP) else 0
                
                stats["per_src_ip"][src_ip] = stats["per_src_ip"].get(src_ip, 0) + 1
                stats["per_port"][dst_port] = stats["per_port"].get(dst_port, 0) + 1
                
                # Threat detection
                if src_ip not in ip_stats:
                    ip_stats[src_ip] = {
                        "packets": 0,
                        "syn": 0,
                        "ports_target": {},
                        "first_seen": time.time(),
                    }
                
                ip_stats[src_ip]["packets"] += 1
                ip_stats[src_ip]["last_seen"] = time.time()
                
                if flags & 0x02:
                    ip_stats[src_ip]["syn"] += 1
                    ip_stats[src_ip]["ports_target"][dst_port] = (
                        ip_stats[src_ip]["ports_target"].get(dst_port, 0) + 1
                    )
                
                # Check for port scanning
                elapsed = time.time() - ip_stats[src_ip]["first_seen"]
                unique_ports = len(ip_stats[src_ip]["ports_target"])
                
                if unique_ports > THRESHOLD_UNIQUE_PORTS and elapsed < THRESHOLD_TIME_WINDOW:
                    threat = {
                        "ip": src_ip,
                        "type": "PORT_SCAN",
                        "details": f"{unique_ports} ports in {elapsed:.1f}s",
                        "timestamp": datetime.now().isoformat(),
                        "evidence": {
                            "ports": list(ip_stats[src_ip]["ports_target"].keys())[:20],
                            "packet_count": ip_stats[src_ip]["packets"],
                        }
                    }
                    # Store threat in global capture_state
                    capture_state.threats_detected.append(threat)
                    
                    # Auto-block
                    blocked = firewall_block_ip(src_ip, threat, root)
                    if blocked.get("ok"):
                        capture_state.blocked_ips.append(src_ip)
                
                # Check for SYN flood
                syn_rate = ip_stats[src_ip]["syn"] / elapsed if elapsed > 0 else 0
                if syn_rate > THRESHOLD_SYN_PER_SEC:
                    threat = {
                        "ip": src_ip,
                        "type": "SYN_FLOOD",
                        "rate": f"{syn_rate:.1f} SYN/sec",
                        "timestamp": datetime.now().isoformat(),
                        "evidence": {
                            "syn_count": ip_stats[src_ip]["syn"],
                            "packet_count": ip_stats[src_ip]["packets"],
                        }
                    }
                    # Store threat in global capture_state
                    capture_state.threats_detected.append(threat)
                    
                    blocked = firewall_block_ip(src_ip, threat, root)
                    if blocked.get("ok"):
                        capture_state.blocked_ips.append(src_ip)
        
        try:
            sniff(
                iface=interface,
                timeout=duration,
                prn=packet_callback,
                store=False,
                stop_filter=lambda: capture_state.stop_event.is_set(),
            )
        except Exception as e:
            with capture_state.lock:
                capture_state.threats_detected.append({"error": str(e)})
        
        # Update global state with final stats
        with capture_state.lock:
            capture_state.packets_count = stats["packets_total"]
    
    # Start thread
    thread = Thread(target=capture_thread, daemon=True)
    thread.start()
    
    with capture_state.lock:
        capture_state.running = True
        capture_state.start_time = time.time()
    
    return {
        "ok": True,
        "message": f"Capture started on '{interface}' for {duration}s",
        "interface": interface,
        "duration": duration,
        "threshold": threshold,
        "thread_id": thread.ident,
    }

def capture_stop_handler(arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    """Stop active packet capture."""
    with capture_state.lock:
        if not capture_state.running:
            return {
                "ok": False,
                "error": "no_capture_running",
                "tool": "network_capture_stop",
                "message": "No active capture to stop",
            }
        
        capture_state.stop_event.set()
        capture_state.running = False
        
        # Get results
        result = {
            "ok": True,
            "message": "Capture stopped",
            "interface": capture_state.interface,
            "duration_seconds": time.time() - capture_state.start_time if capture_state.start_time else 0,
            "threats_detected": len(capture_state.threats_detected),
            "blocked_ips": len(capture_state.blocked_ips),
        }
        
        return result

def capture_status_handler(arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    """Get capture status."""
    with capture_state.lock:
        if capture_state.running:
            elapsed = time.time() - capture_state.start_time
            remaining = capture_state.duration - elapsed
            return {
                "ok": True,
                "running": True,
                "interface": capture_state.interface,
                "elapsed_seconds": round(elapsed, 1),
                "remaining_seconds": round(max(0, remaining), 1),
                "threshold": capture_state.threshold,
            }
        else:
            return {
                "ok": True,
                "running": False,
                "message": "No active capture",
            }

# ============================================================================
# Threat Detection Tools
# ============================================================================

def threat_list_handler(arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    """List detected threats."""
    limit = int(arguments.get("limit", 50))
    
    threats = capture_state.threats_detected[-limit:] if capture_state.threats_detected else []
    
    return {
        "ok": True,
        "threats": threats,
        "total": len(capture_state.threats_detected),
        "shown": len(threats),
    }

def threat_get_handler(arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    """Get details on a specific threat."""
    ip = arguments.get("ip", "")
    threat_type = arguments.get("type", "")
    
    if not ip:
        return {
            "ok": False,
            "error": "missing_required_argument",
            "tool": "network_threat_get",
            "message": "ip is required",
            "required": ["ip"],
        }
    
    threats = [t for t in capture_state.threats_detected if t.get("ip") == ip]
    
    return {
        "ok": True,
        "ip": ip,
        "threats": threats,
        "count": len(threats),
    }

# ============================================================================
# Firewall Tools
# ============================================================================

def firewall_block_ip(ip: str, threat: dict, root: Path) -> dict[str, Any]:
    """Block an IP address via Windows firewall."""
    try:
        rule_name = f"Block-{ip.replace('.', '-')}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        start_time = datetime.now()
        end_time = start_time + timedelta(days=BLOCK_DAYS)
        
        ps_script = f'''
$ruleName = "{rule_name}"
$ipAddress = "{ip}"
$description = "Blocked by Network Monitor: {threat.get('type', 'Unknown')} - {threat.get('details', '')}"
$start = "{start_time.strftime('%Y-%m-%dT%H:%M:%S')}"
$end = "{end_time.strftime('%Y-%m-%dT%H:%M:%S')}"

New-NetFirewallRule -DisplayName $ruleName `
    -Direction Inbound `
    -Action Block `
    -RemoteAddress $ipAddress `
    -Description $description `
    -Enabled True `
    -Profile Any 2>&1

Write-Output "OK"
'''
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode == 0 or "OK" in result.stdout:
            return {
                "ok": True,
                "ip": ip,
                "rule_name": rule_name,
                "reason": f"{threat.get('type')}: {threat.get('details')}",
                "created_at": start_time.isoformat(),
                "expires_at": end_time.isoformat(),
                "days": BLOCK_DAYS,
            }
        else:
            return {
                "ok": False,
                "error": "firewall_rule_creation_failed",
                "ip": ip,
                "stderr": result.stderr,
            }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "ip": ip,
        }

def firewall_block_handler(arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    """Block an IP address via firewall."""
    ip = arguments.get("ip", "")
    reason = arguments.get("reason", "Manual block")
    
    if not ip:
        return {
            "ok": False,
            "error": "missing_required_argument",
            "tool": "network_firewall_block",
            "message": "ip is required",
            "required": ["ip"],
        }
    
    threat = {
        "ip": ip,
        "type": "MANUAL_BLOCK",
        "details": reason,
        "timestamp": datetime.now().isoformat(),
    }
    
    return firewall_block_ip(ip, threat, root)

def firewall_list_rules_handler(arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    """List all firewall block rules."""
    try:
        ps_script = r'''
$rules = Get-NetFirewallRule | Where-Object { $_.DisplayName -like "Block-*" } | Select-Object DisplayName, Description, Enabled, Direction, Action
foreach ($rule in $rules) {
    Write-Output "Rule: $($rule.DisplayName)"
    Write-Output "  Description: $($rule.Description)"
    Write-Output "  Enabled: $($rule.Enabled)"
    Write-Output "  Direction: $($rule.Direction)"
    Write-Output "  Action: $($rule.Action)"
    Write-Output "---"
}
if (($rules | Measure-Object).Count -eq 0) {
    Write-Output "No Block rules found."
}
'''
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        return {
            "ok": True,
            "output": result.stdout,
            "error": result.stderr if result.stderr else None,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }

def firewall_remove_rule_handler(arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    """Remove a specific firewall rule."""
    ip = arguments.get("ip", "")
    
    if not ip:
        return {
            "ok": False,
            "error": "missing_required_argument",
            "tool": "network_firewall_remove_rule",
            "message": "ip is required",
            "required": ["ip"],
        }
    
    try:
        pattern = f"Block-{ip.replace('.', '-')}-*"
        ps_script = f'''
$rules = Get-NetFirewallRule | Where-Object {{ $_.DisplayName -like "{pattern}" }}
foreach ($rule in $rules) {{
    Remove-NetFirewallRule -DisplayName $rule.DisplayName -Confirm:$false
    Write-Output "Removed: $($rule.DisplayName)"
}}
'''
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        return {
            "ok": True,
            "output": result.stdout,
            "removed_ip": ip,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }

# ============================================================================
# Health Tool
# ============================================================================

def health_handler(arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    """Report server health."""
    tools = [
        "network_monitor_health",
        "network_list_interfaces",
        "network_capture_start",
        "network_capture_stop",
        "network_capture_status",
        "network_threat_list",
        "network_threat_get",
        "network_firewall_block",
        "network_firewall_unblock",
        "network_firewall_list_rules",
        "network_firewall_remove_rule",
    ]
    
    return health_payload(SERVER_NAME, tools)

# ============================================================================
# Tool Registry
# ============================================================================

def string_prop_default(default: str = "") -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default:
        schema["default"] = default
    return schema

def integer_prop_default(default: int, minimum: int = 0) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "integer", "default": default, "minimum": minimum}
    return schema

# Tool specifications
TOOLS: dict[str, ToolSpec] = {
    "network_monitor_health": ToolSpec(
        name="network_monitor_health",
        description="Report network monitor MCP server health",
        input_schema=object_schema(),
        handler=health_handler,
    ),
    "network_list_interfaces": ToolSpec(
        name="network_list_interfaces",
        description="List available network interfaces for packet capture",
        input_schema=object_schema(),
        handler=list_interfaces_handler,
    ),
    "network_capture_start": ToolSpec(
        name="network_capture_start",
        description="Start real-time packet capture with automatic threat detection and firewall blocking",
        input_schema=object_schema({
            "interface": string_prop_default(),
            "duration": integer_prop_default(DEFAULT_DURATION, minimum=1),
            "threshold": integer_prop_default(DEFAULT_THRESHOLD, minimum=1),
        }, required=["interface"]),
        handler=capture_start_handler,
    ),
    "network_capture_stop": ToolSpec(
        name="network_capture_stop",
        description="Stop active packet capture",
        input_schema=object_schema(),
        handler=capture_stop_handler,
    ),
    "network_capture_status": ToolSpec(
        name="network_capture_status",
        description="Get current capture status",
        input_schema=object_schema(),
        handler=capture_status_handler,
    ),
    "network_threat_list": ToolSpec(
        name="network_threat_list",
        description="List detected threats from recent captures",
        input_schema=object_schema({
            "limit": integer_prop_default(50, minimum=1),
        }),
        handler=threat_list_handler,
    ),
    "network_threat_get": ToolSpec(
        name="network_threat_get",
        description="Get details on a specific threat by IP",
        input_schema=object_schema({
            "ip": string_prop_default(),
            "type": string_prop_default(),
        }, required=["ip"]),
        handler=threat_get_handler,
    ),
    "network_firewall_block": ToolSpec(
        name="network_firewall_block",
        description="Block an IP address via Windows firewall (120 days)",
        input_schema=object_schema({
            "ip": string_prop_default(),
            "reason": string_prop_default("Manual block"),
        }, required=["ip"]),
        handler=firewall_block_handler,
    ),
    "network_firewall_unblock": ToolSpec(
        name="network_firewall_unblock",
        description="Unblock (remove firewall rule for) an IP address",
        input_schema=object_schema({
            "ip": string_prop_default(),
        }, required=["ip"]),
        handler=firewall_remove_rule_handler,
    ),
    "network_firewall_list_rules": ToolSpec(
        name="network_firewall_list_rules",
        description="List all active firewall block rules",
        input_schema=object_schema(),
        handler=firewall_list_rules_handler,
    ),
    "network_firewall_remove_rule": ToolSpec(
        name="network_firewall_remove_rule",
        description="Remove a specific firewall block rule by IP",
        input_schema=object_schema({
            "ip": string_prop_default(),
        }, required=["ip"]),
        handler=firewall_remove_rule_handler,
    ),
}

# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    sys.exit(serve(SERVER_NAME, SERVER_VERSION, TOOLS))