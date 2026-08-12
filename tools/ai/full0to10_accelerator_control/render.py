"""Render accelerator control plane markdown."""
from __future__ import annotations

from typing import Any


def render_control_markdown(control: dict[str, Any]) -> str:
    readiness = control["readiness"]
    lines = [
        "# Full0To10 accelerator control plane",
        "",
        "## Request",
        "",
        control["request"],
        "",
        "## GPU body",
        "",
        f"- Role: `{control['gpu_body']['role']}`",
        f"- Command available: `{control['gpu_body']['command_available']}`",
        "- Ownership: device visibility, memory budget, process ownership, runtime telemetry.",
        "",
        "## GPU mind",
        "",
        f"- Role: `{control['gpu_mind']['role']}`",
        f"- May generate now: `{control['gpu_mind']['decision_policy']['may_generate']}`",
        "- Policy: explicit launcher, quality gate, workload quality, operator intent.",
        "",
        "## NPU auditor",
        "",
        f"- Role: `{control['npu_auditor']['role']}`",
        f"- Device visible: `{control['npu_auditor']['device_visible']}`",
        "",
        "## OpenVINO GPU.0",
        "",
        f"- Role: `{control['openvino_gpu0']['role']}`",
        f"- Device visible: `{control['openvino_gpu0']['device_visible']}`",
        "",
        "## Scheduler",
        "",
    ]
    for lane in control["scheduler"]["lanes"]:
        lines.append(f"- `{lane['lane']}` allowed=`{lane['allowed']}` priority=`{lane['priority']}` reason={lane['reason']}")
    lines.extend(
        [
            "",
            "## Readiness",
            "",
            f"- Score: `{readiness['score']}`",
            f"- Ready for product package: `{readiness['ready_for_product_package']}`",
            f"- Ready for real provider generation: `{readiness['ready_for_real_provider_generation']}`",
            "",
        ]
    )
    return "\n".join(lines)
