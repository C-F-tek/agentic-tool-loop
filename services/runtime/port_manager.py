# services/runtime/port_manager - Port management and process tracking
#
# This module provides port ownership tracking and service process management.
# It replaces the scattered process management in launch/*.ps1 scripts.
#
# All service process management must use this module instead of direct
# PowerShell process commands or ad-hoc port checks.

from __future__ import annotations

import subprocess
import psutil
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class ServiceProcess:
    """Represents a managed service process."""
    pid: int
    port: int
    process_name: str
    command_line: str
    venv: str = ""
    status: str = "running"  # running, stopped, error
    owner: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "pid": self.pid,
            "port": self.port,
            "process_name": self.process_name,
            "command_line": self.command_line,
            "venv": self.venv,
            "status": self.status,
            "owner": self.owner,
        }


class PortManager:
    """Port Manager.
    
    Tracks port ownership and manages service processes.
    """
    
    # Known service ports and their expected processes
    SERVICE_PORTS: dict[int, dict] = {
        3550: {"name": "OVMS Reranker", "process": "ovms.exe"},
        3571: {"name": "Vulkan Bridge", "process": "uvicorn"},
        3572: {"name": "Broker", "process": "uvicorn"},
        3579: {"name": "Agentic Loop Client", "process": "uvicorn"},
        11434: {"name": "Ollama Main", "process": "ollama.exe"},
        11435: {"name": "Ollama Task", "process": "ollama.exe"},
        3560: {"name": "Executor", "process": "uvicorn"},
        3551: {"name": "NPU Phi", "process": "uvicorn"},
        8080: {"name": "OpenWebUI", "process": "uvicorn"},
    }
    
    def __init__(self):
        self._cached_processes: dict[int, ServiceProcess] = {}
    
    def check_port_ownership(self, port: int) -> Optional[ServiceProcess]:
        """Check which process owns a given port.
        
        Returns ServiceProcess if a process is found, None otherwise.
        """
        # Check if this is a known service port
        if port not in self.SERVICE_PORTS:
            return None
        
        expected_process = self.SERVICE_PORTS[port]["process"]
        
        try:
            # Use PowerShell to get process ownership for the port
            ps_command = f'''
                $processId = (Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue).OwningProcess
                if ($processId) {{
                    $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
                    if ($proc) {{
                        Write-Output ($proc.Id + "|" + $proc.ProcessName + "|" + ($proc.CommandLine -replace '"', "'"))
                    }}
                }}
            '''
            result = subprocess.run(
                ["powershell", "-Command", ps_command],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.stdout.strip():
                parts = result.stdout.strip().split("|")
                if len(parts) >= 3:
                    pid = int(parts[0])
                    process_name = parts[1]
                    command_line = parts[2]
                    
                    service = ServiceProcess(
                        pid=pid,
                        port=port,
                        process_name=process_name,
                        command_line=command_line,
                        status="running",
                        owner=self.SERVICE_PORTS[port]["name"],
                    )
                    self._cached_processes[port] = service
                    return service
            
            return None
        
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            return None
    
    def check_all_ports(self) -> dict[int, ServiceProcess]:
        """Check ownership for all known service ports.
        
        Returns dict mapping port to ServiceProcess.
        """
        results = {}
        for port in self.SERVICE_PORTS:
            process = self.check_port_ownership(port)
            if process:
                results[port] = process
        return results
    
    def is_port_in_use(self, port: int) -> bool:
        """Check if a port is currently in use."""
        try:
            ps_command = f'''
                $conn = Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue
                if ($conn) {{ Write-Output "true" }} else {{ Write-Output "false" }}
            '''
            result = subprocess.run(
                ["powershell", "-Command", ps_command],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.strip() == "true"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def stop_process_by_port(self, port: int) -> bool:
        """Stop the process owning a given port.
        
        Returns True if process was stopped, False otherwise.
        """
        process = self.check_port_ownership(port)
        if not process:
            return False
        
        try:
            ps_command = f'Stop-Process -Id {process.pid} -Force'
            result = subprocess.run(
                ["powershell", "-Command", ps_command],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def get_service_status(self) -> dict:
        """Get status of all known services.
        
        Returns dict with service names and their status.
        """
        status = {}
        for port, info in self.SERVICE_PORTS.items():
            process = self.check_port_ownership(port)
            status[port] = {
                "name": info["name"],
                "port": port,
                "expected_process": info["process"],
                "is_running": process is not None,
                "pid": process.pid if process else None,
                "status": process.status if process else "stopped",
            }
        return status


# Module-level singleton
_port_manager: Optional[PortManager] = None

def get_port_manager() -> PortManager:
    """Get the global PortManager singleton."""
    global _port_manager
    if _port_manager is None:
        _port_manager = PortManager()
    return _port_manager


def check_port_ownership(port: int) -> Optional[ServiceProcess]:
    """Convenience function to check port ownership."""
    return get_port_manager().check_port_ownership(port)


def check_all_ports() -> dict[int, ServiceProcess]:
    """Convenience function to check all ports."""
    return get_port_manager().check_all_ports()


def get_service_status() -> dict:
    """Convenience function to get all service status."""
    return get_port_manager().get_service_status()