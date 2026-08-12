#!/usr/bin/env python3
"""Smoke-test read-only runtime toolbox context injection into the NPU auditor."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def run_command(command: list[str], repo_root: Path) -> tuple[int, str, str]:
    completed = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    return completed.returncode, completed.stdout[-8000:], completed.stderr[-8000:]


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# NPU Runtime Tool Context Smoke", ""]
    for key in (
        "passed",
        "provider_execution_performed",
        "patch_application_performed",
        "npu_tool_context_seen",
        "runtime_tool_context_report_count",
        "sqlite_write_performed",
        "persistent_memory_write_performed",
    ):
        lines.append(f"- {key}: `{report.get(key)}`")
    if report.get("errors"):
        lines.append("")
        lines.append("## Errors")
        for error in report["errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/validation/npu_runtime_tool_context_smoke.json")
    parser.add_argument("--markdown-output", default="output/validation/npu_runtime_tool_context_smoke.md")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    work_dir = repo_root / "output" / "validation" / "npu_runtime_tool_context_smoke"
    gpu_review = work_dir / "synthetic_gpu_review.json"
    broker_report = work_dir / "synthetic_runtime_tool_broker.json"
    audit_json = work_dir / "npu_audit.json"
    audit_md = work_dir / "npu_audit.md"
    context_md = work_dir / "npu_audit_context.md"

    write_json(
        gpu_review,
        {
            "schema_version": 1,
            "kind": "agent_gpu_deep_planning_review",
            "passed": False,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "round_count": 1,
            "recommendation_count": 0,
            "rounds": [
                {"round": 1, "elapsed_seconds": 0.1, "file_count": 0, "files": [], "parsed_response": {}}
            ],
            "decision": {"recommended_next_layer": "inspect_provider_empty_response"},
            "guardrails": {},
        },
    )
    write_json(
        broker_report,
        {
            "schema_version": 1,
            "kind": "agent_runtime_tool_broker",
            "passed": True,
            "tool_request_count": 2,
            "tool_execution_count": 2,
            "blocked_tool_count": 0,
            "failed_tool_count": 0,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
            "tool_results": [
                {"id": "tool_inventory", "tool": "build_agent_agnostic_tool_inventory", "executed": True, "blocked": False, "returncode": 0, "outputs": {}},
                {"id": "python_syntax", "tool": "check_python_syntax", "executed": True, "blocked": False, "returncode": 0, "outputs": {}},
            ],
            "guardrails": {"allowlist_enforced": True},
        },
    )

    command = [
        sys.executable,
        "Tools/ai/run_npu_gpu_deep_review_auditor.py",
        "--repo-root",
        ".",
        "--gpu-review",
        str(gpu_review),
        "--runtime-tool-context-report",
        str(broker_report),
        "--context-output",
        str(context_md),
        "--output",
        str(audit_json),
        "--markdown-output",
        str(audit_md),
    ]
    returncode, stdout, stderr = run_command(command, repo_root)
    audit = read_json(audit_json) if audit_json.exists() else {}
    errors: list[str] = []
    if returncode != 0:
        errors.append(f"auditor returned {returncode}")
    if not audit.get("runtime_tool_context_seen"):
        errors.append("NPU auditor did not see runtime tool context")
    if int(audit.get("runtime_tool_context_report_count") or 0) < 1:
        errors.append("runtime_tool_context_report_count < 1")
    if audit.get("provider_execution_performed"):
        errors.append("provider execution unexpectedly performed")
    if audit.get("patch_application_performed"):
        errors.append("patch application unexpectedly performed")
    guardrails = audit.get("guardrails") if isinstance(audit.get("guardrails"), dict) else {}
    if guardrails.get("persistent_memory_write_performed"):
        errors.append("persistent memory write unexpectedly performed")

    report = {
        "schema_version": 1,
        "kind": "npu_runtime_tool_context_smoke",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": [],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "npu_tool_context_seen": bool(audit.get("runtime_tool_context_seen")),
        "runtime_tool_context_report_count": int(audit.get("runtime_tool_context_report_count") or 0),
        "auditor_returncode": returncode,
        "auditor_stdout_tail": stdout,
        "auditor_stderr_tail": stderr,
        "audit_output": str(audit_json),
        "context_output": str(context_md),
    }
    output = resolve_path(repo_root, args.output)
    markdown = resolve_path(repo_root, args.markdown_output)
    write_json(output, report)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({
        "passed": report["passed"],
        "output": str(output),
        "markdown": str(markdown),
        "provider_execution_performed": report["provider_execution_performed"],
        "patch_application_performed": report["patch_application_performed"],
        "npu_tool_context_seen": report["npu_tool_context_seen"],
        "runtime_tool_context_report_count": report["runtime_tool_context_report_count"],
        "sqlite_write_performed": report["sqlite_write_performed"],
        "persistent_memory_write_performed": report["persistent_memory_write_performed"],
    }, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
