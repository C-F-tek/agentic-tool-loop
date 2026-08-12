"""Semantic checks for light Full0To10 provider telemetry artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import REPORTS, REQUIRED_SEMANTIC_FLAGS, SAFETY_FALSE_FIELDS


def _read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), None
    except Exception as exc:  # pragma: no cover - defensive CLI path
        return {}, f"{type(exc).__name__}: {exc}"


def _walk_values(value: Any) -> list[Any]:
    values = [value]
    if isinstance(value, dict):
        for child in value.values():
            values.extend(_walk_values(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(_walk_values(child))
    return values


def _contains_text(value: Any, needle: str) -> bool:
    lower = needle.lower()
    for item in _walk_values(value):
        if isinstance(item, str) and lower in item.lower():
            return True
        if isinstance(item, dict) and any(lower in str(key).lower() for key in item):
            return True
    return False


def _bool_path(data: dict[str, Any], *path: str) -> bool:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return False
        current = current.get(key)
    return bool(current)


def _dict_path(data: dict[str, Any], *path: str) -> dict[str, Any]:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _report_summary(name: str, spec: dict[str, str], path: Path) -> dict[str, Any]:
    exists = path.exists()
    data, error = _read_json(path) if exists else ({}, "missing")
    kind_ok = data.get("kind") == spec["kind"]
    passed = bool(data.get("passed")) if exists else False
    safety = {
        field: bool(data.get(field)) is False
        for field in SAFETY_FALSE_FIELDS
        if field in data
    }
    return {
        "name": name,
        "path": str(path),
        "exists": exists,
        "json_ok": error is None,
        "json_error": error,
        "kind": data.get("kind"),
        "kind_ok": kind_ok,
        "passed": passed,
        "safety_false_fields_ok": all(safety.values()) if safety else True,
        "safety_false_fields": safety,
        "data": data,
    }


def _has_top_level_openvino_fields(accelerator: dict[str, Any]) -> bool:
    capability = _dict_path(accelerator, "hardware_capability")
    return all(
        key in capability
        for key in ("openvino_devices", "openvino_cpu", "openvino_gpu0", "openvino_gpu1", "openvino_npu")
    )


def _semantic_flags(reports: dict[str, dict[str, Any]]) -> dict[str, bool]:
    accelerator = reports["accelerator_control"]["data"]
    governor = reports["provider_governor"]["data"]
    invocation = reports["provider_invocation_plan"]["data"]
    bridge = reports["provider_execution_bridge"]["data"]
    command_plan = _dict_path(bridge, "command_plan")
    return {
        "accelerator_has_npu_auditor": bool(accelerator.get("npu_auditor")),
        "accelerator_has_openvino_gpu0": bool(accelerator.get("openvino_gpu0")),
        "accelerator_external_probes_disabled": _bool_path(
            accelerator, "hardware_capability", "external_probes_enabled"
        ) is False,
        "accelerator_has_top_level_openvino_fields": _has_top_level_openvino_fields(accelerator),
        "governor_has_run_permit": bool(governor.get("run_permit")),
        "governor_deny_not_failure": bool(governor.get("deny_is_failure")) is False,
        "invocation_generation_not_now": bool(invocation.get("generation_executes_now")) is False,
        "invocation_has_telemetry_contract": bool(invocation.get("expected_telemetry_contract")),
        "invocation_has_workload_contract": bool(invocation.get("workload_report_contract")),
        "bridge_real_run_gate_present": bool(bridge.get("real_run_gate")),
        "bridge_command_plan_non_executing": bool(command_plan.get("all_commands_are_non_executing")),
        "bridge_workload_paths_present": bool(bridge.get("workload_output_paths")),
        "gpu0_policy_visible": _contains_text(accelerator, "gpu0")
        or _contains_text(invocation, "openvino_gpu0")
        or _contains_text(bridge, "openvino_gpu0"),
        "npu_policy_visible": _contains_text(accelerator, "npu")
        or _contains_text(invocation, "openvino_npu")
        or _contains_text(bridge, "openvino_npu"),
    }


def validate_light_provider_telemetry(run_root: Path) -> dict[str, Any]:
    run_root = run_root.resolve()
    report_entries = {
        name: _report_summary(name, spec, run_root / spec["path"])
        for name, spec in REPORTS.items()
    }
    semantic_flags = _semantic_flags(report_entries)
    failed_reports = [
        name
        for name, item in report_entries.items()
        if not (
            item["exists"]
            and item["json_ok"]
            and item["kind_ok"]
            and item["passed"]
            and item["safety_false_fields_ok"]
        )
    ]
    missing_semantics = [
        name for name in REQUIRED_SEMANTIC_FLAGS if not semantic_flags.get(name)
    ]
    errors = [f"report_failed:{name}" for name in failed_reports]
    errors.extend(f"semantic_missing:{name}" for name in missing_semantics)
    public_reports = {
        name: {key: value for key, value in item.items() if key != "data"}
        for name, item in report_entries.items()
    }
    return {
        "kind": "full0to10_provider_telemetry_semantic_validation",
        "passed": not errors,
        "run_root": str(run_root),
        "reports": public_reports,
        "semantic_flags": semantic_flags,
        "failed_reports": failed_reports,
        "missing_semantics": missing_semantics,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "persistent_memory_write_performed": False,
        "blender_runtime_execution_performed": False,
        "ffmpeg_execution_performed": False,
        "errors": errors,
        "warnings": [],
    }
