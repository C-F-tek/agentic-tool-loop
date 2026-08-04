"""Reranker manager for agentic loop MCP server.

This module extracts reranker management logic from agentic_loop_client_mcp_server.py
into a reusable, testable reranker management layer.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from .endpoint_validation import DEFAULT_RERANKER_PORT


class RerankerManagerError(Exception):
    """Exception raised when reranker management fails."""
    pass


class RerankerManager:
    """Manages OVMS BGE reranker processes.
    
    Handles reranker startup, health checking, functional probing, and process metadata.
    """
    
    def __init__(self, root: Path):
        self.root = root
        self.services_root = root / "services"
        self.runtime_dir = root / "state" / "codex_bridge" / "agentic_loop_client"
    
    def start_reranker(
        self,
        ready_url: str,
        rerank_url: str,
        port: int = DEFAULT_RERANKER_PORT,
        script: Path | None = None,
        startup_timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        """Start OVMS BGE reranker process.
        
        Returns structured dict with ok field indicating success/failure.
        """
        if script is None:
            script = self.services_root / "ovms-reranker-npu.ps1"
        
        if not script.is_file():
            return {"ok": False, "error": "reranker_script_missing", "script": str(script)}
        
        if not self._path_is_under(script, self.services_root):
            return {
                "ok": False,
                "error": "reranker_script_outside_services_root",
                "script": str(script),
                "services_root": str(self.services_root.resolve(strict=False)),
            }
        
        runtime_dir = self.runtime_dir
        runtime_dir.mkdir(parents=True, exist_ok=True)
        log_path = runtime_dir / f"reranker-{port}.log"
        
        command = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ]
        
        env = os.environ.copy()
        env.update({
            "RAG_EXTERNAL_RERANKER_URL": rerank_url,
            "AICARMINE_RAG_RERANK_URL": rerank_url,
            "AICARMINE_CONTROLLER_RAG_RERANK_URL": rerank_url,
            "AICARMINE_RAG_RERANK_READY_URL": ready_url,
        })
        
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        log_handle = log_path.open("a", encoding="utf-8", errors="replace")
        try:
            process = subprocess.Popen(
                command,
                cwd=str(script.parent),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=creationflags,
            )
        finally:
            log_handle.close()
        
        deadline = time.monotonic() + max(1, startup_timeout_seconds)
        last_health: dict[str, Any] = {}
        last_functional_probe: dict[str, Any] = {}
        
        while time.monotonic() < deadline:
            exit_code = process.poll()
            if exit_code is not None:
                return {
                    "ok": False,
                    "error": "reranker_process_exited_during_startup",
                    "pid": process.pid,
                    "exit_code": exit_code,
                    "command": command,
                    "cwd": str(script.parent),
                    "log_path": str(log_path),
                    "log_tail": self._tail_text(log_path),
                }
            
            health = self._get_health(ready_url)
            last_health = health
            
            if health.get("ok") is True:
                functional_probe = self._probe_reranker_functional(rerank_url)
                last_functional_probe = functional_probe
                
                if functional_probe.get("ok") is not True:
                    time.sleep(1.0)
                    continue
                
                return {
                    "ok": True,
                    "started": True,
                    "pid": process.pid,
                    "command": command,
                    "cwd": str(script.parent),
                    "port": port,
                    "ready_url": ready_url,
                    "rerank_url": rerank_url,
                    "script": str(script),
                    "log_path": str(log_path),
                    "health": health,
                    "functional_probe": functional_probe,
                }
            
            time.sleep(1.0)
        
        return {
            "ok": False,
            "error": "reranker_startup_timeout",
            "pid": process.pid,
            "command": command,
            "cwd": str(script.parent),
            "port": port,
            "ready_url": ready_url,
            "script": str(script),
            "log_path": str(log_path),
            "log_tail": self._tail_text(log_path),
            "last_health": last_health,
            "last_functional_probe": last_functional_probe,
        }
    
    def check_functional(self, rerank_url: str) -> dict[str, Any]:
        """Run functional probe against reranker."""
        started = time.monotonic()
        marker = "aicarmine_codex_mcp_reranker_functional_probe"
        payload = {
            "model": "BAAI/bge-reranker-v2-m3",
            "query": f"{marker} planner validator tool surface",
            "documents": [
                f"{marker} planner validator tool surface evidence {index}"
                for index in range(4)
            ],
        }
        
        response = self._http_json(method="POST", url=rerank_url, payload=payload)
        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        
        if response.get("ok") is not True:
            return {
                "ok": False,
                "error": "reranker_functional_probe_failed",
                "elapsed_ms": elapsed_ms,
                "response": response,
            }
        
        payload_value = response.get("payload") if isinstance(response.get("payload"), dict) else {}
        results = payload_value.get("results") if isinstance(payload_value, dict) else None
        
        if not isinstance(results, list) or not results:
            return {
                "ok": False,
                "error": "reranker_functional_probe_no_scores",
                "elapsed_ms": elapsed_ms,
                "response": response,
            }
        
        return {
            "ok": True,
            "elapsed_ms": elapsed_ms,
            "input_count": len(payload["documents"]),
            "returned_scores": len(results),
            "first_result": results[0],
        }
    
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
    
    def _http_json(self, method: str, url: str, payload: dict | None = None) -> dict[str, Any]:
        """Internal HTTP JSON request handler."""
        import httpx
        body = None
        headers = {"User-Agent": "aicarmine-codex-mcp", "Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            headers["Content-Type"] = "application/json"
        
        try:
            with httpx.Client(timeout=30) as client:
                response = client.request(method=method, url=url, data=body, headers=headers)
                raw = response.read()
                text = raw.decode("utf-8", errors="replace")
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = {"_raw_text": text}
                return {
                    "ok": True,
                    "http_status": response.status_code,
                    "url": url,
                    "payload": parsed,
                }
        except Exception as exc:
            return {
                "ok": False,
                "error": "request_failed",
                "url": url,
                "error_type": type(exc).__name__,
                "message": str(exc)[:2000],
            }
    
    def _probe_reranker_functional(self, rerank_url: str) -> dict[str, Any]:
        """Functional probe for reranker."""
        return self.check_functional(rerank_url)
    
    def _tail_text(self, path: Path, max_chars: int = 4000) -> str:
        """Read tail of file."""
        try:
            if not path.is_file():
                return ""
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        if len(text) <= max_chars:
            return text
        return text[-max_chars:]
    
    def _path_is_under(self, path: Path, parent: Path) -> bool:
        """Check if path is under parent directory."""
        try:
            path.resolve(strict=False).relative_to(parent.resolve(strict=False))
            return True
        except ValueError:
            return False