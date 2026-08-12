from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from Tools.ai.runtime_hardware_capability.policy import (
    build_hardware_runtime_policy,
    policy_warnings,
)
from Tools.ai.runtime_hardware_capability.probes import (
    cpu_diagnostics,
    detect_openvino_devices,
    nvidia_smi_diagnostics,
)

SAFE_SIDE_EFFECTS = ["read_only", "report_only"]


def capability_entry(
    *,
    name: str,
    resource: str,
    role: str,
    status: str,
    provider: str,
    diagnostics: dict[str, Any] | None = None,
    workload_allowed: bool = True,
    exclusive: bool = False,
) -> dict[str, Any]:
    return {
        "name": name,
        "resource": resource,
        "role": role,
        "provider": provider,
        "status": status,
        "exclusive": exclusive,
        "workload_allowed": workload_allowed,
        "allowed_side_effects": SAFE_SIDE_EFFECTS,
        "source_writes_allowed": False,
        "patch_application_allowed": False,
        "persistent_memory_write_allowed": False,
        "media_runtime_allowed": False,
        "network_or_secret_access_allowed": False,
        "timeout_seconds_default": 120,
        "diagnostics": diagnostics or {},
    }


def build_manifest(repo_root: Path) -> dict[str, Any]:
    openvino = detect_openvino_devices()
    nvidia = nvidia_smi_diagnostics()
    policy = build_hardware_runtime_policy(openvino, nvidia)

    capabilities = [
        capability_entry(
            name="cpu_shared_orchestration_validation_fallback",
            resource="CPU",
            role="orchestration_validation_fallback",
            status="available",
            provider="python_stdlib",
            diagnostics=cpu_diagnostics(),
            workload_allowed=True,
            exclusive=False,
        ),
        capability_entry(
            name="cuda_gpu_primary_ollama_exclusive",
            resource="GPU 1 / NVIDIA RTX 5080",
            role="primary_advisory_provider",
            status="available" if policy["cuda_gpu_primary"]["visible"] else "unavailable",
            provider="ollama_or_cuda_runtime",
            diagnostics={"nvidia_smi": nvidia, "policy": policy["cuda_gpu_primary"]},
            workload_allowed=True,
            exclusive=True,
        ),
        capability_entry(
            name="openvino_gpu0_secondary_accelerator",
            resource="GPU.0",
            role="secondary_accelerator",
            status="available" if policy["openvino_gpu0"]["visible"] else "unavailable",
            provider="openvino",
            diagnostics={"openvino": openvino, "policy": policy["openvino_gpu0"]},
            workload_allowed=bool(policy["openvino_gpu0"]["openvino_workload_allowed"]),
            exclusive=False,
        ),
        capability_entry(
            name="openvino_npu_auditor_guardrail",
            resource="NPU",
            role="auditor_guardrail",
            status="available" if policy["openvino_npu"]["visible"] else "unavailable",
            provider="openvino_genai",
            diagnostics={"openvino": openvino, "policy": policy["openvino_npu"]},
            workload_allowed=bool(policy["openvino_npu"]["openvino_workload_allowed"]),
            exclusive=False,
        ),
        capability_entry(
            name="openvino_gpu1_reserved_for_cuda_ollama",
            resource="GPU.1",
            role="reserved_for_cuda_ollama",
            status="reserved" if policy["openvino_gpu1_reserved"]["visible"] else "unavailable",
            provider="openvino_visibility_only",
            diagnostics={"openvino": openvino, "policy": policy["openvino_gpu1_reserved"]},
            workload_allowed=False,
            exclusive=True,
        ),
    ]

    warnings: list[str] = []
    if not openvino.get("available"):
        warnings.append("OpenVINO import/device detection unavailable; GPU.0/NPU are reported unavailable.")
    if not nvidia.get("available"):
        warnings.append("nvidia-smi unavailable or failed; NVIDIA GPU advisory visibility is degraded.")
    warnings.extend(policy_warnings(policy))

    return {
        "schema_version": 1,
        "kind": "runtime_hardware_capability_manifest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": str(repo_root),
        "mode": "report_only",
        "hardware_detection_performed": True,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "persistent_memory_write_performed": False,
        "media_runtime_performed": False,
        "hardware_lane_policy": policy,
        "capabilities": capabilities,
        "required_resources_visible": {
            "CPU": True,
            "CUDA_GPU_PRIMARY": bool(policy["cuda_gpu_primary"]["visible"]),
            "GPU.0": bool(policy["openvino_gpu0"]["visible"]),
            "NPU": bool(policy["openvino_npu"]["visible"]),
            "GPU.1_OPENVINO_VISIBLE_RESERVED": bool(policy["openvino_gpu1_reserved"]["visible"]),
        },
        "errors": [],
        "warnings": warnings,
        "passed": True,
    }
