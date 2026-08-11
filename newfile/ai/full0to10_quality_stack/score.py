"""Score Full0To10 quality stack readiness."""
from __future__ import annotations

from typing import Any


def is_passed(report: dict[str, Any] | None) -> bool:
    return bool(report and report.get("passed") is True)


def hardware_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if not report:
        return {"present": False}
    return {
        "present": True,
        "passed": report.get("passed"),
        "external_probes_enabled": report.get("external_probes_enabled"),
        "gpu_available": report.get("gpu", {}).get("command_available"),
        "ollama_available": report.get("ollama", {}).get("command_available"),
        "npu_probe_performed": report.get("npu", {}).get("probe_performed"),
    }


def runtime_tool_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if not report:
        return {"present": False}
    return {
        "present": True,
        "passed": report.get("passed"),
        "tool_count": report.get("tool_count"),
        "broker_bridge_ready": report.get("broker_bridge_ready"),
    }


def compute_readiness(reports: dict[str, Any]) -> dict[str, Any]:
    blockers = []
    warnings = []
    score = 100

    for role in ("hardware_capability", "runtime_tool_registry", "quality_gate"):
        if not is_passed(reports.get(role)):
            score -= 20
            blockers.append(f"{role}_not_passed_or_missing")

    if reports.get("run_manifest") is None:
        score -= 10
        warnings.append("run_manifest_missing")
    if reports.get("contract_validation") is None:
        score -= 10
        warnings.append("contract_validation_missing")

    quality = reports.get("quality_gate") or {}
    if quality.get("readiness", {}).get("blockers"):
        score -= 15
        blockers.extend(quality["readiness"]["blockers"])

    score = max(score, 0)
    return {
        "score": score,
        "ready_for_real_run": score >= 85 and not blockers,
        "blockers": blockers,
        "warnings": warnings,
    }
