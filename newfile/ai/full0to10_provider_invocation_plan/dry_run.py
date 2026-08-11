"""Dry-run step plan for provider invocation."""
from __future__ import annotations

from typing import Any

from .constants import PRIMARY_PROVIDER_LANE, SAFETY_FLAGS


def step(index: int, name: str, action: str, executes_provider: bool = False) -> dict[str, Any]:
    return {
        "index": index,
        "name": name,
        "action": action,
        "executes_provider": executes_provider,
    }


def build_dry_run_steps(governor: dict[str, Any]) -> dict[str, Any]:
    permit = governor.get("run_permit") or {}
    steps = [
        step(1, "load_permit", "read provider_run_permit.json"),
        step(2, "load_quality_gate", "read final product quality gate evidence"),
        step(3, "load_accelerator_control", "read GPU body/mind and scheduler"),
        step(4, "bind_context", "bind SQLite/memory/final-product evidence"),
        step(5, "prepare_provider_command", "prepare Ollama/GPU command but do not execute"),
        step(6, "prepare_workload_report_paths", "reserve output paths for workload report and telemetry"),
        step(7, "prepare_npu_audit_hooks", "schedule before/after NPU audit hooks"),
        step(8, "deny_or_wait", "stop unless a future explicit real-run flag is supplied"),
    ]
    report = {
        "kind": "full0to10_provider_dry_run_steps",
        "passed": True,
        "provider_lane": PRIMARY_PROVIDER_LANE,
        "permit_decision": permit.get("decision"),
        "permit_allowed": permit.get("permit_allowed"),
        "generation_would_execute": False,
        "steps": steps,
    }
    report.update(SAFETY_FLAGS)
    return report
