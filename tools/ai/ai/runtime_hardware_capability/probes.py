from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Any


def command_json(cmd: list[str], timeout: int = 20) -> dict[str, Any]:
    """Run a short local diagnostic command and return bounded output."""
    exe = shutil.which(cmd[0])
    if not exe:
        return {"available": False, "command": cmd, "error": f"{cmd[0]} not found"}
    try:
        result = subprocess.run(
            [exe, *cmd[1:]],
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except Exception as exc:
        return {"available": False, "command": cmd, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "available": result.returncode == 0,
        "command": cmd,
        "returncode": result.returncode,
        "stdout_preview": result.stdout[:4000],
        "stderr_preview": result.stderr[:2000],
    }


def _safe_openvino_property(core: Any, device: str, name: str) -> Any:
    try:
        value = core.get_property(device, name)
    except Exception as exc:  # noqa: BLE001 - diagnostics must not fail the manifest.
        return {"error": f"{type(exc).__name__}: {exc}"}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items()}
    return str(value)


def detect_openvino_devices() -> dict[str, Any]:
    """Detect OpenVINO devices without running model inference."""
    try:
        try:
            from openvino import Core  # type: ignore
        except ImportError:
            from openvino.runtime import Core  # type: ignore
    except Exception as exc:
        return {"available": False, "devices": [], "device_details": {}, "error": f"{type(exc).__name__}: {exc}"}

    try:
        core = Core()
        devices = [str(device) for device in core.available_devices]
        details: dict[str, Any] = {}
        for device in devices:
            details[device] = {
                "full_device_name": _safe_openvino_property(core, device, "FULL_DEVICE_NAME"),
                "optimization_capabilities": _safe_openvino_property(core, device, "OPTIMIZATION_CAPABILITIES"),
            }
    except Exception as exc:
        return {"available": False, "devices": [], "device_details": {}, "error": f"{type(exc).__name__}: {exc}"}
    return {"available": True, "devices": devices, "device_details": details, "error": None}


def cpu_diagnostics() -> dict[str, Any]:
    """Return report-only CPU/Python diagnostics."""
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "cpu_count": os.cpu_count(),
    }


def nvidia_smi_diagnostics() -> dict[str, Any]:
    """Return bounded NVIDIA visibility diagnostics."""
    return command_json(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
        timeout=20,
    )
