"""GPU/NPU optimization candidate planner."""
from __future__ import annotations

from typing import Any

from .constants import HARDWARE_KEYWORDS


def hardware_relevant(record: dict[str, Any]) -> bool:
    haystack = (str(record["path"]) + "\n" + str(record.get("lower_preview", ""))).lower()
    return any(keyword in haystack for keyword in HARDWARE_KEYWORDS)


def build_hardware_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for record in records:
        if not hardware_relevant(record):
            continue
        path = str(record["path"])
        text = str(record.get("lower_preview", ""))
        if "gpu.0" not in text and "openvino" in text:
            candidates.append(
                {
                    "kind": "npu_gpu0_integration_contract",
                    "path": path,
                    "severity": "medium",
                    "reason": "OpenVINO/NPU code should declare GPU.0 relationship or exclusion explicitly.",
                }
            )
        if "npu" in text and "sampled" not in text:
            candidates.append(
                {
                    "kind": "npu_sampled_auditor_contract",
                    "path": path,
                    "severity": "medium",
                    "reason": "NPU lane should remain sampled auditor unless explicitly promoted.",
                }
            )
        if "gpu" in text and "telemetry" not in text:
            candidates.append(
                {
                    "kind": "gpu_telemetry_visibility",
                    "path": path,
                    "severity": "medium",
                    "reason": "GPU optimization path should expose telemetry/capability outputs.",
                }
            )
    return candidates


def build_hardware_contract() -> dict[str, Any]:
    return {
        "gpu_primary_lane": "Ollama/GPU remains primary advisory/planning provider lane.",
        "npu_lane": "NPU/OpenVINO remains sampled auditor/diagnostic lane.",
        "openvino_gpu0": "OpenVINO GPU.0 must be documented as diagnostic/secondary unless promoted explicitly.",
        "optimization_mode": "Planner only; no runtime setting mutation in this patch.",
        "provider_execution_performed": False,
    }
