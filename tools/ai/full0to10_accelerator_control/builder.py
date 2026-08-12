"""Build Full0To10 accelerator control plane."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from full0to10_hardware_capability.builder import build_capability_manifest

from .constants import CONTROL_JSON, CONTROL_MD, SAFETY_FLAGS, TELEMETRY_JSON
from .gpu0_contract import build_gpu0_contract
from .gpu_body import build_gpu_body
from .gpu_mind import build_gpu_mind
from .npu_auditor import build_npu_auditor
from .paths import ensure_dir, repo_relative
from .readiness import build_accelerator_readiness
from .render import render_control_markdown
from .scheduler import build_scheduler
from .telemetry import build_accelerator_telemetry, telemetry_event


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_accelerator_control(
    repo_root: Path,
    output_dir: Path,
    request: str,
    no_external_probes: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output_dir = ensure_dir(output_dir)
    events: list[dict[str, Any]] = []

    capability = build_capability_manifest(repo_root, timeout_seconds=timeout_seconds, external=not no_external_probes)
    events.append(telemetry_event("hardware_capability", capability.get("passed", False), {"external": not no_external_probes}))

    gpu_body = build_gpu_body(capability)
    gpu_mind = build_gpu_mind(request, gpu_body)
    npu = build_npu_auditor(capability)
    gpu0 = build_gpu0_contract(capability)
    scheduler = build_scheduler(gpu_body, gpu_mind, npu, gpu0)

    control: dict[str, Any] = {
        "kind": "full0to10_accelerator_control",
        "passed": True,
        "request": request,
        "hardware_capability": capability,
        "gpu_body": gpu_body,
        "gpu_mind": gpu_mind,
        "npu_auditor": npu,
        "openvino_gpu0": gpu0,
        "scheduler": scheduler,
        "errors": [],
        "warnings": [],
    }
    control.update(SAFETY_FLAGS)
    control["readiness"] = build_accelerator_readiness(control)
    control["passed"] = control["readiness"]["passed"]
    events.append(telemetry_event("accelerator_control", control["passed"], {"score": control["readiness"]["score"]}))
    telemetry = build_accelerator_telemetry(events)

    control_path = output_dir / CONTROL_JSON
    telemetry_path = output_dir / TELEMETRY_JSON
    markdown_path = output_dir / CONTROL_MD
    write_json(control_path, control)
    write_json(telemetry_path, telemetry)
    markdown_path.write_text(render_control_markdown(control), encoding="utf-8")
    control["outputs"] = {
        "control": repo_relative(control_path, repo_root),
        "telemetry": repo_relative(telemetry_path, repo_root),
        "markdown": repo_relative(markdown_path, repo_root),
    }
    return control
