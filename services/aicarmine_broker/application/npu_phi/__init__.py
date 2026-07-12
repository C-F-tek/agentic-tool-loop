"""Best-effort NPU Phi diagnostic integration helpers."""

from .client import NpuPhiClientConfig, enqueue_scene_spec_best_effort
from .policy import maybe_enqueue_npu_phi_diagnostic, should_attempt_npu_phi_diagnostic

__all__ = [
    "NpuPhiClientConfig",
    "enqueue_scene_spec_best_effort",
    "maybe_enqueue_npu_phi_diagnostic",
    "should_attempt_npu_phi_diagnostic",
]
