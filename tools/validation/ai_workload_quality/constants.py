"""Constants for AI workload quality validation."""
from __future__ import annotations

DEFAULT_REPORT_DIR = "output/ai_packets"

KNOWN_WORKLOAD_REPORTS = (
    ("npu", "npu_real_workload_report.md"),
    ("ollama", "ollama_gpu_real_workload_report.md"),
)

LANE_ROLES = {
    "ollama": {
        "provider": "ollama",
        "compute_lane": "gpu_cuda",
        "allowed_role_when_usable": "primary_advisory",
        "execution_mode": "explicit_only",
    },
    "npu": {
        "provider": "openvino_npu",
        "compute_lane": "npu",
        "allowed_role_when_usable": "knowledge_broker_or_probe",
        "execution_mode": "explicit_only",
    },
}

HEXISH_CHARS = set("0123456789abcdefABCDEF, .\n\r\t")
