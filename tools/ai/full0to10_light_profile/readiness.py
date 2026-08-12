"""Readiness checks for Full0To10 light profile promotion."""
from __future__ import annotations

from typing import Any

from .constants import REQUIRED_STEPS, SAFETY_FALSE_FIELDS, NEXT_LOOP_ACTIONS
from .reader import failed_steps, steps_by_name


def missing_required_steps(run: dict[str, Any]) -> list[str]:
    names = steps_by_name(run)
    return [step for step in REQUIRED_STEPS if step not in names]


def safety_violations(run: dict[str, Any]) -> list[str]:
    return [field for field in SAFETY_FALSE_FIELDS if bool(run.get(field)) is not False]


def build_readiness(run: dict[str, Any], run_report_path: str) -> dict[str, Any]:
    failed = failed_steps(run)
    missing = missing_required_steps(run)
    safety = safety_violations(run)
    passed = bool(run.get("passed")) and not failed and not missing and not safety

    return {
        "kind": "full0to10_light_profile_promotion",
        "source_report": run_report_path,
        "passed": passed,
        "promotable_to_unified_launcher": passed,
        "light_profile_name": "LightFull0To10",
        "recommended_launcher_flag": "-LightFull0To10",
        "recommended_default_flags": ["-NoExternalProbes"],
        "step_count": int(run.get("step_count", len(steps_by_name(run)))),
        "failed_count": len(failed),
        "missing_required_steps": missing,
        "failed_steps": failed,
        "safety_violations": safety,
        "provider_execution_performed": bool(run.get("provider_execution_performed")),
        "patch_application_performed": bool(run.get("patch_application_performed")),
        "blender_runtime_execution_performed": bool(run.get("blender_runtime_execution_performed")),
        "ffmpeg_execution_performed": bool(run.get("ffmpeg_execution_performed")),
        "next_loop_actions": list(NEXT_LOOP_ACTIONS),
    }
