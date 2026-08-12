#!/usr/bin/env python3
"""Build a report-only NPU decode quality remediation plan.

This validator consumes ``ai_workload_report_quality.json`` and emits a focused
remediation report for NPU/OpenVINO decoding quality. It does not execute NPU,
OpenVINO, Ollama or any provider; it only describes safe follow-up actions for
human review or an explicitly scoped future milestone.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from report_utils import resolve_output_path, write_json_report


def _ensure_repo_imports(repo_root: Path) -> None:
    root_text = str(repo_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001 - report-only diagnostic.
        return None
    return data if isinstance(data, dict) else None


def _lane_result(report: dict[str, Any], lane: str) -> dict[str, Any] | None:
    checks = report.get("checks") or {}
    results = checks.get("results") if isinstance(checks, dict) else []
    if not isinstance(results, list):
        return None
    for item in results:
        if isinstance(item, dict) and item.get("lane") == lane:
            return item
    return None


def _diagnose_npu(result: dict[str, Any] | None) -> tuple[list[str], list[str], list[str]]:
    findings: list[str] = []
    remediation: list[str] = []
    stop_conditions: list[str] = []

    if not result:
        findings.append("npu quality result is missing")
        remediation.append("Regenerate ai_workload_report_quality.json before changing NPU decode settings.")
        stop_conditions.append("No NPU quality metrics are available.")
        return findings, remediation, stop_conditions

    metrics = result.get("metrics") or {}
    alpha_ratio = float(metrics.get("alpha_ratio") or 0.0)
    digit_ratio = float(metrics.get("digit_ratio") or 0.0)
    hexish_ratio = float(metrics.get("hexish_ratio") or 0.0)
    word_count = int(metrics.get("word_count") or 0)

    if result.get("classification") == "unusable_output":
        findings.append("NPU workload output is currently classified as unusable_output.")
    if alpha_ratio < 0.18:
        findings.append(f"Alphabetic ratio is below natural-language threshold: {alpha_ratio}.")
    if digit_ratio > 0.75:
        findings.append(f"Digit ratio is abnormally high for Markdown output: {digit_ratio}.")
    if hexish_ratio > 0.82:
        findings.append(f"Hex-like character ratio indicates non-linguistic decoding: {hexish_ratio}.")
    if word_count < 20:
        findings.append(f"Word count is too low for advisory use: {word_count}.")

    remediation.extend(
        [
            "Keep NPU/OpenVINO excluded from advisory context until the workload report is classified usable_text.",
            "Add an explicit NPU decode smoke mode that writes only to output/validation or output/ai_packets and is never called by legacy runtime defaults.",
            "Capture raw NPU generation metadata next to the text report: engine, device, model_dir, prompt lengths, requested token limits and output metrics.",
            "Investigate OpenVINO GenAI string decoding/tokenizer compatibility before changing model, temperature, provider orchestration or prompt prose.",
            "Run a minimal short-prompt NPU diagnostic separately from repository-context review to isolate decode corruption from context length pressure.",
            "Promote NPU from probe/guardrail to advisory only after ai_workload_report_quality reports npu in usable_lanes.",
        ]
    )
    stop_conditions.extend(
        [
            "Any fix requires changing prompt prose legacy, model selection, temperature or provider orchestration without a separate explicit milestone.",
            "Any diagnostic would execute NPU implicitly from packet/proposal builders or Blender runtime.",
            "Any diagnostic output would overwrite legacy output or full analysis JSON.",
            "Any change would introduce OpenVINO GPU as a primary lane.",
        ]
    )
    return findings, remediation, stop_conditions


def build_npu_decode_quality_remediation_report(repo_root: Path, quality_report_path: Path) -> dict[str, Any]:
    quality_report = _load_json(quality_report_path)
    errors: list[str] = []
    warnings: list[str] = []

    if not quality_report:
        errors.append("quality report is missing or unreadable")
        npu_result = None
    elif quality_report.get("kind") != "ai_workload_report_quality":
        errors.append("quality report kind is not ai_workload_report_quality")
        npu_result = None
    else:
        npu_result = _lane_result(quality_report, "npu")
        if not npu_result:
            warnings.append("quality report does not contain an npu lane result")

    findings, remediation, stop_conditions = _diagnose_npu(npu_result)
    npu_usable = bool(npu_result and npu_result.get("usable") is True)

    return {
        "schema_version": 1,
        "kind": "npu_decode_quality_remediation",
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "mode": "report_only_decode_remediation_plan",
        "policy": "no_provider_execution_no_runtime_changes",
        "checks": {
            "quality_report_path": str(quality_report_path),
            "npu_usable_for_advisory": npu_usable,
            "npu_classification": npu_result.get("classification") if npu_result else "missing",
            "npu_metrics": npu_result.get("metrics") if npu_result else {},
            "findings": findings,
            "remediation_steps": remediation,
            "stop_conditions": stop_conditions,
            "required_promotion_gate": "ai_workload_report_quality.usable_lanes contains npu",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--quality-report", default="output/validation/ai_workload_report_quality.json")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    _ensure_repo_imports(repo_root)
    quality_report_path = Path(args.quality_report)
    if not quality_report_path.is_absolute():
        quality_report_path = repo_root / quality_report_path

    report = build_npu_decode_quality_remediation_report(repo_root, quality_report_path)
    output = resolve_output_path(repo_root, args.output) if args.output else None
    text = write_json_report(report, output)
    print(text, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
