"""Track input contract builder."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import INPUT_ROLES, SAFETY_FLAGS
from .discovery import scan_json_candidates, selected_inputs


def build_contract(repo_root: Path, track_name: str, max_candidates: int, require_inputs: bool) -> dict[str, Any]:
    candidates = scan_json_candidates(repo_root, track_name, max_candidates)
    selected = selected_inputs(candidates)
    missing = [role for role in INPUT_ROLES if selected.get(role) is None]
    warnings = [f"missing track input: {role}" for role in missing]
    errors = warnings if require_inputs else []

    contract = {
        "kind": "full0to10_track_input_contract",
        "track_name": track_name,
        "passed": not errors,
        "complete": not missing,
        "require_inputs": require_inputs,
        "required_roles": list(INPUT_ROLES),
        "selected_inputs": selected,
        "candidates": candidates,
        "missing_roles": missing,
        "errors": errors,
        "warnings": warnings,
        "policy": {
            "missing_inputs_default": "warning",
            "missing_inputs_when_require_inputs": "error",
            "template_generated": True,
            "no_blender_runtime": True,
            "no_provider_execution": True,
        },
    }
    contract.update(SAFETY_FLAGS)
    return contract
