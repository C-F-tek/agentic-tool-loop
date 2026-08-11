"""Build Full0To10 final product quality package."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import REQUIRED_REPORTS, SAFETY_FALSE_FIELDS


def _read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), None
    except Exception as exc:
        return {}, f"{type(exc).__name__}: {exc}"


def _report_entry(run_root: Path, spec: dict[str, str]) -> dict[str, Any]:
    path = run_root / spec["path"]
    exists = path.exists()
    data, error = _read_json(path) if exists else ({}, "missing")
    safety = {
        field: bool(data.get(field)) is False
        for field in SAFETY_FALSE_FIELDS
        if field in data
    }
    return {
        "name": spec["name"],
        "path": spec["path"],
        "absolute_path": str(path),
        "exists": exists,
        "json_ok": error is None,
        "json_error": error,
        "kind": data.get("kind"),
        "kind_ok": data.get("kind") == spec["kind"],
        "passed": bool(data.get("passed")),
        "warning_count": len(data.get("warnings", [])) if isinstance(data.get("warnings"), list) else 0,
        "error_count": len(data.get("errors", [])) if isinstance(data.get("errors"), list) else 0,
        "safety_false_fields_ok": all(safety.values()) if safety else True,
        "safety_false_fields": safety,
    }


def _quality_score(entries: list[dict[str, Any]]) -> tuple[int, list[str], list[str]]:
    score = 100
    blockers: list[str] = []
    warnings: list[str] = []
    for item in entries:
        name = item["name"]
        if not item["exists"]:
            score -= 25
            blockers.append(f"missing_report:{name}")
            continue
        if not item["json_ok"]:
            score -= 25
            blockers.append(f"invalid_json:{name}")
            continue
        if not item["kind_ok"]:
            score -= 12
            blockers.append(f"kind_mismatch:{name}")
        if not item["passed"]:
            score -= 10
            warnings.append(f"report_not_passed:{name}")
        if not item["safety_false_fields_ok"]:
            score -= 50
            blockers.append(f"safety_violation:{name}")
    return max(0, score), blockers, warnings


def build_final_product_quality_package(run_root: Path) -> dict[str, Any]:
    run_root = run_root.resolve()
    entries = [_report_entry(run_root, spec) for spec in REQUIRED_REPORTS]
    score, blockers, warnings = _quality_score(entries)
    passed = not blockers and score >= 80
    summary = {
        "kind": "full0to10_final_product_quality_summary",
        "passed": passed,
        "score": score,
        "ready_for_handoff": passed,
        "ready_for_merge": False,
        "report_count": len(entries),
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
        "visibility_first_package": True,
        "report_only": True,
    }
    return {
        "kind": "full0to10_final_product_quality_package",
        "passed": passed,
        "score": score,
        "run_root": str(run_root),
        "summary": summary,
        "reports": entries,
        "blockers": blockers,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "persistent_memory_write_performed": False,
        "blender_runtime_execution_performed": False,
        "ffmpeg_execution_performed": False,
        "errors": blockers,
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
