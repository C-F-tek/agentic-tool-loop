"""Provider scheduler policy for accelerator control."""
from __future__ import annotations

from typing import Any


def lane_state(name: str, allowed: bool, reason: str, priority: int) -> dict[str, Any]:
    return {"lane": name, "allowed": allowed, "reason": reason, "priority": priority}


def build_scheduler(
    gpu_body: dict[str, Any],
    gpu_mind: dict[str, Any],
    npu: dict[str, Any],
    gpu0: dict[str, Any],
) -> dict[str, Any]:
    gpu_available = bool(gpu_body.get("command_available"))
    return {
        "kind": "accelerator_scheduler_policy",
        "passed": True,
        "generation_allowed": False,
        "default_mode": "quality_and_evidence_only",
        "lanes": [
            lane_state("sqlite_fts5_memory", True, "deterministic local context lane", 10),
            lane_state("runtime_tools", True, "local telemetry-capable tool lane", 20),
            lane_state("ollama_gpu", False, "requires explicit RunLauncher and quality gates", 30 if gpu_available else 90),
            lane_state("openvino_npu", False, "auditor/diagnostic only until promoted", 60),
            lane_state("openvino_gpu0", False, "secondary diagnostic only until promoted", 70),
        ],
        "routing_rules": [
            "memory and tool lanes run before provider generation",
            "GPU advisory cannot start without explicit launcher",
            "NPU can disagree or audit, not lead by default",
            "GPU.0 cannot take the primary GPU lane implicitly",
            "quality product package must exist before real run",
        ],
        "gpu_mind_policy": gpu_mind["decision_policy"],
        "npu_role": npu["role"],
        "gpu0_role": gpu0["role"],
    }
