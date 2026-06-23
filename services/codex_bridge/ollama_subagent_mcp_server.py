#!/usr/bin/env python3
"""MCP server for parallel Ollama subagent task execution on Vulkan GPU port 11435."""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any
from collections import OrderedDict

from repo_mcp_common import (
    ToolSpec,
    handle_request,
    health_payload,
    object_schema,
    serve,
)

SERVER_NAME = "aicarmine-ollama-subagent-mcp"
SERVER_VERSION = "1.0.0"

# Default model for the Vulkan GPU Ollama instance on port 11435
# Override with OLLAMA_SUBAGENT_MODEL environment variable or via mcp.json env
DEFAULT_VULKAN_MODEL = "qwen3-task-8k:latest"


# ---------------------------------------------------------------------------
# Ollama Subagent Manager
# ---------------------------------------------------------------------------

class OllamaSubagentManager:
    """Manages parallel Ollama subagent tasks via the Vulkan GPU Ollama instance."""

    def __init__(self, repo_root: str, ollama_url: str = "http://127.0.0.1:11435") -> None:
        self.repo_root = Path(repo_root)
        self.ollama_url = ollama_url.rstrip("/")
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._max_cache_entries = 50

    def health(self) -> dict[str, Any]:
        """Check Ollama connectivity and list available models."""
        try:
            req = urllib.request.Request(f"{self.ollama_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = [m["name"] for m in data.get("models", [])] if isinstance(data, dict) else []
            return {
                "ok": True,
                "ollama_url": self.ollama_url,
                "model_count": len(models),
                "models": models[:20],
            }
        except Exception as e:
            return {
                "ok": False,
                "ollama_url": self.ollama_url,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    def generate(
        self,
        prompt: str,
        model: str = "",
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Generate a completion from the Vulkan GPU Ollama instance (port 11435)."""
        if not model:
            model = os.environ.get("OLLAMA_SUBAGENT_MODEL", DEFAULT_VULKAN_MODEL)

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
            "think": False,
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.ollama_url}/api/chat",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))

            content = response_data.get("message", {}).get("content", "")
            cache_key = f"{model}:{hash(prompt)}"
            self._cache[cache_key] = {"content": content, "model": model}
            if len(self._cache) > self._max_cache_entries:
                self._cache.pop(next(iter(self._cache)) if self._cache else None)

            return {
                "ok": True,
                "model": model,
                "ollama_url": self.ollama_url,
                "content": content,
                "cache_key": cache_key,
            }
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "model": model,
                "ollama_url": self.ollama_url,
            }

    def generate_stream(
        self,
        prompt: str,
        model: str = "",
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Generate a streaming completion from the Vulkan GPU Ollama instance."""
        if not model:
            model = os.environ.get("OLLAMA_SUBAGENT_MODEL", DEFAULT_VULKAN_MODEL)

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
            "think": False,
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.ollama_url}/api/chat",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8")
                lines = raw.split("\n")
                chunks = []
                full_content = ""
                for line in lines:
                    if line.strip():
                        try:
                            chunk = json.loads(line)
                            msg = chunk.get("message", {})
                            content = msg.get("content", "")
                            chunks.append(content)
                            full_content += content
                        except json.JSONDecodeError:
                            continue

            cache_key = f"{model}:stream:{hash(prompt)}"
            self._cache[cache_key] = {"content": full_content, "model": model}
            if len(self._cache) > self._max_cache_entries:
                self._cache.pop(next(iter(self._cache)) if self._cache else None)

            return {
                "ok": True,
                "model": model,
                "ollama_url": self.ollama_url,
                "content": full_content,
                "chunks": chunks[:100],
                "chunk_count": len(chunks),
                "stream": True,
                "cache_key": cache_key,
            }
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "model": model,
                "ollama_url": self.ollama_url,
            }

    def list_models(self) -> dict[str, Any]:
        """List all available Ollama models on the Vulkan GPU instance."""
        try:
            req = urllib.request.Request(f"{self.ollama_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = data.get("models", []) if isinstance(data, dict) else []
            return {
                "ok": True,
                "ollama_url": self.ollama_url,
                "model_count": len(models),
                "models": [
                    {
                        "name": m.get("name", ""),
                        "size": m.get("size", ""),
                        "model": m.get("model", ""),
                        "modified_at": m.get("modified_at", ""),
                    }
                    for m in models[:50]
                ],
            }
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "ollama_url": self.ollama_url,
            }


# Module-level singleton
_subagent_manager: OllamaSubagentManager | None = None
_lock = threading.Lock()


def _get_subagent_manager(repo_root: str) -> OllamaSubagentManager:
    global _subagent_manager
    if _subagent_manager is None:
        with _lock:
            if _subagent_manager is None:
                ollama_url = os.environ.get("OLLAMA_SUBAGENT_URL", "http://127.0.0.1:11435")
                _subagent_manager = OllamaSubagentManager(repo_root, ollama_url)
    return _subagent_manager


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        payload = health_payload(SERVER_NAME, list(tools))
        manager = _get_subagent_manager(str(root))
        health_result = manager.health()
        payload["ollama_subagent"] = {
            "enabled": True,
            "ollama_url": manager.ollama_url,
            "default_model": os.environ.get("OLLAMA_SUBAGENT_MODEL", DEFAULT_VULKAN_MODEL),
            "health_ok": health_result.get("ok") is True,
        }
        return payload

    tools["aicarmine_ollama_subagent_health"] = ToolSpec(
        name="aicarmine_ollama_subagent_health",
        description="Report Ollama subagent MCP health and Vulkan GPU connectivity.",
        input_schema=object_schema(),
        handler=health,
    )

    tools["aicarmine_ollama_subagent_generate"] = ToolSpec(
        name="aicarmine_ollama_subagent_generate",
        description="Generate a completion from the Vulkan GPU Ollama instance (port 11435).",
        input_schema=object_schema({
            "prompt": {"type": "string"},
            "model": {"type": "string", "default": ""},
            "system": {"type": "string", "default": ""},
            "max_tokens": {"type": "integer", "default": 4096, "minimum": 1, "maximum": 32768},
            "temperature": {"type": "number", "default": 0.1, "minimum": 0.0, "maximum": 2.0},
        }, required=["prompt"]),
        handler=lambda args, root: _get_subagent_manager(str(root)).generate(
            prompt=args["prompt"],
            model=args.get("model", ""),
            system=args.get("system", ""),
            max_tokens=args.get("max_tokens", 4096),
            temperature=args.get("temperature", 0.1),
        ),
    )

    tools["aicarmine_ollama_subagent_generate_stream"] = ToolSpec(
        name="aicarmine_ollama_subagent_generate_stream",
        description="Stream a completion from the Vulkan GPU Ollama instance (port 11435).",
        input_schema=object_schema({
            "prompt": {"type": "string"},
            "model": {"type": "string", "default": ""},
            "system": {"type": "string", "default": ""},
            "max_tokens": {"type": "integer", "default": 4096, "minimum": 1, "maximum": 32768},
            "temperature": {"type": "number", "default": 0.1, "minimum": 0.0, "maximum": 2.0},
        }, required=["prompt"]),
        handler=lambda args, root: _get_subagent_manager(str(root)).generate_stream(
            prompt=args["prompt"],
            model=args.get("model", ""),
            system=args.get("system", ""),
            max_tokens=args.get("max_tokens", 4096),
            temperature=args.get("temperature", 0.1),
        ),
    )

    tools["aicarmine_ollama_subagent_list_models"] = ToolSpec(
        name="aicarmine_ollama_subagent_list_models",
        description="List all available Ollama models on the Vulkan GPU instance.",
        input_schema=object_schema(),
        handler=lambda args, root: _get_subagent_manager(str(root)).list_models(),
    )

    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    if "--self-test" in argv:
        print(json.dumps({"ok": True, "server": SERVER_NAME, "tool_count": len(tools)}, ensure_ascii=False))
        return 0
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())