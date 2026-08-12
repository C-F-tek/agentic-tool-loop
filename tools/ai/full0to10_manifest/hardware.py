"""Hardware capability/delegation manifest helpers."""
from __future__ import annotations


def build_hardware_manifest() -> dict[str, object]:
    return {
        "cpu": {
            "role": "discovery_validation_index_bundle",
            "parallel_safe": True,
            "expected_artifacts": ["csv", "repository_consistency", "validation_reports"],
        },
        "gpu_ollama": {
            "role": "primary_provider_advisory_planner",
            "parallel_safe": True,
            "expected_artifacts": ["parallel_gpu", "recommendations", "provider_diagnostics"],
        },
        "npu_openvino": {
            "role": "sampled_auditor_guardrail_decode_diagnostic",
            "parallel_safe": True,
            "lockstep_required": False,
            "expected_artifacts": ["npu_audits", "gpu_npu_sync"],
        },
        "contract": {
            "gpu_is_primary_provider_lane": True,
            "npu_is_sampled_auditor": True,
            "cpu_keeps_validation_and_bundle_accounting": True,
        },
    }
