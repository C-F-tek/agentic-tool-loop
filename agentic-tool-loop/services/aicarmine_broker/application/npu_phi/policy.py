from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from .client import enqueue_scene_spec_best_effort


_TRIGGER_TERMS = (
    "album",
    "animazione",
    "animation",
    "blender",
    "camera",
    "cinematic",
    "lighting",
    "music",
    "render",
    "scene",
    "scena",
    "video",
    "visual",
)


EnqueueFn = Callable[..., dict[str, Any]]


def should_attempt_npu_phi_diagnostic(goal: str) -> bool:
    text = str(goal or "").lower()
    return any(term in text for term in _TRIGGER_TERMS)


def _evidence_hash(evidence_contract: dict[str, Any], validation: dict[str, Any]) -> str:
    payload = {
        "violations": validation.get("violations") if isinstance(validation.get("violations"), list) else [],
        "coverage": evidence_contract.get("evidence_coverage") if isinstance(evidence_contract.get("evidence_coverage"), dict) else {},
        "required_next_progress_model": (
            evidence_contract.get("required_next_progress_model")
            if isinstance(evidence_contract.get("required_next_progress_model"), dict)
            else {}
        ),
        "candidate_next_actions_count": (
            len(evidence_contract.get("candidate_next_actions"))
            if isinstance(evidence_contract.get("candidate_next_actions"), list)
            else 0
        ),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:32]


def maybe_enqueue_npu_phi_diagnostic(
    *,
    goal: str,
    evidence_contract: dict[str, Any],
    validation: dict[str, Any],
    enqueue: EnqueueFn = enqueue_scene_spec_best_effort,
) -> dict[str, Any]:
    if not should_attempt_npu_phi_diagnostic(goal):
        return {
            "schema": "npu_phi_broker_enqueue_attempt.v1",
            "attempted": False,
            "status": "not_applicable",
            "reason": "goal_not_in_npu_phi_diagnostic_scope",
        }
    return enqueue(
        goal=goal,
        evidence_hash=_evidence_hash(evidence_contract, validation),
    )
