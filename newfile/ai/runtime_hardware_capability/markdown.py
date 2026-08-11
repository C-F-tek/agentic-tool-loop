from __future__ import annotations

from typing import Any


def _yes_no(value: Any) -> str:
    return "true" if bool(value) else "false"


def render_markdown(report: dict[str, Any]) -> str:
    policy = report.get("hardware_lane_policy")
    if not isinstance(policy, dict):
        policy = {}

    lines = [
        "# Runtime hardware capability manifest",
        "",
        f"- Kind: `{report.get('kind')}`",
        f"- Passed: `{report.get('passed')}`",
        f"- Mode: `{report.get('mode')}`",
        f"- Provider execution performed: `{report.get('provider_execution_performed')}`",
        f"- Patch application performed: `{report.get('patch_application_performed')}`",
        "",
        "## Hardware lane policy",
        "",
        "| Lane | Device | Owner | Role | Visible | Workload allowed | Policy |",
        "|---|---|---|---|---|---|---|",
    ]

    lane_rows = [
        ("cuda_gpu_primary", "CUDA/Ollama primary"),
        ("cpu_shared", "CPU shared"),
        ("openvino_gpu0", "OpenVINO GPU.0"),
        ("openvino_npu", "OpenVINO NPU"),
        ("openvino_gpu1_reserved", "OpenVINO GPU.1 reserved"),
    ]
    for key, label in lane_rows:
        item = policy.get(key) if isinstance(policy.get(key), dict) else {}
        workload_allowed = item.get("openvino_workload_allowed", item.get("workload_allowed", item.get("exclusive") is False))
        lines.append(
            f"| `{label}` | `{item.get('full_device_name') or item.get('device')}` | "
            f"`{item.get('owner')}` | `{item.get('role')}` | `{_yes_no(item.get('visible', True))}` | "
            f"`{_yes_no(workload_allowed)}` | `{item.get('policy') or item.get('rationale') or ''}` |"
        )

    lines.extend([
        "",
        "## Capabilities",
        "",
        "| Resource | Name | Role | Provider | Status | Workload allowed | Exclusive |",
        "|---|---|---|---|---|---|---|",
    ])
    for item in report.get("capabilities", []):
        lines.append(
            f"| `{item.get('resource')}` | `{item.get('name')}` | `{item.get('role')}` | "
            f"`{item.get('provider')}` | `{item.get('status')}` | `{_yes_no(item.get('workload_allowed'))}` | "
            f"`{_yes_no(item.get('exclusive'))}` |"
        )
    lines.extend(["", "## Warnings", ""])
    warnings = report.get("warnings") or []
    lines.extend([f"- {warning}" for warning in warnings] or ["- none"])
    lines.append("")
    return "\n".join(lines)
