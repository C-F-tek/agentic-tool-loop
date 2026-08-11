"""NVIDIA GPU capability probe."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .command import command_available, run_command


def build_gpu_probe(repo_root: Path, timeout_seconds: int, external: bool) -> dict[str, Any]:
    query = [
        "nvidia-smi",
        "--query-gpu=name,driver_version,memory.total",
        "--format=csv,noheader",
    ]
    result = run_command(query, timeout_seconds=timeout_seconds, cwd=repo_root, enabled=external)
    return {
        "lane": "gpu_nvidia",
        "command_available": command_available("nvidia-smi"),
        "probe_performed": external and command_available("nvidia-smi"),
        "provider_execution_performed": False,
        "generation_performed": False,
        "result": result,
    }
