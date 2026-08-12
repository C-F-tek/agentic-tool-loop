"""OpenVINO/NPU capability probe without model loading."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .command import run_command


def build_npu_probe(repo_root: Path, timeout_seconds: int, external: bool) -> dict[str, Any]:
    code = (
        "import json\n"
        "try:\n"
        " import openvino as ov\n"
        " core=ov.Core()\n"
        " print(json.dumps({'import_ok': True, 'devices': list(core.available_devices)}))\n"
        "except Exception as exc:\n"
        " print(json.dumps({'import_ok': False, 'error': type(exc).__name__ + ': ' + str(exc)}))\n"
    )
    result = run_command([sys.executable, "-c", code], timeout_seconds, cwd=repo_root, enabled=external)
    return {
        "lane": "npu_openvino",
        "probe_performed": external,
        "model_load_performed": False,
        "generation_performed": False,
        "result": result,
    }
