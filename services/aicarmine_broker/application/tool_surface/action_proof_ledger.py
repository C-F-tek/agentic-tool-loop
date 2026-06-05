"""Stable proof metadata for planner candidate actions."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_action_id(action: dict[str, Any]) -> str:
    normalized = {
        key: value
        for key, value in dict(action or {}).items()
        if key not in {"action_id", "action_proof"}
    }
    raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str)
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
    if not isinstance(action, dict) or not action.get("tool"):
        return dict(action or {})
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
