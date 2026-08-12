#!/usr/bin/env python3
"""Smoke test for explicit provider_empty_response and bootstrap reporting diagnostics.

This smoke does not execute GPU/Ollama or NPU providers. It validates that:
- NPU audit classification maps empty text to provider_empty_response;
- supervised GPU runner contains explicit provider_empty_response handling;
- supervised GPU report code exposes bootstrap broker diagnostics.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.ai.run_npu_gpu_deep_review_auditor import classify_npu_output
except ImportError:
    import sys

    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.run_npu_gpu_deep_review_auditor import classify_npu_output  # type: ignore


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def marker_check(text: str, marker: str, errors: list[str]) -> None:
    if marker not in text:
        errors.append(f"missing supervised marker: {marker}")


def build_report(repo_root: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    classification, npu_warnings = classify_npu_output(
        text="",
        returncode=0,
        error=None,
        stdout="[NPU] Loading model:\n[NPU] Device: NPU\n",
        stderr="",
        metadata_only=False,
    )
    if classification != "provider_empty_response":
        errors.append(f"NPU empty output classified as {classification!r}, expected provider_empty_response")
    if not any("empty response" in item.lower() for item in npu_warnings):
        errors.append("NPU empty output did not emit an empty-response warning")

    supervised_path = repo_root / "Tools" / "ai" / "run_agent_gpu_deep_planning_supervised.py"
    supervised_text = supervised_path.read_text(encoding="utf-8")

    for marker in (
        "provider_empty_response_count",
        "ProviderEmptyResponse: model returned an empty response",
        "provider_empty_response",
        "runtime_tool_bootstrap",
        "runtime_tool_bootstrap_output",
        "runtime_tool_bootstrap_execution_count",
        "runtime_tool_bootstrap_result_count",
        "recommended_next_layer",
    ):
        marker_check(supervised_text, marker, errors)

    if '"empty_recommendations_reason": "provider_empty_response"' not in supervised_text and "provider_empty_response" not in supervised_text:
        errors.append("supervised runner does not expose provider_empty_response as an empty recommendation reason")

    return {
        "schema_version": 1,
        "kind": "provider_empty_response_diagnostics_smoke",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "npu_empty_classification": classification,
        "npu_empty_warnings": npu_warnings,
        "guardrails": {
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
            "blender_runtime_touched": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Provider Empty Response Diagnostics Smoke", ""]
    for key in (
        "passed",
        "provider_execution_performed",
        "patch_application_performed",
        "sqlite_write_performed",
        "persistent_memory_write_performed",
        "npu_empty_classification",
    ):
        lines.append(f"- {key}: `{report.get(key)}`")
    if report.get("errors"):
        lines.extend(["", "## Errors"])
        lines.extend(f"- {item}" for item in report["errors"])
    if report.get("warnings"):
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {item}" for item in report["warnings"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/validation/provider_empty_response_diagnostics_smoke.json")
    parser.add_argument("--markdown-output", default="output/validation/provider_empty_response_diagnostics_smoke.md")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_report(repo_root)
    output = resolve_path(repo_root, args.output)
    markdown = resolve_path(repo_root, args.markdown_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown),
                "provider_execution_performed": report["provider_execution_performed"],
                "patch_application_performed": report["patch_application_performed"],
                "npu_empty_classification": report["npu_empty_classification"],
                "sqlite_write_performed": report["sqlite_write_performed"],
                "persistent_memory_write_performed": report["persistent_memory_write_performed"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
