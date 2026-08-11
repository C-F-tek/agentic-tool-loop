"""OpenVINO device visibility normalization for accelerator control."""
from __future__ import annotations

import json
import re
from typing import Any


DEVICE_PATTERN = re.compile(r"\b(?:CPU|NPU|GPU(?:\.?\d+)?)\b", re.IGNORECASE)


def _canonical(value: str) -> str:
    text = value.strip().upper()
    if text.startswith("GPU") and "." not in text and len(text) > 3:
        return f"GPU.{text[3:]}"
    return text


def _json_from_text(value: str) -> Any | None:
    text = value.strip()
    if not text:
        return None
    for candidate in (text, text.splitlines()[-1].strip()):
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


def _add_device(output: list[str], value: Any) -> None:
    normalized = _canonical(str(value))
    if DEVICE_PATTERN.fullmatch(normalized) and normalized not in output:
        output.append(normalized)


def _walk(value: Any, output: list[str]) -> None:
    if value is None:
        return
    if isinstance(value, dict):
        for key in ("devices", "available_devices", "openvino_devices", "normalized_devices"):
            if key in value:
                _walk(value[key], output)
        for key in ("stdout", "result", "raw", "probe", "data"):
            if key in value:
                _walk(value[key], output)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _walk(item, output)
        return
    if isinstance(value, str):
        parsed = _json_from_text(value)
        if parsed is not None and parsed is not value:
            _walk(parsed, output)
        for match in DEVICE_PATTERN.findall(value):
            _add_device(output, match)
        for part in re.split(r"[,;\s]+", value):
            if DEVICE_PATTERN.fullmatch(part.strip()):
                _add_device(output, part)


def normalized_openvino_devices(capability: dict[str, Any]) -> list[str]:
    """Return normalized OpenVINO device names from capability payloads."""
    devices: list[str] = []
    if isinstance(capability, dict):
        _walk(capability.get("openvino_devices"), devices)
        _walk(capability.get("npu", {}), devices)
    return devices


def has_device(capability: dict[str, Any], device: str) -> bool:
    expected = _canonical(device)
    return expected in normalized_openvino_devices(capability)


def openvino_visibility_summary(capability: dict[str, Any]) -> dict[str, Any]:
    devices = normalized_openvino_devices(capability)
    return {
        "devices": devices,
        "cpu_visible": "CPU" in devices,
        "npu_visible": "NPU" in devices,
        "gpu0_visible": "GPU.0" in devices,
        "gpu1_visible": "GPU.1" in devices,
        "gpu_devices": [item for item in devices if item.startswith("GPU")],
    }
