"""Ollama capability probe without generation."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .command import command_available, run_command


def build_ollama_probe(repo_root: Path, timeout_seconds: int, external: bool) -> dict[str, Any]:
    available = command_available("ollama")
    return {
        "lane": "ollama",
        "command_available": available,
        "generation_performed": False,
        "list": run_command(["ollama", "list"], timeout_seconds, cwd=repo_root, enabled=external),
        "ps": run_command(["ollama", "ps"], timeout_seconds, cwd=repo_root, enabled=external),
    }
