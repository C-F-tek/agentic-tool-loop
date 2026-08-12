#!/usr/bin/env python3
"""Smoke-test the report-only refactor duplication audit tool."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

try:
    from Tools.ai.build_refactor_duplication_audit import build_report, render_markdown
    from Tools.validation.report_utils import resolve_output_path, write_json_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.build_refactor_duplication_audit import build_report, render_markdown
    from Tools.validation.report_utils import resolve_output_path, write_json_report


SMOKE_STAMP = "smoke-20260503-000000"


def write_json(path: Path, data: dict[str, Any]) -> None:
    write_json_report(data, path)


def fake_report(kind: str, *, passed: bool = True) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": kind,
        "passed": passed,
        "errors": [],
        "warnings": [],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
    }


def create_fake_reports(repo_root: Path, stamp: str) -> dict[str, Path]:
    base = repo_root / "output" / "testdata" / "refactor_duplication_audit_smoke"
    reports = {
        "line_count": base / f"line_count_{stamp}.json",
        "code_interpreter": base / f"code_interpreter_{stamp}.json",
        "syntax": base / f"python_syntax_{stamp}.json",
        "bundle_smoke": base / f"bundle_smoke_{stamp}.json",
        "memory_routing": base / f"memory_routing_{stamp}.json",
    }
    write_json(reports["line_count"], {**fake_report("python_line_count"), "file_count": 10, "total_lines": 1000})
    write_json(reports["code_interpreter"], {**fake_report("code_interpreter_report"), "input_count": 4})
    write_json(reports["syntax"], {**fake_report("python_syntax_validation"), "checked_count": 10, "failed_count": 0})
    write_json(reports["bundle_smoke"], {**fake_report("shared_toolbox_ai_to_ai_bundle_smoke"), "bundle_validation_passed": True, "chunked_file_count": 1})
    write_json(reports["memory_routing"], {**fake_report("agent_memory_routing_policy"), "tool_request_count": 12})
    return reports


def repo_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path)


def smoke_args(repo_root: Path, reports: dict[str, Path]) -> SimpleNamespace:
    return SimpleNamespace(
        repo_root=str(repo_root),
        stamp=SMOKE_STAMP,
        root=["Tools/ai", "Tools/validation"],
        report=[],
        line_count_report=[repo_rel(reports["line_count"], repo_root)],
        code_interpreter_report=[repo_rel(reports["code_interpreter"], repo_root)],
        python_syntax_report=[repo_rel(reports["syntax"], repo_root)],
        bundle_smoke_report=[repo_rel(reports["bundle_smoke"], repo_root)],
        memory_routing_report=[repo_rel(reports["memory_routing"], repo_root)],
        input_audit_report=[],
        max_candidates=30,
        output=None,
        markdown_output=None,
    )



def run_broker_smoke(repo_root: Path, reports: dict[str, Path], stamp: str) -> dict[str, Any]:
    request_file = repo_root / "output" / "testdata" / "refactor_duplication_audit_smoke" / f"broker_request_{stamp}.json"
    broker_output = repo_root / "output" / "validation" / f"refactor_duplication_audit_broker_smoke_{stamp}.json"
    broker_markdown = repo_root / "output" / "validation" / f"refactor_duplication_audit_broker_smoke_{stamp}.md"
    tool_output_dir = repo_root / "output" / "ai_runtime_tools" / f"refactor_duplication_audit_broker_smoke_{stamp}"
    request = {
        "schema_version": 1,
        "kind": "refactor_duplication_audit_broker_smoke_request",
        "tool_requests": [
            {
                "id": "refactor_duplication_audit",
                "tool": "build_refactor_duplication_audit",
                "reason": "Validate that the reusable duplication audit is broker-callable.",
                "args": {
                    "root": ["Tools/ai", "Tools/validation"],
                    "line_count_report": repo_rel(reports["line_count"], repo_root),
                    "code_interpreter_report": repo_rel(reports["code_interpreter"], repo_root),
                    "python_syntax_report": repo_rel(reports["syntax"], repo_root),
                    "bundle_smoke_report": repo_rel(reports["bundle_smoke"], repo_root),
                    "memory_routing_report": repo_rel(reports["memory_routing"], repo_root),
                },
            }
        ],
    }
    write_json(request_file, request)
    command = [
        sys.executable,
        "Tools/ai/agent_runtime_tool_broker.py",
        "--repo-root",
        ".",
        "--request-file",
        str(request_file),
        "--tool-output-dir",
        str(tool_output_dir),
        "--timeout-seconds",
        "240",
        "--output",
        str(broker_output),
        "--markdown-output",
        str(broker_markdown),
    ]
    completed = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    broker_report = json.loads(broker_output.read_text(encoding="utf-8-sig")) if broker_output.exists() else {}
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "request_file": repo_rel(request_file, repo_root),
        "broker_output": repo_rel(broker_output, repo_root),
        "broker_markdown": repo_rel(broker_markdown, repo_root),
        "passed": broker_report.get("passed"),
        "tool_request_count": broker_report.get("tool_request_count"),
        "tool_execution_count": broker_report.get("tool_execution_count"),
        "blocked_tool_count": broker_report.get("blocked_tool_count"),
        "failed_tool_count": broker_report.get("failed_tool_count"),
        "provider_execution_performed": broker_report.get("provider_execution_performed"),
        "patch_application_performed": broker_report.get("patch_application_performed"),
        "sqlite_write_performed": broker_report.get("sqlite_write_performed"),
        "persistent_memory_write_performed": broker_report.get("persistent_memory_write_performed"),
    }

def render_smoke_markdown(report: dict[str, Any]) -> str:
    lines = ["# Refactor Duplication Audit Smoke", ""]
    for key in (
        "passed",
        "audit_passed",
        "duplication_candidate_count",
        "manual_review_patch_plan_candidate_count",
        "layering_preserved",
        "builder_delegates_to_common_bundle",
        "chunking_in_common_evidence_layer",
        "validator_reused",
        "smoke_coverage_present",
        "provider_execution_performed",
        "patch_application_performed",
        "sqlite_write_performed",
        "persistent_memory_write_performed",
    ):
        lines.append(f"- {key}: `{report.get(key)}`")
    if report.get("errors"):
        lines.append("")
        lines.append("## Errors")
        for item in report.get("errors", []):
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/validation/refactor_duplication_audit_smoke.json")
    parser.add_argument("--markdown-output", default="output/validation/refactor_duplication_audit_smoke.md")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    fake_reports = create_fake_reports(repo_root, SMOKE_STAMP)
    audit = build_report(smoke_args(repo_root, fake_reports))
    broker_smoke = run_broker_smoke(repo_root, fake_reports, SMOKE_STAMP)
    audit_json = repo_root / "output" / "analysis" / f"refactor_duplication_audit_{SMOKE_STAMP}.json"
    audit_md = repo_root / "output" / "analysis" / f"refactor_duplication_audit_{SMOKE_STAMP}.md"
    write_json(audit_json, audit)
    audit_md.parent.mkdir(parents=True, exist_ok=True)
    audit_md.write_text(render_markdown(audit), encoding="utf-8")

    verification = audit.get("refactor_verification", {}) if isinstance(audit.get("refactor_verification"), dict) else {}
    errors: list[str] = []
    if audit.get("passed") is not True:
        errors.append("audit passed is not true")
    if audit.get("duplication_candidate_count", 0) < 1:
        errors.append("expected at least one duplication candidate")
    if not audit.get("manual_review_patch_plan_candidates"):
        errors.append("expected at least one manual-review patch-plan candidate")
    for key in (
        "layering_preserved",
        "builder_delegates_to_common_bundle",
        "chunking_in_common_evidence_layer",
        "validator_reused",
        "smoke_coverage_present",
    ):
        if verification.get(key) is not True:
            errors.append(f"{key} is not true")
    if broker_smoke.get("passed") is not True:
        errors.append("broker-callable smoke did not pass")
    if broker_smoke.get("tool_execution_count") != 1:
        errors.append("broker-callable smoke expected one executed tool")
    if broker_smoke.get("blocked_tool_count") not in (0, None):
        errors.append("broker-callable smoke should not block the allowlisted tool")

    for key in (
        "provider_execution_performed",
        "patch_application_performed",
        "sqlite_write_performed",
        "persistent_memory_write_performed",
    ):
        if audit.get(key) is not False:
            errors.append(f"{key} must be false")

    report = {
        "schema_version": 1,
        "kind": "refactor_duplication_audit_smoke",
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": [],
        "audit_output": repo_rel(audit_json, repo_root),
        "audit_markdown": repo_rel(audit_md, repo_root),
        "audit_passed": audit.get("passed"),
        "duplication_candidate_count": audit.get("duplication_candidate_count"),
        "manual_review_patch_plan_candidate_count": len(audit.get("manual_review_patch_plan_candidates", [])),
        "layering_preserved": verification.get("layering_preserved"),
        "builder_delegates_to_common_bundle": verification.get("builder_delegates_to_common_bundle"),
        "chunking_in_common_evidence_layer": verification.get("chunking_in_common_evidence_layer"),
        "validator_reused": verification.get("validator_reused"),
        "smoke_coverage_present": verification.get("smoke_coverage_present"),
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
    }
    output = resolve_output_path(repo_root, args.output)
    markdown = resolve_output_path(repo_root, args.markdown_output)
    write_json_report(report, output)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_smoke_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
