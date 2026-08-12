"""Hardware delegation contract checks."""
from __future__ import annotations

import json
from typing import Any


def check_hardware_contract(bundle: dict[str, Any], paths: list[str]) -> dict[str, Any]:
    text = (json.dumps(bundle, sort_keys=True, ensure_ascii=False) + "\n" + "\n".join(paths)).lower()
    cpu_visible = any(token in text for token in ("check_python_syntax", "validation", "repository_consistency", "csv"))
    gpu_visible = any(token in text for token in ("gpu", "ollama", "parallel_gpu"))
    npu_visible = any(token in text for token in ("npu", "openvino", "gpu_npu"))
    npu_sampled = any(token in text for token in ("sampled", "auditor", "npu_audit", "npu-auditor"))
    gpu_primary = any(token in text for token in ("primary", "planner", "advisory", "gpu_recommendation", "recommendation_count"))

    errors: list[str] = []
    warnings: list[str] = []
    if not cpu_visible:
        errors.append("CPU validation/discovery lane is not visible")
    if not gpu_visible:
        errors.append("GPU/Ollama provider lane is not visible")
    if not npu_visible:
        errors.append("NPU/OpenVINO diagnostic lane is not visible")
    if npu_visible and not npu_sampled:
        warnings.append("NPU is visible but sampled-auditor semantics are not explicit")
    if gpu_visible and not gpu_primary:
        warnings.append("GPU is visible but primary planner/advisory semantics are not explicit")

    return {
        "passed": not errors,
        "cpu_validation_visible": cpu_visible,
        "gpu_ollama_visible": gpu_visible,
        "npu_openvino_visible": npu_visible,
        "npu_sampled_auditor_visible": npu_sampled,
        "gpu_primary_advisory_visible": gpu_primary,
        "errors": errors,
        "warnings": warnings,
    }
