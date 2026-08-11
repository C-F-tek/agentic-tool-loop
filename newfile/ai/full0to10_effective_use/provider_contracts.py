"""Provider hardening contracts for Full0To10 effective use."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from full0to10_hardware_capability.builder import build_capability_manifest

from .constants import PROVIDER_LANES, SAFETY_FLAGS


def lane_contract(name: str) -> dict[str, Any]:
    if name == "sqlite_fts5":
        return {
            "role": "deterministic_local_memory",
            "primary": True,
            "execution": "local_sqlite_only",
            "hardening": ["namespace_required", "fts5_required", "embedding_cache_optional"],
        }
    if name == "runtime_tools":
        return {
            "role": "tool_invocation_and_telemetry",
            "primary": True,
            "execution": "local_cli_or_adapter",
            "hardening": ["json_report_required", "capability_manifest_required", "no_source_write_default"],
        }
    if name == "ollama_gpu":
        return {
            "role": "primary_advisory_when_explicit",
            "primary": False,
            "execution": "explicit_provider_only",
            "hardening": ["no_implicit_generation", "quality_preflight_required", "gpu_telemetry_required"],
        }
    if name == "openvino_npu":
        return {
            "role": "sampled_auditor_or_diagnostic",
            "primary": False,
            "execution": "explicit_probe_or_sample_only",
            "hardening": ["no_primary_advisory_default", "model_load_not_required_for_preflight"],
        }
    return {
        "role": "secondary_diagnostic_gpu0",
        "primary": False,
        "execution": "diagnostic_only_until_promoted",
        "hardening": ["document_gpu0_relationship", "do_not_steal_primary_gpu_lane"],
    }


def build_provider_contracts(repo_root: Path, timeout_seconds: int, external: bool) -> dict[str, Any]:
    capability = build_capability_manifest(repo_root, timeout_seconds=timeout_seconds, external=external)
    report = {
        "kind": "full0to10_provider_hardening_contracts",
        "passed": True,
        "lanes": {name: lane_contract(name) for name in PROVIDER_LANES},
        "hardware_capability": capability,
        "optimization_policy": {
            "gpu": "optimize visibility and telemetry before generation",
            "npu": "use as sampled auditor/diagnostic, not primary advisory",
            "gpu0": "keep OpenVINO GPU.0 secondary unless explicitly promoted",
            "ollama": "list/ps/probe safe; generation requires explicit run lane",
        },
        "errors": [],
        "warnings": [],
    }
    report.update(SAFETY_FLAGS)
    return report
