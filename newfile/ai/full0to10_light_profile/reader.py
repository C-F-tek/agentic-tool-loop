"""Read light evidence run reports."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def steps_by_name(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    steps = run.get("steps", [])
    if not isinstance(steps, list):
        return {}
    output: dict[str, dict[str, Any]] = {}
    for step in steps:
        if isinstance(step, dict) and step.get("name"):
            output[str(step["name"])] = step
    return output


def failed_steps(run: dict[str, Any]) -> list[dict[str, Any]]:
    steps = run.get("steps", [])
    if not isinstance(steps, list):
        return []
    return [
        step for step in steps
        if isinstance(step, dict) and step.get("status") in {"failed", "missing_required"}
    ]
