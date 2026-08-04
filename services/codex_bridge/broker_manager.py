"""Broker manager for agentic loop MCP server.

This module extracts broker management logic from agentic_loop_client_mcp_server.py
into a reusable, testable broker management layer.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from .endpoint_validation import RESERVED_PORTS, DEFAULT_AGENTIC_LOOP_PORT, safe_int


class BrokerManagerError(Exception):
    """Exception raised when broker management fails."""
    pass


class BrokerManager:
    """Manages dedicated agentic loop broker processes.
    
    Handles broker startup, health checking, process metadata, and source freshness.
    """
    
    def __init__(self, root: Path):
        self.root = root
        self.services_root = root / "services"
        self.runtime_dir = root / "state" / "codex_bridge" / "agentic_loop_client"
    
    def start_broker(
        self,
        port: int = DEFAULT_AGENTIC_LOOP_PORT,
        startup_timeout_seconds: int = 45,
        rerank_url: str = "",
        reranker_ready_url: str = "",
    ) -> dict[str, Any]:
        """Start a dedicated agentic loop broker process.
        
        Returns structured dict with ok field indicating success/failure.
        """
        if not self.services_root.is_dir():
            return {"ok": False, "error": "services_directory_missing", "path": str(self.services_root)}
        
        python_exe = self._select_python()
        if not python_exe.is_file():
            return {"ok": False, "error": "python_executable_missing", "python_executable": str(python_exe)}
        
        instance_dir = self.runtime_dir / f"port-{port}"
        instance_dir.mkdir(parents=True, exist_ok=True)
        workspace = instance_dir / "workspace"
        agent_job_root = workspace / "agent-jobs"
        agent_job_db = agent_job_root / "agent_jobs.sqlite3"
        log_path = instance_dir / f"agentic-loop-{port}.log"
        
        env = os.environ.copy()
        root_text = str(self.root.resolve(strict=False))
        env.update({
            "AICARMINE_LAB_REPO": root_text,
            "AICARMINE_REAL_REPO": root_text,
            "AICARMINE_CODEX_MCP_REPO_ROOT": root_text,
            "OPEN_TERMINAL_CWD": root_text,
            "AICARMINE_OPEN_TERMINAL_WORKDIR": root_text,
            "AICARMINE_VULKAN_WORKSPACE": str(workspace),
            "AICARMINE_AGENT_JOB_ROOT": str(agent_job_root),
            "AICARMINE_AGENT_JOB_DB": str(agent_job_db),
            "AICARMINE_AGENT_PUBLIC_BASE_URL": f"http://127.0.0.1:{port}",
            "AICARMINE_VULKAN_AGENT_URL": f"http://127.0.0.1:{port}/vulkan/agent",
            "AICARMINE_BROKER_SERVICE_NAME": f"aicarmine-codex-agentic-loop-{port}",
            "AICARMINE_BROKER_APP_TITLE": f"AI-Carmine Codex Agentic Loop {port}",
            "AICARMINE_BROKER_UVICORN_RELOAD": "0",
        })
        
        command = [
            str(python_exe),
            "-m",
            "uvicorn",
            "aicarmine_vulkan_tool_broker:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]
        
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        log_handle = log_path.open("a", encoding="utf-8", errors="replace")
        try:
            process = subprocess.Popen(
                command,
                cwd=str(self.services_root),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=creationflags,
            )
        finally:
            log_handle.close()
        
        self._write_process_metadata(port, process.pid, command, log_path)
        
        deadline = time.monotonic() + max(1, startup_timeout_seconds)
        last_health: dict[str, Any] = {}
        
        while time.monotonic() < deadline:
            exit_code = process.poll()
            if exit_code is not None:
                return {
                    "ok": False,
                    "error": "broker_process_exited_during_startup",
                    "pid": process.pid,
                    "exit_code": exit_code,
                    "command": command,
                    "log_path": str(log_path),
                }
            
            health_endpoint = f"http://127.0.0.1:{port}/health"
            health = self._get_health(health_endpoint)
            last_health = health
            
            if health.get("ok") is True:
                return {
                    "ok": True,
                    "started": True,
                    "pid": process.pid,
                    "command": command,
                    "port": port,
                    "workspace": str(workspace),
                    "agent_job_root": str(agent_job_root),
                    "agent_job_db": str(agent_job_db),
                    "log_path": str(log_path),
                    "health": health,
                }
            
            time.sleep(0.5)
        
        return {
            "ok": False,
            "error": "broker_startup_timeout",
            "pid": process.pid,
            "command": command,
            "port": port,
            "log_path": str(log_path),
            "last_health": last_health,
        }
    
    def check_source_freshness(self, port: int) -> dict[str, Any]:
        """Check if broker source files are newer than the running process."""
        metadata = self._read_process_metadata(port)
        if not metadata:
            return {"ok": True, "checked": False, "reason": "broker_process_metadata_missing"}
        
        if bool(metadata.get("reload")):
            return {
                "ok": False,
                "checked": True,
                "reload": True,
                "error": "broker_started_with_removed_reload",
                "fix": "Stop and restart the dedicated 3579 broker manually without uvicorn --reload.",
            }
        
        started_at = float(metadata.get("started_at_unix") or 0.0)
        if started_at <= 0:
            return {"ok": True, "checked": False, "reason": "broker_started_at_missing"}
        
        newest_mtime = 0.0
        newest_path = ""
        checked = 0
        
        for py_file in self._broker_source_files():
            try:
                mtime = py_file.stat().st_mtime
            except OSError:
                continue
            checked += 1
            if mtime > newest_mtime:
                newest_mtime = mtime
                newest_path = str(py_file)
        
        stale = bool(newest_mtime > started_at + 1.0)
        return {
            "ok": not stale,
            "checked": True,
            "started_at_unix": started_at,
            "newest_source_mtime_unix": newest_mtime,
            "newest_source_path": newest_path,
            "checked_source_file_count": checked,
            "metadata": metadata,
            **({"error": "broker_stale_code_possible", "fix": "Restart the 3579 broker manually."} if stale else {}),
        }
    
    def _select_python(self) -> Path:
        """Select Python executable with fallback chain."""
        env_python = os.environ.get("AICARMINE_LABTOOLS_PYTHON", "").strip()
        if env_python:
            candidate = Path(env_python).expanduser()
            if candidate.is_file():
                return candidate
        labtools_python = self.root / "venvs" / "labtools" / "Scripts" / "python.exe"
        if labtools_python.is_file():
            return labtools_python
        return Path(__import__("sys").executable)
    
    def _get_health(self, endpoint: str) -> dict[str, Any]:
        """GET health check."""
        import httpx
        try:
            response = httpx.get(endpoint, timeout=3)
            if response.status_code == 200:
                return {"ok": True, "http_status": response.status_code}
        except Exception as exc:
            return {"ok": False, "error": type(exc).__name__, "message": str(exc)[:200]}
        return {"ok": False, "http_status": response.status_code if 'response' in dir() else 0}
    
    def _broker_source_files(self) -> list[Path]:
        """List broker source files for freshness check."""
        candidates = [self.services_root / "aicarmine_vulkan_tool_broker.py"]
        for relative in ("aicarmine_broker", "vulkan_bridge"):
            base = self.services_root / relative
            if base.is_dir():
                candidates.extend(base.rglob("*.py"))
        out = []
        seen = set()
        for path in candidates:
            try:
                resolved = path.resolve(strict=False)
            except OSError:
                resolved = path
            key = str(resolved).lower()
            if key in seen or not path.is_file():
                continue
            seen.add(key)
            out.append(path)
        return out
    
    def _write_process_metadata(self, port: int, pid: int, command: list[str], log_path: Path) -> dict[str, Any]:
        """Write broker process metadata."""
        path = self.runtime_dir / f"port-{port}" / "broker-process.json"
        payload = {
            "service": "aicarmine-agentic-loop-client-mcp",
            "kind": "dedicated_agentic_loop_broker",
            "pid": pid,
            "port": port,
            "root": str(self.root.resolve(strict=False)),
            "command": command,
            "cwd": str(self.services_root),
            "reload": False,
            "log_path": str(log_path),
            "started_at_unix": time.time(),
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            return {"ok": False, "path": str(path), "error": type(exc).__name__}
        return {"ok": True, "path": str(path)}
    
    def _read_process_metadata(self, port: int) -> dict[str, Any]:
        """Read broker process metadata."""
        path = self.runtime_dir / f"port-{port}" / "broker-process.json"
        try:
            if not path.is_file():
                return {}
            parsed = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            return {}
        return parsed if isinstance(parsed, dict) else {}