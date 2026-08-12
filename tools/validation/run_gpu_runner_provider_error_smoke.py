#!/usr/bin/env python3
"""Smoke-test GPU supervised runner provider-error hardening.

This test does not run Ollama, NPU, Blender, patch application, Git writes or SQLite writes.
It verifies that schema repair is skipped for an empty/missing raw provider response
and that the supervised runner source contains explicit provider-error hardening markers.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


class FailingRepairManager:
    def __init__(self) -> None:
        self.called = False

    def generate(self, *_args: Any, **_kwargs: Any) -> tuple[str, str]:
        self.called = True
        raise AssertionError("schema repair generate must not be called for empty raw_response")


def build_report(repo_root: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    runner_path = repo_root / "Tools/ai/run_agent_gpu_deep_planning_supervised.py"
    if not runner_path.exists():
        errors.append(f"missing runner file: {runner_path}")
        source = ""
    else:
        source = runner_path.read_text(encoding="utf-8-sig")

    required_markers = {
        "raw_response_initialized": "raw_response = \"\"",
        "provider_error_initialized": "provider_error = \"\"",
        "empty_raw_response_repair_guard": "empty_or_missing_raw_response",
        "provider_error_report_field": "\"provider_error\": provider_error",
        "provider_error_count_report_field": "\"provider_error_count\": provider_error_count",
        "raw_response_assignment_after_generate": "raw_response = response",
    }
    marker_results: dict[str, bool] = {}
    for key, marker in required_markers.items():
        marker_results[key] = marker in source
        if not marker_results[key]:
            errors.append(f"missing hardening marker: {key} -> {marker}")

    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

    repair_result: dict[str, Any] | None = None
    manager = FailingRepairManager()
    try:
        from Tools.ai.run_agent_gpu_deep_planning_supervised import run_schema_repair_retry_for_round

        repair_result = run_schema_repair_retry_for_round(
            manager=manager,
            model="dummy-model",
            args=SimpleNamespace(max_new_tokens=1200, runtime_tool_max_requests_per_round=8),
            round_index=1,
            objective="provider error hardening smoke",
            raw_response="",
            parsed_response={},
            parse_diagnostics={"schema_ok": False, "valid_tool_request_count": 0},
            context_reports=[],
            rounds=[],
            evidence_ready_for_manual_patch_count=1,
        )
        if manager.called:
            errors.append("repair manager was called for empty raw_response")
        if repair_result.get("attempted") is not False:
            errors.append(f"expected attempted=false for empty raw_response, got {repair_result}")
        if repair_result.get("reason") != "empty_or_missing_raw_response":
            errors.append(f"expected empty_or_missing_raw_response reason, got {repair_result}")
    except Exception as exc:  # noqa: BLE001 - smoke report must capture failure.
        errors.append(f"dynamic empty-response repair guard failed: {type(exc).__name__}: {exc}")

    return {
        "schema_version": 1,
        "kind": "gpu_runner_provider_error_smoke",
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
        "blender_runtime_execution_performed": False,
        "marker_results": marker_results,
        "repair_result": repair_result,
        "guardrails": {
            "report_only": True,
            "no_ollama_provider_call": True,
            "no_npu_provider_call": True,
            "no_blender_runtime": True,
            "no_patch_application": True,
            "no_git_write": True,
            "no_sqlite_write": True,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# GPU Runner Provider Error Smoke", ""]
    for key in (
        "passed",
        "provider_execution_performed",
        "patch_application_performed",
        "sqlite_write_performed",
        "blender_runtime_execution_performed",
    ):
        lines.append(f"- {key}: `{report.get(key)}`")
    lines.append("")
    lines.append("## Marker results")
    lines.append("")
    for key, value in report.get("marker_results", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Repair result")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report.get("repair_result"), indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    if report.get("errors"):
        lines.append("## Errors")
        lines.append("")
        for error in report.get("errors", []):
            lines.append(f"- {error}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/validation/gpu_runner_provider_error_smoke.json")
    parser.add_argument("--markdown-output", default="output/validation/gpu_runner_provider_error_smoke.md")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_report(repo_root)
    output = resolve(repo_root, args.output)
    markdown = resolve(repo_root, args.markdown_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown.write_text(render_markdown(report) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown),
                "errors": report["errors"],
                "warnings": report["warnings"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
