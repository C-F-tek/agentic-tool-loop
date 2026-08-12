#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_markdown(report: dict, path: Path) -> None:
    lines = [
        "# AI workload report quality global DataStamp smoke",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Quality report passed: `{report.get('quality_passed')}`",
        f"- DataStamp: `{report.get('data_stamp')}`",
        f"- AI packets dir: `{report.get('ai_packets_dir')}`",
        f"- Selected count: `{report.get('selected_count')}`",
        f"- Unselected known count: `{report.get('unselected_known_count')}`",
        "",
    ]
    if report.get("errors"):
        lines += ["## Errors", ""]
        for item in report["errors"]:
            lines.append(f"- {item}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke global DataStamp ai_packets workload quality contract.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output", required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve(strict=False)
    output = Path(args.output).resolve(strict=False)
    markdown_output = Path(args.markdown_output).resolve(strict=False)

    data_stamp = "smoke-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    ai_packets_root = output.with_name(output.stem + "_ai_packets")
    ai_packets_dir = ai_packets_root / data_stamp
    ai_packets_dir.mkdir(parents=True, exist_ok=True)

    npu_report = ai_packets_dir / "npu_real_workload_report.md"
    npu_report.write_text(
        "NPU OpenVINO Real Workload Report\n\n"
        "This deterministic fixture validates a single global DataStamp and stamp-scoped provider packets. "
        "It contains natural language text describing NPU probe output, advisory restrictions, lane role, "
        "quality routing, report-only validation, and absence of runtime side effects. "
        "No provider execution is performed by this smoke.\n",
        encoding="utf-8",
    )

    legacy_report = ai_packets_root / "legacy_workload_report.md"
    legacy_report.write_text(
        "Legacy workload report fixture\n\n"
        "This root-level fixture validates that output/ai_packets remains acceptable as a root report folder. "
        "The checker must inspect concrete workload report files in the root and in timestamp child folders "
        "without treating directories as context files.\n",
        encoding="utf-8",
    )

    quality_output = output.with_name(output.stem + "_quality.json")
    cmd = [
        sys.executable,
        str(repo_root / "Tools" / "validation" / "check_ai_workload_report_quality.py"),
        "--repo-root",
        str(repo_root),
        "--report-dir",
        str(ai_packets_root),
        "--output",
        str(quality_output),
    ]
    result = subprocess.run(cmd, cwd=repo_root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)

    errors: list[str] = []
    quality = {}
    if quality_output.exists():
        try:
            quality = json.loads(quality_output.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            errors.append(f"quality output is not valid JSON: {type(exc).__name__}: {exc}")
    else:
        errors.append(f"quality output missing: {quality_output}")

    if result.returncode != 0:
        errors.append(f"quality checker returned {result.returncode}: {result.stdout[-1200:]}")
    if quality.get("passed") is not True:
        errors.append(f"quality report did not pass: {quality.get('errors')}")
    if not str(quality.get("report_dir", "")).replace("\\", "/").endswith("_ai_packets"):
        errors.append("quality report_dir is not the selected AI packets root")
    selected_paths = [str(item.get("path", "")).replace("\\", "/") for item in quality.get("selected_reports", [])]
    if not any(data_stamp in item and item.endswith("npu_real_workload_report.md") for item in selected_paths):
        errors.append("stamp-scoped npu fixture was not selected from a child packet directory")
    if not any(item.endswith("legacy_workload_report.md") for item in selected_paths):
        errors.append("root-level workload report fixture was not selected")
    if "npu" not in quality.get("usable_lanes", []):
        errors.append("npu fixture was not selected as usable")
    if "ollama" in quality.get("unusable_lanes", []):
        errors.append("missing ollama should not be selected into unusable_lanes in default output-folder mode")
    if not quality.get("unselected_known_reports"):
        errors.append("missing known reports should be serialized as unselected_known_reports")

    report = {
        "schema_version": 1,
        "kind": "ai_workload_report_quality_global_datastamp_smoke",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": [],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": True,
        "blender_runtime_execution_performed": False,
        "ffmpeg_execution_performed": False,
        "data_stamp": data_stamp,
        "ai_packets_dir": str(ai_packets_dir),
        "quality_output": str(quality_output),
        "quality_passed": quality.get("passed"),
        "selected_count": len(quality.get("selected_reports", [])),
        "unselected_known_count": len(quality.get("unselected_known_reports", [])),
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(report, markdown_output)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
