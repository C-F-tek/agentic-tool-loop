"""Build Full0To10 hardware/tool capability manifests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .gpu import build_gpu_probe
from .npu import build_npu_probe
from .ollama import build_ollama_probe
from .openvino_devices import enrich_npu_probe, normalize_openvino_device_visibility
from .python_env import build_python_env
from .tools import build_tool_inventory


def build_capability_manifest(
    repo_root: Path,
    timeout_seconds: int,
    external: bool,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    tool_inventory = build_tool_inventory(repo_root)
    with ThreadPoolExecutor(max_workers=3) as executor:
        gpu_future = executor.submit(build_gpu_probe, repo_root, timeout_seconds, external)
        ollama_future = executor.submit(build_ollama_probe, repo_root, timeout_seconds, external)
        npu_future = executor.submit(build_npu_probe, repo_root, timeout_seconds, external)

    errors: list[str] = []
    warnings: list[str] = []
    if not tool_inventory["passed"]:
        errors.extend(f"missing_tool: {path}" for path in tool_inventory["missing"])

    npu_probe = npu_future.result()
    openvino_visibility = normalize_openvino_device_visibility(npu_probe)
    enriched_npu = enrich_npu_probe(npu_probe, openvino_visibility)

    return {
        "kind": "full0to10_hardware_tool_capability",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": not errors,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "persistent_memory_write_performed": False,
        "external_probes_enabled": external,
        "python": build_python_env(),
        "tool_inventory": tool_inventory,
        "gpu": gpu_future.result(),
        "ollama": ollama_future.result(),
        "openvino_devices": openvino_visibility["openvino_devices"],
        "openvino_cpu": openvino_visibility["openvino_cpu"],
        "openvino_gpu0": openvino_visibility["openvino_gpu0"],
        "openvino_gpu1": openvino_visibility["openvino_gpu1"],
        "openvino_npu": openvino_visibility["openvino_npu"],
        "npu": enriched_npu,
        "errors": errors,
        "warnings": warnings,
    }
