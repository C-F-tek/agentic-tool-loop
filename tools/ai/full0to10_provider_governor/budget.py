"""Provider budget planning."""
from __future__ import annotations

from typing import Any

from .constants import PROVIDER_BUDGETS


def build_budget_plan(request: str) -> dict[str, Any]:
    return {
        "kind": "full0to10_provider_budget_plan",
        "passed": True,
        "request": request,
        "budgets": PROVIDER_BUDGETS,
        "global_limits": {
            "no_generation_without_permit": True,
            "no_patch_apply_from_provider": True,
            "no_blender_runtime": True,
            "no_ffmpeg_runtime": True,
            "output_only_under_output_validation": True,
        },
        "budget_order": [
            "sqlite_memory_and_tools_first",
            "quality_gate_second",
            "accelerator_control_third",
            "permit_decision_fourth",
            "provider_generation_only_after_explicit_future_run",
        ],
    }
