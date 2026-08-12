"""GPU mind contract for Full0To10."""
from __future__ import annotations

from typing import Any

from .constants import GPU_MIND_DIMENSIONS


def build_gpu_mind(request: str, gpu_body: dict[str, Any]) -> dict[str, Any]:
    available = bool(gpu_body.get("command_available"))
    return {
        "kind": "gpu_mind_contract",
        "passed": True,
        "role": "primary_advisory_mind_when_explicit",
        "request": request,
        "owns": list(GPU_MIND_DIMENSIONS),
        "decision_policy": {
            "may_generate": False,
            "requires_run_launcher": True,
            "requires_quality_gate_clean": True,
            "requires_workload_quality_passed": True,
            "requires_operator_intent": True,
        },
        "fallback_policy": {
            "if_gpu_unavailable": "use report-only memory/tool product",
            "if_ollama_unavailable": "keep advisory disabled",
            "if_quality_gate_blocked": "produce blockers not generation",
        },
        "confidence": "prepared" if available else "degraded_without_probe",
    }
