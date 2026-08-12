#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

try:
    from Tools.ai.run_agent_gpu_npu_parallel_orchestrator import execute_gpu_runtime_tool_requests_from_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.run_agent_gpu_npu_parallel_orchestrator import execute_gpu_runtime_tool_requests_from_report


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Orchestrator GPU Runtime Tool Routing Smoke", ""]
    for key in ["passed", "provider_execution_performed", "patch_application_performed", "sqlite_write_performed", "persistent_memory_write_performed", "gpu_runtime_tool_request_count", "gpu_runtime_tool_execution_count", "gpu_runtime_tool_failed_count", "gpu_runtime_tool_blocked_count"]:
        lines.append(f"- `{key}`: `{report.get(key)}`")
    if report.get("errors"):
        lines.append("")
        lines.append("## Errors")
        for error in report["errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/validation/orchestrator_gpu_runtime_tool_routing_smoke.json")
    parser.add_argument("--markdown-output", default="output/validation/orchestrator_gpu_runtime_tool_routing_smoke.md")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    runtime_args = SimpleNamespace(enable_runtime_tool_broker=True, runtime_tool_output_dir=str(repo_root / "output" / "validation" / "orchestrator_gpu_runtime_tool_routing_smoke_tools"), runtime_tool_timeout_seconds=300, runtime_tool_max_requests_per_round=4)
    gpu_report = {"rounds": [{"round": 1, "parsed_response": {"tool_requests": [{"id": "gpu_orchestrated_python_syntax", "tool": "check_python_syntax", "reason": "Validate orchestrator-routed GPU tool request execution through broker.", "args": {}}]}}]}
    brokers = execute_gpu_runtime_tool_requests_from_report(args=runtime_args, repo_root=repo_root, gpu_report=gpu_report)
    request_count = sum(int(item.get("requested_tool_count") or 0) for item in brokers)
    execution_count = sum(int(item.get("tool_execution_count") or 0) for item in brokers)
    failed_count = sum(int(item.get("failed_tool_count") or 0) for item in brokers)
    blocked_count = sum(int(item.get("blocked_tool_count") or 0) for item in brokers)
    provider_execution = any(bool(item.get("provider_execution_performed")) for item in brokers)
    patch_application = any(bool(item.get("patch_application_performed")) for item in brokers)
    sqlite_write = any(bool(item.get("sqlite_write_performed")) for item in brokers)
    persistent_write = any(bool(item.get("persistent_memory_write_performed")) for item in brokers)
    errors: list[str] = []
    if request_count != 1:
        errors.append(f"expected 1 GPU runtime tool request, got {request_count}")
    if execution_count != 1:
        errors.append(f"expected 1 GPU runtime tool execution, got {execution_count}")
    if failed_count:
        errors.append(f"expected 0 failed tools, got {failed_count}")
    if blocked_count:
        errors.append(f"expected 0 blocked tools, got {blocked_count}")
    if provider_execution:
        errors.append("provider execution unexpectedly performed")
    if patch_application:
        errors.append("patch application unexpectedly performed")
    if sqlite_write:
        errors.append("SQLite write unexpectedly performed")
    if persistent_write:
        errors.append("persistent memory write unexpectedly performed")
    report = {"schema_version": 1, "kind": "orchestrator_gpu_runtime_tool_routing_smoke", "repo_root": str(repo_root), "passed": not errors, "errors": errors, "warnings": [], "provider_execution_performed": provider_execution, "patch_application_performed": patch_application, "sqlite_write_performed": sqlite_write, "persistent_memory_write_performed": persistent_write, "gpu_runtime_tool_request_count": request_count, "gpu_runtime_tool_execution_count": execution_count, "gpu_runtime_tool_failed_count": failed_count, "gpu_runtime_tool_blocked_count": blocked_count, "broker_results": brokers}
    output = resolve_path(repo_root, args.output)
    markdown = resolve_path(repo_root, args.markdown_output)
    write_json(output, report)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "output": str(output), "markdown": str(markdown), "provider_execution_performed": report["provider_execution_performed"], "patch_application_performed": report["patch_application_performed"], "sqlite_write_performed": report["sqlite_write_performed"], "persistent_memory_write_performed": report["persistent_memory_write_performed"], "gpu_runtime_tool_request_count": request_count, "gpu_runtime_tool_execution_count": execution_count, "gpu_runtime_tool_failed_count": failed_count, "gpu_runtime_tool_blocked_count": blocked_count}, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
