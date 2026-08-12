#!/usr/bin/env python3
"""Smoke test for the shared toolbox AI-to-AI bundle builder.

The smoke is no-provider and report-only. It creates fake input reports under
output/testdata, runs the builder, verifies final summary, compact bundle,
recursive discovery, pointer-style chunk metadata and optional bundle validation
outputs, then writes a smoke JSON/Markdown report.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

try:
    from Tools.ai.build_shared_toolbox_ai_to_ai_bundle import build_shared_toolbox_bundle
    from Tools.ai.github_evidence_bundle_io import read_json, repo_relative
    from Tools.validation.report_utils import resolve_output_path, write_json_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.build_shared_toolbox_ai_to_ai_bundle import build_shared_toolbox_bundle
    from Tools.ai.github_evidence_bundle_io import read_json, repo_relative
    from Tools.validation.report_utils import resolve_output_path, write_json_report


SMOKE_STAMP = "smoke-20260503-000000"


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON smoke inputs through the shared validation report helper."""
    write_json_report(data, path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def fake_report(
    *,
    kind: str,
    passed: bool = True,
    provider_execution_performed: bool = False,
    patch_application_performed: bool = False,
    sqlite_write_performed: bool = False,
    persistent_memory_write_performed: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": 1,
        "kind": kind,
        "passed": passed,
        "errors": [],
        "warnings": [],
        "provider_execution_performed": provider_execution_performed,
        "patch_application_performed": patch_application_performed,
        "source_writes_performed": False,
        "sqlite_write_performed": sqlite_write_performed,
        "persistent_memory_write_performed": persistent_memory_write_performed,
        "blender_runtime_execution_performed": False,
    }
    if extra:
        data.update(extra)
    return data


def create_fake_inputs(repo_root: Path, stamp: str) -> dict[str, Path]:
    base = repo_root / "output" / "testdata" / "shared_toolbox_ai_to_ai_bundle_smoke"
    reports = {
        "python_syntax": base / f"shared_toolbox_python_syntax_{stamp}.json",
        "code_interpreter": base / f"shared_toolbox_code_interpreter_{stamp}.json",
        "gpu_contract_smoke": base / f"shared_toolbox_gpu_contract_smoke_{stamp}.json",
        "gpu_routing": base / f"shared_toolbox_gpu_routing_{stamp}.json",
        "npu_execution": base / f"shared_toolbox_npu_execution_{stamp}.json",
        "orchestrator": base / f"shared_toolbox_ai_to_ai_{stamp}_orchestrator.json",
        "gpu": base / f"shared_toolbox_ai_to_ai_{stamp}_gpu.json",
        "large_json": base / f"shared_toolbox_large_recursive_report_{stamp}.json",
    }
    write_json(reports["python_syntax"], fake_report(kind="python_syntax_validation", extra={"checked_count": 2, "failed_count": 0}))
    write_json(reports["code_interpreter"], fake_report(kind="code_interpreter_report", extra={"input_count": 2}))
    write_json(reports["gpu_contract_smoke"], fake_report(kind="gpu_planner_json_contract_smoke", extra={"case_count": 3, "failed_case_count": 0}))
    write_json(
        reports["gpu_routing"],
        fake_report(
            kind="orchestrator_gpu_runtime_tool_routing_smoke",
            extra={
                "gpu_runtime_tool_request_count": 1,
                "gpu_runtime_tool_execution_count": 1,
                "gpu_runtime_tool_failed_count": 0,
                "gpu_runtime_tool_blocked_count": 0,
                "tool_requests": [
                    {
                        "id": "smoke_check_python_syntax",
                        "tool": "check_python_syntax",
                        "reason": "Smoke request for report-only syntax validation.",
                        "args": {},
                    }
                ],
            },
        ),
    )
    write_json(
        reports["npu_execution"],
        fake_report(
            kind="npu_runtime_tool_execution_smoke",
            extra={
                "npu_runtime_tool_request_count": 1,
                "npu_runtime_tool_execution_count": 1,
                "npu_runtime_tool_failed_count": 0,
                "npu_runtime_tool_blocked_count": 0,
            },
        ),
    )
    write_json(
        reports["orchestrator"],
        fake_report(
            kind="agent_gpu_npu_parallel_orchestrator",
            provider_execution_performed=True,
            extra={"gpu_runtime_tool_request_count": 1, "gpu_runtime_tool_execution_count": 1},
        ),
    )
    write_json(
        reports["gpu"],
        fake_report(
            kind="agent_gpu_deep_planning_supervised",
            provider_execution_performed=True,
            extra={"round_count": 1, "recommendation_count": 0, "runtime_tool_broker_enabled": True},
        ),
    )
    write_json(
        reports["large_json"],
        fake_report(
            kind="shared_toolbox_large_recursive_report",
            extra={"rows": [{"index": index, "value": f"row-{index}"} for index in range(1, 220)]},
        ),
    )

    artifacts = {
        "task_md": base / "shared-runtime-toolbox-ai-to-ai-next-task-smoke.md",
        "architecture_md": base / "shared-runtime-toolbox-orchestration-architecture-smoke.md",
        "code_interpreter_md": base / f"shared_toolbox_code_interpreter_{stamp}.md",
        "orchestrator_md": base / f"shared_toolbox_ai_to_ai_{stamp}_orchestrator.md",
        "gpu_md": base / f"shared_toolbox_ai_to_ai_{stamp}_gpu.md",
        "large_markdown": base / f"shared_toolbox_large_recursive_artifact_{stamp}.md",
    }
    write_text(artifacts["task_md"], "# Smoke task\n\nReport-only shared toolbox smoke task.\n")
    write_text(artifacts["architecture_md"], "# Smoke architecture\n\nProviders ask. Orchestrator decides. Broker executes. Reports become evidence.\n")
    write_text(artifacts["code_interpreter_md"], "# Smoke code interpreter report\n\nNo provider execution.\n")
    write_text(artifacts["orchestrator_md"], "# Smoke orchestrator report\n\nProvider flag is inherited from fake input only.\n")
    write_text(artifacts["gpu_md"], "# Smoke GPU report\n\nNo real provider was executed by this smoke.\n")
    write_text(
        artifacts["large_markdown"],
        "# Large recursive artifact\n\n" + "\n".join(f"line {index}" for index in range(1, 241)) + "\n",
    )
    return {**reports, **artifacts}


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Shared Toolbox AI-to-AI Bundle Builder Smoke", ""]
    for key in (
        "passed",
        "provider_execution_performed",
        "patch_application_performed",
        "sqlite_write_performed",
        "persistent_memory_write_performed",
        "final_summary_json_exists",
        "final_summary_markdown_exists",
        "bundle_json_exists",
        "bundle_markdown_exists",
        "bundle_validation_passed",
        "recursive_defaults_enabled",
        "recursive_default_files_seen",
        "chunked_large_files_seen",
        "chunk_next_pointer_seen",
    ):
        lines.append(f"- {key}: {report.get(key)}")
    if report.get("errors"):
        lines.append("")
        lines.append("## Errors")
        for error in report.get("errors", []):
            lines.append(f"- {error}")
    if report.get("warnings"):
        lines.append("")
        lines.append("## Warnings")
        for warning in report.get("warnings", []):
            lines.append(f"- {warning}")
    return "\n".join(lines) + "\n"


def build_builder_args(repo_root: Path, paths: dict[str, Path]) -> SimpleNamespace:
    stamp = SMOKE_STAMP
    return SimpleNamespace(
        repo_root=str(repo_root),
        stamp=stamp,
        basename=f"shared_toolbox_ai_to_ai_bundle_{stamp}",
        output_dir="docs/LOCAL_VALIDATION_EVIDENCE",
        task_md=repo_relative(paths["task_md"], repo_root),
        architecture_md=repo_relative(paths["architecture_md"], repo_root),
        orchestrator_report=[repo_relative(paths["orchestrator"], repo_root)],
        gpu_report=[repo_relative(paths["gpu"], repo_root)],
        sync_report=[],
        contract_replay_report=[],
        code_interpreter_report=[repo_relative(paths["code_interpreter"], repo_root)],
        python_syntax_report=[repo_relative(paths["python_syntax"], repo_root)],
        report=[
            repo_relative(paths["gpu_contract_smoke"], repo_root),
            repo_relative(paths["gpu_routing"], repo_root),
            repo_relative(paths["npu_execution"], repo_root),
        ],
        artifact=[
            repo_relative(paths["code_interpreter_md"], repo_root),
            repo_relative(paths["orchestrator_md"], repo_root),
            repo_relative(paths["gpu_md"], repo_root),
        ],
        include_missing_optional=False,
        validate_bundle=True,
        validation_output=f"output/validation/shared_toolbox_ai_to_ai_bundle_{stamp}_validation.json",
        max_included_artifact_chars=8000,
        max_included_artifacts=30,
        no_recursive_defaults=True,
        recursive_report_root=[repo_relative(paths["large_json"].parent, repo_root)],
        recursive_artifact_root=[repo_relative(paths["large_markdown"].parent, repo_root)],
        recursive_include_unstamped=False,
        recursive_max_files=80,
        chunk_large_files_lines=200,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/validation/shared_toolbox_ai_to_ai_bundle_smoke.json")
    parser.add_argument("--markdown-output", default="output/validation/shared_toolbox_ai_to_ai_bundle_smoke.md")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    paths = create_fake_inputs(repo_root, SMOKE_STAMP)
    builder_result = build_shared_toolbox_bundle(build_builder_args(repo_root, paths))

    final_summary_json = repo_root / str(builder_result.get("final_summary_json") or "")
    final_summary_md = repo_root / str(builder_result.get("final_summary_markdown") or "")
    bundle_outputs = [repo_root / str(item) for item in builder_result.get("bundle_outputs", [])]
    bundle_json = next((path for path in bundle_outputs if path.suffix == ".json"), repo_root / "missing.json")
    bundle_md = next((path for path in bundle_outputs if path.suffix == ".md"), repo_root / "missing.md")
    validation_output = repo_root / str(builder_result.get("validation_output") or "")

    summary = read_json(final_summary_json) or {}
    bundle = read_json(bundle_json) or {}
    validation = read_json(validation_output) or {}
    errors: list[str] = []
    warnings: list[str] = []

    chunked_index = bundle.get("artifact_chunk_index") if isinstance(bundle.get("artifact_chunk_index"), list) else []
    recursive_defaults = bundle.get("recursive_default_discovery") if isinstance(bundle.get("recursive_default_discovery"), dict) else {}
    has_chunk_next_pointer = any(
        bool(chunk.get("next_chunk_id"))
        for item in chunked_index
        if isinstance(item, dict)
        for chunk in item.get("chunks", [])
        if isinstance(chunk, dict)
    )

    checks = {
        "final_summary_json_exists": final_summary_json.exists(),
        "final_summary_markdown_exists": final_summary_md.exists(),
        "bundle_json_exists": bundle_json.exists(),
        "bundle_markdown_exists": bundle_md.exists(),
        "bundle_validation_passed": validation.get("passed") is True,
        "recursive_defaults_enabled": recursive_defaults.get("enabled") is True,
        "recursive_default_files_seen": bool(recursive_defaults.get("discovered_reports") or recursive_defaults.get("discovered_artifacts")),
        "chunked_large_files_seen": bool(chunked_index),
        "chunk_next_pointer_seen": has_chunk_next_pointer,
    }
    for key, ok in checks.items():
        if not ok:
            errors.append(f"{key} is false")

    if summary.get("patch_application_performed") is not False:
        errors.append("final summary patch_application_performed must be false")
    if summary.get("sqlite_write_performed") is not False:
        errors.append("final summary sqlite_write_performed must be false")
    if summary.get("persistent_memory_write_performed") is not False:
        errors.append("final summary persistent_memory_write_performed must be false")
    if summary.get("provider_execution_performed") is not True:
        warnings.append("provider_execution_performed was expected true from fake input reports")

    report = {
        "schema_version": 1,
        "kind": "shared_toolbox_ai_to_ai_bundle_smoke",
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": bool(summary.get("provider_execution_performed")),
        "patch_application_performed": bool(summary.get("patch_application_performed")),
        "sqlite_write_performed": bool(summary.get("sqlite_write_performed")),
        "persistent_memory_write_performed": bool(summary.get("persistent_memory_write_performed")),
        **checks,
        "final_summary_json": repo_relative(final_summary_json, repo_root),
        "final_summary_markdown": repo_relative(final_summary_md, repo_root),
        "bundle_json": repo_relative(bundle_json, repo_root),
        "bundle_markdown": repo_relative(bundle_md, repo_root),
        "validation_output": repo_relative(validation_output, repo_root),
        "builder_result": builder_result,
        "chunked_file_count": len(chunked_index),
        "recursive_discovered_report_count": len(recursive_defaults.get("discovered_reports") or []),
        "recursive_discovered_artifact_count": len(recursive_defaults.get("discovered_artifacts") or []),
    }

    output = resolve_output_path(repo_root, args.output)
    markdown_output = resolve_output_path(repo_root, args.markdown_output)
    write_json_report(report, output)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
