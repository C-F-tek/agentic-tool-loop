"""Readiness scoring for accelerator control plane."""
from __future__ import annotations

from typing import Any

from .constants import SAFETY_FLAGS


def build_accelerator_readiness(control: dict[str, Any]) -> dict[str, Any]:
    score = 100
    warnings: list[str] = []
    blockers: list[str] = []

    if not control["gpu_body"].get("command_available"):
        score -= 15
        warnings.append("gpu_command_not_visible_or_probe_disabled")
    if not control["npu_auditor"].get("device_visible"):
        score -= 8
        warnings.append("npu_not_visible_or_probe_disabled")
    if control["scheduler"].get("generation_allowed"):
        blockers.append("generation_should_not_be_allowed_in_control_plane")
        score -= 40

    report = {
        "kind": "full0to10_accelerator_readiness",
        "passed": not blockers,
        "score": max(0, score),
        "ready_for_product_package": not blockers and score >= 70,
        "ready_for_real_provider_generation": False,
        "blockers": blockers,
        "warnings": warnings,
    }
    report.update(SAFETY_FLAGS)
    return report
