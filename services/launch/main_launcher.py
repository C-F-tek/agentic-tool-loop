"""
services.launch.main_launcher
=============================
Unified launcher entry point for the Agentic Tool Loop runtime.

This module consolidates the functionality of the individual PowerShell launch
scripts into a single Python entry point that uses PortManager and JobLifecycle
from the services.runtime package.

Usage:
    python -m services.launch.main_launcher <command> [options]

Commands:
    start      - Start all required services in correct order
    stop       - Stop all running services gracefully
    status     - Show status of all services
    restart    - Restart all services
    health     - Check health of all services

Examples:
    python -m services.launch.main_launcher start
    python -m services.launch.main_launcher status
    python -m services.launch.main_launcher health
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from config import get_planner_config, load_port_config
from runtime import get_port_manager, get_job_lifecycle


class ServiceStatus:
    """Represents the status of a single service."""
    
    def __init__(self, name: str, port: int, pid: int = 0, running: bool = False, health: str = "unknown"):
        self.name = name
        self.port = port
        self.pid = pid
        self.running = running
        self.health = health
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "port": self.port,
            "pid": self.pid,
            "running": self.running,
            "health": self.health,
        }


class MainLauncher:
    """Unified launcher for all Agentic Tool Loop services."""
    
    # Service definitions - defined as class constants
    _SERVICE_PORTS: Dict[str, int] = {
        "ollama": 11434,
        "ovms_reranker": 3550,
        "vulkan_bridge": 3571,
        "broker": 3572,
        "agentic_loop": 3579,
    }
    
    _SERVICE_CONFIGS: Dict[str, Dict[str, Any]] = {
        "ollama": {
            "port": 11434,
            "command": ["ollama", "list"],
            "executable": "ollama",
            "startup_script": None,
            "health_url": "http://127.0.0.1:11434/api/tags",
        },
        "ovms_reranker": {
            "port": 3550,
            "command": ["python", "-u", "services/codex_bridge/ovms_mcp_server.py"],
            "executable": "python",
            "startup_script": "services/codex_bridge/ovms_mcp_server.py",
            "health_url": "http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready",
        },
        "vulkan_bridge": {
            "port": 3571,
            "command": ["python", "-u", "-m", "services.vulkan_bridge"],
            "executable": "python",
            "module": "services.vulkan_bridge",
            "health_url": "http://127.0.0.1:3571/health",
        },
        "broker": {
            "port": 3572,
            "command": ["python", "-u", "-m", "services.aicarmine_broker.app"],
            "executable": "python",
            "module": "services.aicarmine_broker.app",
            "health_url": "http://127.0.0.1:3572/health",
        },
        "agentic_loop": {
            "port": 3579,
            "command": ["python", "-u", "-m", "services.codex_bridge.agentic_loop_client_mcp_server"],
            "executable": "python",
            "module": "services.codex_bridge.agentic_loop_client_mcp_server",
            "health_url": "http://127.0.0.1:3579/health",
        },
    }
    
    # Startup order - dependencies must start first
    _STARTUP_ORDER: List[str] = [
        "ollama",
        "ovms_reranker",
        "vulkan_bridge",
        "broker",
        "agentic_loop",
    ]
    
    def __init__(self):
        """Initialize the launcher with runtime configuration."""
        self.port_config = load_port_config()
        self.port_manager = get_port_manager()
        self.job_lifecycle = get_job_lifecycle()
        self.services: Dict[str, ServiceStatus] = {}
        self._processes: Dict[str, subprocess.Popen] = {}
    
    def _find_python_executable(self) -> str:
        """Find the Python executable path."""
        python_path = os.getenv("AICARMINE_LAB_PYTHON", sys.executable)
        return python_path
    
    def _build_service_command(self, service_name: str) -> List[str]:
        """Build the full command for a service."""
        config = self._SERVICE_CONFIGS[service_name]
        cmd = list(config["command"])
        
        # Replace placeholder with actual Python path
        if cmd[0] == "python":
            python_exe = self._find_python_executable()
            cmd[0] = python_exe
        
        return cmd
    
    def start_all(self) -> dict[str, Any]:
        """Start all required services in correct order.
        
        Returns:
            Dictionary with keys: started, failed, errors
        """
        results = {"started": [], "failed": [], "errors": []}
        
        # Start services in dependency order
        for name in self._STARTUP_ORDER:
            try:
                config = self._SERVICE_CONFIGS[name]
                cmd = self._build_service_command(name)
                
                # Check if port is already in use
                if self.port_manager.is_port_up(config["port"]):
                    results["started"].append(name)
                    self.services[name] = ServiceStatus(
                        name, config["port"], running=True, health="already_running"
                    )
                    continue
                
                # Start the process
                process = subprocess.Popen(
                    cmd,
                    cwd=str(Path(__file__).parent.parent),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                
                self._processes[name] = process
                self.services[name] = ServiceStatus(
                    name, config["port"], process.pid, True, "starting"
                )
                results["started"].append(name)
                
                # Wait for service to be ready
                timeout = 60 if name == "ollama" else 30
                if not self.port_manager.wait_for_service(config["port"], timeout=timeout):
                    results["errors"].append(f"{name}: timed out waiting for port {config['port']}")
                    
            except Exception as e:
                results["failed"].append(name)
                results["errors"].append(f"{name}: {str(e)}")
        
        return results
    
    def stop_all(self) -> dict[str, Any]:
        """Stop all running services gracefully.
        
        Returns:
            Dictionary with keys: stopped, errors
        """
        results = {"stopped": [], "errors": []}
        
        # Stop in reverse dependency order
        for name in reversed(self._STARTUP_ORDER):
            process = self._processes.get(name)
            if process and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=10)
                    results["stopped"].append(name)
                except Exception as e:
                    try:
                        process.kill()
                        results["stopped"].append(name)
                    except Exception as e2:
                        results["errors"].append(f"{name}: {str(e2)}")
                    results["errors"].append(f"{name}: {str(e)}")
        
        self._processes.clear()
        return results
    
    def get_status(self) -> dict[str, Any]:
        """Get status of all services.
        
        Returns:
            Dictionary mapping service names to their status dicts
        """
        status = {}
        for name in self._STARTUP_ORDER:
            config = self._SERVICE_CONFIGS[name]
            service = self.services.get(name)
            if not service:
                service = ServiceStatus(name, config["port"])
            status[name] = service.to_dict()
        return status
    
    def check_health(self) -> dict[str, Any]:
        """Check health of all services.
        
        Returns:
            Dictionary mapping service names to health info
        """
        health = {}
        for name in self._STARTUP_ORDER:
            config = self._SERVICE_CONFIGS[name]
            port = config["port"]
            is_up = self.port_manager.is_port_up(port)
            health[name] = {
                "port": port,
                "up": is_up,
                "health": "healthy" if is_up else "unhealthy",
            }
        return health
    
    def wait_all_healthy(self, timeout: int = 120) -> bool:
        """Wait for all services to be healthy.
        
        Args:
            timeout: Maximum seconds to wait
            
        Returns:
            True if all healthy, False otherwise
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            health = self.check_health()
            if all(h.get("up", False) for h in health.values()):
                return True
            time.sleep(1)
        return False


def main():
    """Main entry point for the launcher."""
    parser = argparse.ArgumentParser(description="Agentic Tool Loop Launcher")
    parser.add_argument("command", choices=["start", "stop", "status", "restart", "health"])
    
    args = parser.parse_args()
    launcher = MainLauncher()
    
    if args.command == "start":
        result = launcher.start_all()
        print(json.dumps(result, indent=2))
    elif args.command == "stop":
        result = launcher.stop_all()
        print(json.dumps(result, indent=2))
    elif args.command == "status":
        result = launcher.get_status()
        print(json.dumps(result, indent=2))
    elif args.command == "health":
        result = launcher.check_health()
        print(json.dumps(result, indent=2))
    elif args.command == "restart":
        launcher.stop_all()
        time.sleep(2)
        result = launcher.start_all()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()