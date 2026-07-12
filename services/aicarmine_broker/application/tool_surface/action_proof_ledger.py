"""Stable proof metadata for planner candidate actions."""

from __future__ import annotations

import hashlib
from typing import Any

from ..shared.diagnostics import diagnostic_row, safe_json_text


def stable_action_id(action: dict[str, Any]) -> str:
    source = dict(action) if isinstance(action, dict) else {
        "invalid_action_type": type(action).__name__,
    }
    normalized = {
        key: value
        for key, value in source.items()
        if key not in {"action_id", "action_proof"}
    }
    raw, _diagnostic = safe_json_text(normalized, reason="stable_action_id_json_failed")
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def attach_action_proof(
    action: dict[str, Any],
    *,
    source: str,
    path_exists: bool | None = None,
    path_readable: bool | None = None,
    under_scope: bool | None = None,
    validator_admissible: bool | None = None,
    source_step: int | None = None,
    source_hash: str = "",
) -> dict[str, Any]:
    if not isinstance(action, dict):
        return diagnostic_row(
            "invalid_action_for_proof",
            schema="action_proof_diagnostic.v1",
            received_type=type(action).__name__,
        )
    if not action.get("tool"):
        out = dict(action)
        out["action_proof_diagnostics"] = [
            diagnostic_row("action_tool_missing", schema="action_proof_diagnostic.v1")
        ]
        return out
    out = dict(action)
    out["action_id"] = stable_action_id(action)
    out["action_proof"] = {
        "source": source,
        "path_exists": path_exists,
        "path_readable": path_readable,
        "under_scope": under_scope,
        "validator_admissible": validator_admissible,
        "source_step": source_step,
        "source_hash": source_hash,
    }
    return out
