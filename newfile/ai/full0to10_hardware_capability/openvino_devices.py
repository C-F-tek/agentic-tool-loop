"""Normalize OpenVINO device visibility for Full0To10 reports."""
from __future__ import annotations

import json
import re
from typing import Any


DEVICE_PATTERN = re.compile(r"\b(?:CPU|NPU|GPU(?:\.?\d+)?)\b", re.IGNORECASE)


def _canonical_device(value: str) -> str:
    text = value.strip().upper()
    if text.startswith("GPU") and "." not in text and len(text) > 3:
        return f"GPU.{text[3:]}"
    return text


def _add_device(output: list[str], value: Any) -> None:
    text = _canonical_device(str(value))
    if DEVICE_PATTERN.fullmatch(text) and text not in output:
        output.append(text)


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


def _walk(value: Any, output: list[str]) -> None:
    if value is None:
        return
    if isinstance(value, dict):
        for key in ("devices", "available_devices", "openvino_devices", "normalized_devices"):
            if key in value:
                _walk(value[key], output)
        for key in ("stdout", "stderr", "result", "raw", "probe", "data"):
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
        return


def extract_openvino_devices(npu_probe: dict[str, Any]) -> list[str]:
    devices: list[str] = []
    _walk(npu_probe, devices)
    return devices


def _entry(device: str, devices: list[str], role: str, primary: bool) -> dict[str, Any]:
    return {
        "device": device,
        "device_visible": device in devices,
        "role": role,
        "primary_advisory_allowed": primary,
    }


def normalize_openvino_device_visibility(npu_probe: dict[str, Any]) -> dict[str, Any]:
    devices = extract_openvino_devices(npu_probe)
    return {
        "openvino_devices": devices,
        "openvino_cpu": _entry("CPU", devices, "host_fallback_and_baseline", False),
        "openvino_gpu0": _entry("GPU.0", devices, "secondary_diagnostic_only", False),
        "openvino_gpu1": _entry("GPU.1", devices, "secondary_diagnostic_only", False),
        "openvino_npu": _entry("NPU", devices, "sampled_auditor_or_diagnostic", False),
    }


def enrich_npu_probe(npu_probe: dict[str, Any], visibility: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(npu_probe)
    devices = list(visibility.get("openvino_devices", []))
    enriched["devices"] = devices
    enriched["normalized_devices"] = devices
    enriched["device_visible"] = bool(visibility["openvino_npu"]["device_visible"])
    enriched["role"] = "sampled_auditor_or_diagnostic"
    enriched["primary_advisory_allowed"] = False
    return enriched
