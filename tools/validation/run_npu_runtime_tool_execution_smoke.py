#!/usr/bin/env python3
"""Smoke test NPU runtime tool request execution through orchestrator broker."""
from __future__ import annotations

import argparse
import json
import sys
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.ai.run_agent_gpu_npu_parallel_orchestrator import run_npu_runtime_tool_broker_for_audit
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.run_agent_gpu_npu_parallel_orchestrator import run_npu_runtime_tool_broker_for_audit  # type: ignore


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


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# NPU Runtime Tool Execution Smoke", ""]
    for key in (
        "passed",
        "provider_execution_performed",
        "patch_application_performed",
        "sqlite_write_performed",
        "persistent_memory_write_performed",
        "npu_runtime_tool_request_count",
        "npu_runtime_tool_execution_count",
        "npu_runtime_tool_failed_count",
        "npu_runtime_tool_blocked_count",
    ):
        lines.append(f"- {key}: `{report.get(key)}`")
    if report.get("errors"):
        lines.append("")
        lines.append("## Errors")
        for err in report["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    tool_output_dir = resolve_path(repo_root, args.tool_output_dir)
    orchestrator_args = Namespace(
        enable_runtime_tool_broker=True,
        runtime_tool_output_dir=str(tool_output_dir),
        runtime_tool_timeout_seconds=args.timeout_seconds,
    )
    audit_record: dict[str, Any] = {
        "round": 1,
        "audit_output": "output/validation/synthetic_npu_audit.json",
        "npu_tool_requests": [
            {
                "id": "npu_smoke_python_syntax",
                "tool": "check_python_syntax",
                "reason": "Smoke validate NPU requests execute only through broker.",
                "args": {},
                "source": "npu_auditor",
            }
        ],
    }
    broker = run_npu_runtime_tool_broker_for_audit(
        args=orchestrator_args,
        repo_root=repo_root,
        audit_record=audit_record,
    )
    errors: list[str] = []
    if broker.get("passed") is not True:
        errors.append("broker did not pass")
    if int(broker.get("tool_execution_count") or 0) != 1:
        errors.append("expected exactly one broker tool execution")
    if broker.get("provider_execution_performed"):
        errors.append("provider execution was unexpectedly performed")
    if broker.get("patch_application_performed"):
        errors.append("patch application was unexpectedly performed")
    if broker.get("sqlite_write_performed"):
        errors.append("sqlite write was unexpectedly performed")
    if broker.get("persistent_memory_write_performed"):
        errors.append("persistent memory write was unexpectedly performed")

    return {
        "schema_version": 1,
        "kind": "npu_runtime_tool_execution_smoke",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": [],
        "provider_execution_performed": bool(broker.get("provider_execution_performed")),
        "patch_application_performed": bool(broker.get("patch_application_performed")),
        "sqlite_write_performed": bool(broker.get("sqlite_write_performed")),
        "persistent_memory_write_performed": bool(broker.get("persistent_memory_write_performed")),
        "npu_runtime_tool_request_count": int(broker.get("requested_tool_count") or 0),
        "npu_runtime_tool_execution_count": int(broker.get("tool_execution_count") or 0),
        "npu_runtime_tool_failed_count": int(broker.get("failed_tool_count") or 0),
        "npu_runtime_tool_blocked_count": int(broker.get("blocked_tool_count") or 0),
        "npu_runtime_tool_result_count": len(broker.get("tool_results", [])),
        "broker": broker,
        "guardrails": {
            "npu_tool_execution_requires_broker": True,
            "provider_execution_performed": bool(broker.get("provider_execution_performed")),
            "patch_application_performed": bool(broker.get("patch_application_performed")),
            "sqlite_write_performed": bool(broker.get("sqlite_write_performed")),
            "persistent_memory_write_performed": bool(broker.get("persistent_memory_write_performed")),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--tool-output-dir", default="output/validation/npu_runtime_tool_execution_smoke_tools")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--output", default="output/validation/npu_runtime_tool_execution_smoke.json")
    parser.add_argument("--markdown-output", default="output/validation/npu_runtime_tool_execution_smoke.md")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_report(args)
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
        "sqlite_write_performed": report["sqlite_write_performed"],
        "persistent_memory_write_performed": report["persistent_memory_write_performed"],
        "npu_runtime_tool_request_count": report["npu_runtime_tool_request_count"],
        "npu_runtime_tool_execution_count": report["npu_runtime_tool_execution_count"],
        "npu_runtime_tool_failed_count": report["npu_runtime_tool_failed_count"],
        "npu_runtime_tool_blocked_count": report["npu_runtime_tool_blocked_count"],
    }, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
