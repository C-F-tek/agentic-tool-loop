#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from Tools.ai.runtime_hardware_capability.workloads import run_openvino_gpu0_tensor_test


def resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# OpenVINO GPU.0 secondary workload",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Provider execution performed: `{report.get('provider_execution_performed')}`",
        f"- Production support: `{report.get('production_support')}`",
        f"- Iterations: `{report.get('iterations')}`",
        f"- Minimum seconds: `{report.get('min_seconds')}`",
        f"- Requested role: `{report.get('requested_role')}`",
        f"- GPU.0 visible: `{report.get('openvino_gpu0_visible')}`",
        f"- GPU.0 probe performed: `{report.get('openvino_gpu0_probe_performed')}`",
        f"- GPU.0 workload performed: `{report.get('openvino_gpu0_workload_performed')}`",
        f"- GPU.0 workload passed: `{report.get('openvino_gpu0_workload_passed')}`",
        f"- GPU.0 role: `{report.get('openvino_gpu0_role')}`",
        f"- GPU.0 support lane: `{report.get('openvino_gpu0_support_lane')}`",
        f"- GPU.0 sustained requested: `{report.get('openvino_gpu0_sustained_workload_requested')}`",
        f"- GPU.0 sustained performed: `{report.get('openvino_gpu0_sustained_workload_performed')}`",
        f"- GPU.0 iterations requested: `{report.get('openvino_gpu0_sustained_iterations_requested')}`",
        f"- GPU.0 iterations performed: `{report.get('openvino_gpu0_sustained_iterations_performed')}`",
        f"- GPU.0 min seconds requested: `{report.get('openvino_gpu0_sustained_min_seconds_requested')}`",
        f"- GPU.1 reserved visible: `{report.get('openvino_gpu1_reserved_visible')}`",
        f"- GPU.1 workload performed: `{report.get('openvino_gpu1_workload_performed')}`",
        f"- Selected device: `{report.get('selected_device')}`",
        f"- Available devices: `{report.get('available_devices')}`",
        f"- Elapsed seconds: `{report.get('elapsed_seconds')}`",
        f"- Compile seconds: `{report.get('compile_seconds')}`",
        f"- Inference seconds: `{report.get('inference_seconds')}`",
        "",
        "## Output preview",
        "",
        str(report.get("output_preview") or ""),
        "",
        "## Errors",
    ]
    errors = report.get("errors") or []
    lines.extend([f"- {item}" for item in errors] or ["- none"])
    lines.extend(["", "## Warnings"])
    warnings = report.get("warnings") or []
    lines.extend([f"- {item}" for item in warnings] or ["- none"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/validation/openvino_gpu0_workload.json")
    parser.add_argument("--markdown-output", default="output/validation/openvino_gpu0_workload.md")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--min-seconds", type=float, default=0.0)
    parser.add_argument("--role", default="secondary_accelerator")
    parser.add_argument("--production-support", action="store_true")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    report = run_openvino_gpu0_tensor_test(
        iterations=args.iterations,
        min_seconds=args.min_seconds,
        role=args.role,
        production_support=args.production_support,
    )
    report["production_support"] = bool(args.production_support)
    report["iterations"] = int(args.iterations)
    report["min_seconds"] = float(args.min_seconds)
    report["requested_role"] = str(args.role)
    if args.production_support:
        report["openvino_gpu0_role"] = str(args.role)
        report["openvino_gpu0_not_primary_advisory"] = False
    report["repo_root"] = str(repo_root)
    output = resolve_path(repo_root, args.output)
    markdown = resolve_path(repo_root, args.markdown_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"passed": report.get("passed"), "output": str(output), "markdown": str(markdown)}, indent=2))
    return 0 if report.get("passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
