"""Build provider tool feedback loop report-only artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import INPUT_REPORTS


def _read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), None
    except Exception as exc:
        return {}, f"{type(exc).__name__}: {exc}"


def _entry(run_root: Path, spec: dict[str, str]) -> dict[str, Any]:
    path = run_root / spec["path"]
    data, error = _read_json(path) if path.exists() else ({}, "missing")
    return {
        "name": spec["name"],
        "path": str(path),
        "exists": path.exists(),
        "json_ok": error is None,
        "json_error": error,
        "kind": data.get("kind"),
        "kind_ok": data.get("kind") == spec["kind"],
        "passed": bool(data.get("passed")),
        "provider_execution_performed": bool(data.get("provider_execution_performed")),
        "patch_application_performed": bool(data.get("patch_application_performed")),
    }


def build_tool_output_manifest(run_root: Path) -> dict[str, Any]:
    outputs = [_entry(run_root, spec) for spec in INPUT_REPORTS]
    failed = [
        item["name"]
        for item in outputs
        if not (item["exists"] and item["json_ok"] and item["kind_ok"] and item["passed"])
    ]
    return {
        "kind": "full0to10_provider_tool_output_manifest",
        "passed": not failed,
        "run_root": str(run_root),
        "outputs": outputs,
        "failed_outputs": failed,
        "broker_dry_run_performed": True,
        "broker_execution_performed": False,
        "provider_execution_performed": False,
        "patch_application_performed": False,
    }


def build_feedback_packet(manifest: dict[str, Any]) -> dict[str, Any]:
    available = [item["name"] for item in manifest.get("outputs", []) if item.get("passed")]
    return {
        "kind": "full0to10_provider_feedback_packet",
        "passed": bool(manifest.get("passed")),
        "feedback_mode": "report_only",
        "provider_request_reinjection_performed": False,
        "broker_dry_run_performed": True,
        "broker_execution_performed": False,
        "available_tool_outputs": available,
        "feedback_items": [
            "Use provider_governor for run permit and deny semantics.",
            "Use provider_invocation_plan for dry-run workload and telemetry contracts.",
            "Use provider_execution_bridge for non-executing command gate.",
            "Use provider_telemetry_semantic before promoting provider evidence.",
        ],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "persistent_memory_write_performed": False,
    }


def build_provider_tool_feedback_loop(run_root: Path) -> dict[str, Any]:
    run_root = run_root.resolve()
    manifest = build_tool_output_manifest(run_root)
    packet = build_feedback_packet(manifest)
    errors = [f"tool_output_failed:{name}" for name in manifest.get("failed_outputs", [])]
    return {
        "kind": "full0to10_provider_tool_feedback_loop",
        "passed": not errors and packet["passed"],
        "run_root": str(run_root),
        "tool_output_manifest": manifest,
        "provider_feedback_packet": packet,
        "feedback_mode": packet["feedback_mode"],
        "broker_dry_run_performed": True,
        "broker_execution_performed": False,
        "provider_request_reinjection_performed": False,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "persistent_memory_write_performed": False,
        "blender_runtime_execution_performed": False,
        "ffmpeg_execution_performed": False,
        "errors": errors,
        "warnings": [],
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
