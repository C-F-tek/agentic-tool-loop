#!/usr/bin/env python3
"""Report-only runtime tool broker for IA-Carmine planners.

This broker lets local AI planners request existing repository tools through a
strict allowlist. It never exposes a free shell to the model. Every invocation is
translated into a deterministic command with validated arguments.

Guardrails:
- no provider execution;
- no patch application;
- no Blender runtime execution;
- no SQLite writes;
- no persistent memory writes;
- no Git writes;
- no source writes except explicit report artifacts under output/**.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

try:
    from Tools.validation.report_utils import read_json_report, split_csv_values, write_json_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.validation.report_utils import read_json_report, split_csv_values, write_json_report


DEFAULT_OUTPUT = "output/validation/agent_runtime_tool_broker.json"
DEFAULT_MARKDOWN = "output/validation/agent_runtime_tool_broker.md"
SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    allowed_args: tuple[str, ...]
    builder: Callable[[Path, Path, str, dict[str, Any]], tuple[list[str], dict[str, str]]]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def repo_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path)


def safe_id(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip()
    text = SAFE_ID_RE.sub("_", text).strip("._-")
    return text[:80] or fallback


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def split_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = [value]
    out: list[str] = []
    for item in items:
        for part in str(item).split(","):
            normalized = part.strip().strip("'\"")
            if normalized:
                out.append(normalized)
    return out



def compact_value(value: Any, *, max_chars: int = 2500) -> Any:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return value
    if isinstance(value, str):
        return value[:max_chars] + "\n...[truncated]"
    return text[:max_chars] + "\n...[truncated]"


def validate_request_args(tool_name: str, request_args: dict[str, Any], allowed_args: tuple[str, ...]) -> list[str]:
    errors: list[str] = []
    if not isinstance(request_args, dict):
        return [f"{tool_name}: args must be an object"]
    unknown = sorted(set(request_args) - set(allowed_args))
    if unknown:
        errors.append(f"{tool_name}: unsupported args: {', '.join(unknown)}")
    return errors


def base_outputs(out_dir: Path, request_id: str, stem: str) -> tuple[Path, Path]:
    return out_dir / f"{request_id}_{stem}.json", out_dir / f"{request_id}_{stem}.md"


def build_python_line_count_csv(repo_root: Path, out_dir: Path, request_id: str, args: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    report, markdown = base_outputs(out_dir, request_id, "python_line_count")
    csv_output = out_dir / f"{request_id}_python_line_count.csv"
    command = [
        sys.executable,
        "Tools/validation/build_python_line_count_csv.py",
        "--repo-root",
        ".",
        "--csv-output",
        str(csv_output),
        "--report-output",
        str(report),
        "--markdown-output",
        str(markdown),
    ]
    for value in split_values(args.get("exclude_dir")):
        command.extend(["--exclude-dir", value])
    return command, {"json_report": repo_rel(report, repo_root), "markdown_report": repo_rel(markdown, repo_root), "csv_output": repo_rel(csv_output, repo_root)}


def build_agent_memory_inventory(repo_root: Path, out_dir: Path, request_id: str, args: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    report, markdown = base_outputs(out_dir, request_id, "agent_memory_inventory")
    command = [
        sys.executable,
        "Tools/ai/build_agent_memory_inventory.py",
        "--repo-root",
        ".",
        "--objective",
        str(args.get("objective") or "Runtime read-only memory inventory for IA-Carmine planner."),
        "--memory-db",
        str(args.get("memory_db") or "indexAI/agent_memory/agent_memory.sqlite"),
        "--output",
        str(report),
        "--markdown-output",
        str(markdown),
    ]
    return command, {"json_report": repo_rel(report, repo_root), "markdown_report": repo_rel(markdown, repo_root)}


def build_agent_agnostic_tool_inventory(repo_root: Path, out_dir: Path, request_id: str, args: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    report, markdown = base_outputs(out_dir, request_id, "agent_agnostic_tool_inventory")
    command = [
        sys.executable,
        "Tools/ai/build_agent_agnostic_tool_inventory.py",
        "--repo-root",
        ".",
        "--output",
        str(report),
        "--markdown-output",
        str(markdown),
    ]
    for root in split_values(args.get("root")):
        command.extend(["--root", root])
    return command, {"json_report": repo_rel(report, repo_root), "markdown_report": repo_rel(markdown, repo_root)}


def build_agent_transient_request_context(repo_root: Path, out_dir: Path, request_id: str, args: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    report, markdown = base_outputs(out_dir, request_id, "agent_transient_request_context")
    command = [
        sys.executable,
        "Tools/ai/build_agent_transient_request_context.py",
        "--repo-root",
        ".",
        "--objective",
        str(args.get("objective") or "Runtime request-scoped context for IA-Carmine planner."),
        "--output",
        str(report),
        "--markdown-output",
        str(markdown),
    ]
    for note in split_values(args.get("memory_note")):
        command.extend(["--memory-note", note])
    for raw_file in split_values(args.get("raw_file")):
        command.extend(["--raw-file", raw_file])
    for report_file in split_values(args.get("report_file")):
        command.extend(["--report-file", report_file])
    return command, {"json_report": repo_rel(report, repo_root), "markdown_report": repo_rel(markdown, repo_root)}


def check_python_syntax(repo_root: Path, out_dir: Path, request_id: str, args: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    report = out_dir / f"{request_id}_python_syntax.json"
    command = [
        sys.executable,
        "Tools/validation/check_python_syntax.py",
        "--repo-root",
        ".",
        "--output",
        str(report),
    ]
    return command, {"json_report": repo_rel(report, repo_root)}


def check_validation_report_contract(repo_root: Path, out_dir: Path, request_id: str, args: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    report = out_dir / f"{request_id}_validation_report_contract.json"
    command = [
        sys.executable,
        "Tools/validation/check_validation_report_contract.py",
        "--repo-root",
        ".",
        "--report-dir",
        str(out_dir),
        "--output",
        str(report),
    ]
    for report_file in split_values(args.get("report_file")):
        command.extend(["--report-file", report_file])
    return command, {"json_report": repo_rel(report, repo_root)}


def run_gpu_planner_json_contract_smoke(repo_root: Path, out_dir: Path, request_id: str, args: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    report, markdown = base_outputs(out_dir, request_id, "gpu_planner_json_contract_smoke")
    command = [
        sys.executable,
        "Tools/validation/run_gpu_planner_json_contract_smoke.py",
        "--repo-root",
        ".",
        "--output",
        str(report),
        "--markdown-output",
        str(markdown),
    ]
    return command, {"json_report": repo_rel(report, repo_root), "markdown_report": repo_rel(markdown, repo_root)}


def build_code_interpreter_report(repo_root: Path, out_dir: Path, request_id: str, args: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    report, markdown = base_outputs(out_dir, request_id, "code_interpreter_report")
    command = [
        sys.executable,
        "Tools/ai/build_code_interpreter_report.py",
        "--repo-root",
        ".",
        "--output",
        str(report),
        "--markdown-output",
        str(markdown),
    ]
    inputs = split_values(args.get("input")) or ["Tools/ai", "Tools/validation", "Tools/workflow", "Tools/npu"]
    for item in inputs:
        command.extend(["--input", item])
    return command, {"json_report": repo_rel(report, repo_root), "markdown_report": repo_rel(markdown, repo_root)}



def build_refactor_duplication_audit(repo_root: Path, out_dir: Path, request_id: str, args: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    report, markdown = base_outputs(out_dir, request_id, "refactor_duplication_audit")
    command = [
        sys.executable,
        "Tools/ai/build_refactor_duplication_audit.py",
        "--repo-root",
        ".",
        "--output",
        str(report),
        "--markdown-output",
        str(markdown),
    ]
    multi_args = (
        ("root", "--root"),
        ("report", "--report"),
        ("input_audit_report", "--input-audit-report"),
        ("line_count_report", "--line-count-report"),
        ("code_interpreter_report", "--code-interpreter-report"),
        ("python_syntax_report", "--python-syntax-report"),
        ("bundle_smoke_report", "--bundle-smoke-report"),
        ("memory_routing_report", "--memory-routing-report"),
    )
    for key, flag in multi_args:
        for value in split_values(args.get(key)):
            command.extend([flag, value])
    return command, {"json_report": repo_rel(report, repo_root), "markdown_report": repo_rel(markdown, repo_root)}

def runtime_sqlite_memory(repo_root: Path, out_dir: Path, request_id: str, args: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    report, markdown = base_outputs(out_dir, request_id, "runtime_sqlite_memory")
    command = [
        sys.executable,
        "Tools/ai/agent_runtime_sqlite_memory.py",
        "--repo-root",
        ".",
        "--action",
        str(args.get("action") or "status"),
        "--scope",
        str(args.get("scope") or "operational"),
        "--request-id",
        request_id,
        "--output",
        str(report),
        "--markdown-output",
        str(markdown),
    ]
    for source, flag in (
        ("database", "--database"),
        ("persistent_database", "--persistent-database"),
        ("summary", "--summary"),
        ("content", "--content"),
        ("role", "--role"),
        ("query", "--query"),
        ("confirm", "--confirm"),
    ):
        if args.get(source) is not None:
            command.extend([flag, str(args[source])])
    if args.get("limit") is not None:
        command.extend(["--limit", str(args["limit"])])
    if truthy(args.get("allow_persistent_write")):
        command.append("--allow-persistent-write")
    for tag in split_values(args.get("tag")):
        command.extend(["--tag", tag])
    return command, {"json_report": repo_rel(report, repo_root), "markdown_report": repo_rel(markdown, repo_root)}


TOOL_SPECS: dict[str, ToolSpec] = {
    "build_python_line_count_csv": ToolSpec(
        name="build_python_line_count_csv",
        description="Build full Python line-count CSV/JSON/MD evidence.",
        allowed_args=("exclude_dir",),
        builder=build_python_line_count_csv,
    ),
    "build_agent_memory_inventory": ToolSpec(
        name="build_agent_memory_inventory",
        description="Read-only SQLite/JSONL agent memory inventory.",
        allowed_args=("objective", "memory_db"),
        builder=build_agent_memory_inventory,
    ),
    "build_agent_agnostic_tool_inventory": ToolSpec(
        name="build_agent_agnostic_tool_inventory",
        description="Inventory existing reusable IA-Carmine tools and guardrails.",
        allowed_args=("root",),
        builder=build_agent_agnostic_tool_inventory,
    ),
    "build_agent_transient_request_context": ToolSpec(
        name="build_agent_transient_request_context",
        description="Build request-scoped context from memory notes, raw files and reports.",
        allowed_args=("objective", "memory_note", "raw_file", "report_file"),
        builder=build_agent_transient_request_context,
    ),
    "check_python_syntax": ToolSpec(
        name="check_python_syntax",
        description="Validate Python syntax across repository.",
        allowed_args=(),
        builder=check_python_syntax,
    ),
    "check_validation_report_contract": ToolSpec(
        name="check_validation_report_contract",
        description="Validate validation report contract for a scoped report-dir or explicit report files.",
        allowed_args=("report_file",),
        builder=check_validation_report_contract,
    ),
    "run_gpu_planner_json_contract_smoke": ToolSpec(
        name="run_gpu_planner_json_contract_smoke",
        description="Run GPU planner JSON contract smoke tests without provider.",
        allowed_args=(),
        builder=run_gpu_planner_json_contract_smoke,
    ),
    "build_code_interpreter_report": ToolSpec(
        name="build_code_interpreter_report",
        description="Build static code-interpreter style report over selected roots.",
        allowed_args=("input",),
        builder=build_code_interpreter_report,
    ),

    "build_refactor_duplication_audit": ToolSpec(
        name="build_refactor_duplication_audit",
        description="Build a report-only duplicated-helper/refactor audit over selected code roots and existing evidence reports.",
        allowed_args=(
            "root",
            "report",
            "input_audit_report",
            "line_count_report",
            "code_interpreter_report",
            "python_syntax_report",
            "bundle_smoke_report",
            "memory_routing_report",
        ),
        builder=build_refactor_duplication_audit,
    ),
    "runtime_sqlite_memory": ToolSpec(
        name="runtime_sqlite_memory",
        description="Use protected persistent SQLite read-only or operational scratch SQLite memory under output/**.",
        allowed_args=(
            "action",
            "scope",
            "database",
            "persistent_database",
            "summary",
            "content",
            "role",
            "tag",
            "query",
            "limit",
            "confirm",
            "allow_persistent_write",
        ),
        builder=runtime_sqlite_memory,
    ),
}


def extract_tool_requests(data: dict[str, Any]) -> list[dict[str, Any]]:
    requests = data.get("tool_requests", [])
    if not isinstance(requests, list):
        return []
    return [item for item in requests if isinstance(item, dict)]


def execute_command(command: list[str], repo_root: Path, timeout_seconds: int) -> tuple[int, str, str, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return completed.returncode, completed.stdout[-12000:], completed.stderr[-12000:], ""
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or "", f"TimeoutExpired: {timeout_seconds}s"
    except Exception as exc:  # noqa: BLE001 - broker report must capture failure.
        return 1, "", "", f"{type(exc).__name__}: {exc}"


def execute_tool_request(
    *,
    repo_root: Path,
    out_dir: Path,
    index: int,
    request: dict[str, Any],
    timeout_seconds: int,
    dry_run: bool,
) -> dict[str, Any]:
    request_id = safe_id(request.get("id"), f"tool_{index:03d}")
    tool_name = str(request.get("tool") or "")
    request_args = request.get("args") if isinstance(request.get("args"), dict) else {}
    base_result: dict[str, Any] = {
        "id": request_id,
        "tool": tool_name,
        "reason": str(request.get("reason") or ""),
        "requested": True,
        "executed": False,
        "blocked": False,
        "dry_run": dry_run,
        "persistent_memory_write_authorized": False,
        "returncode": None,
        "errors": [],
        "warnings": [],
        "outputs": {},
        "summary": {},
        "guardrails": {
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
            "persistent_memory_write_count": 0,
            "persistent_memory_write_requires_explicit_confirm": True,
            "operational_sqlite_write_performed": False,
            "operational_memory_write_performed": False,
            "operational_memory_clear_performed": False,
            "blender_runtime_touched": False,
            "git_write_performed": False,
        },
    }

    base_result["persistent_memory_write_authorized"] = (
        tool_name == "runtime_sqlite_memory"
        and str(request_args.get("action") or "") == "remember"
        and str(request_args.get("scope") or "") == "persistent"
        and truthy(request_args.get("allow_persistent_write"))
        and str(request_args.get("confirm") or "") == "persistent_write"
    )

    spec = TOOL_SPECS.get(tool_name)
    if spec is None:
        base_result["blocked"] = True
        base_result["errors"] = [f"tool not allowlisted: {tool_name}"]
        return base_result

    arg_errors = validate_request_args(tool_name, request_args, spec.allowed_args)
    if arg_errors:
        base_result["blocked"] = True
        base_result["errors"] = arg_errors
        return base_result

    command, outputs = spec.builder(repo_root, out_dir, request_id, request_args)
    base_result["command"] = command
    base_result["outputs"] = outputs

    if dry_run:
        return base_result

    returncode, stdout, stderr, error = execute_command(command, repo_root, timeout_seconds)
    base_result["executed"] = True
    base_result["returncode"] = returncode
    base_result["stdout_tail"] = stdout
    base_result["stderr_tail"] = stderr
    if error:
        base_result["errors"].append(error)
    if returncode != 0:
        base_result["errors"].append(f"tool returned {returncode}")

    json_report = outputs.get("json_report")
    if json_report:
        report_data = read_json_report(resolve_path(repo_root, json_report))
        if report_data:
            base_result["summary"] = {
                "kind": report_data.get("kind"),
                "passed": report_data.get("passed"),
                "errors": compact_value(report_data.get("errors", [])),
                "warnings": compact_value(report_data.get("warnings", [])),
                "decision": compact_value(report_data.get("decision", {})),
                "guardrails": compact_value(report_data.get("guardrails", {})),
            }
            guardrails = report_data.get("guardrails") if isinstance(report_data.get("guardrails"), dict) else {}
            base_result["guardrails"].update(
                {
                    "provider_execution_performed": bool(report_data.get("provider_execution_performed") or guardrails.get("provider_execution_performed")),
                    "patch_application_performed": bool(report_data.get("patch_application_performed") or guardrails.get("patch_application_performed")),
                    "sqlite_write_performed": bool(guardrails.get("sqlite_write_performed") or guardrails.get("sqlite_db_committed") or guardrails.get("sqlite_db_touched") is True and not guardrails.get("sqlite_read_only")),
                    "persistent_memory_write_performed": bool(guardrails.get("persistent_memory_write_performed") or guardrails.get("memory_promotion_performed")),
                    "operational_sqlite_write_performed": bool(report_data.get("operational_sqlite_write_performed") or guardrails.get("operational_sqlite_write_performed")),
                    "operational_memory_write_performed": bool(report_data.get("operational_memory_write_performed") or guardrails.get("operational_memory_write_performed")),
                    "operational_memory_clear_performed": bool(report_data.get("operational_memory_clear_performed") or guardrails.get("operational_memory_clear_performed")),
                    "blender_runtime_touched": bool(guardrails.get("blender_runtime_touched")),
                }
            )
    return base_result


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    request_path = resolve_path(repo_root, args.request_file)
    requests_data = read_json_report(request_path)
    tool_requests = extract_tool_requests(requests_data)
    stamp = args.stamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = resolve_path(repo_root, args.tool_output_dir or f"output/ai_runtime_tools/{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    results = [
        execute_tool_request(
            repo_root=repo_root,
            out_dir=out_dir,
            index=index,
            request=request,
            timeout_seconds=args.timeout_seconds,
            dry_run=args.dry_run,
        )
        for index, request in enumerate(tool_requests, start=1)
    ]

    blocked = [item for item in results if item.get("blocked")]
    executed = [item for item in results if item.get("executed")]
    failed = [item for item in results if item.get("errors") and not item.get("blocked")]
    dangerous_guardrail = [
        item
        for item in results
        if item.get("guardrails", {}).get("provider_execution_performed")
        or item.get("guardrails", {}).get("patch_application_performed")
        or (item.get("guardrails", {}).get("sqlite_write_performed") and not item.get("persistent_memory_write_authorized"))
        or (item.get("guardrails", {}).get("persistent_memory_write_performed") and not item.get("persistent_memory_write_authorized"))
        or item.get("guardrails", {}).get("blender_runtime_touched")
        or item.get("guardrails", {}).get("git_write_performed")
    ]
    operational_sqlite_write_count = sum(1 for item in results if item.get("guardrails", {}).get("operational_sqlite_write_performed"))
    persistent_memory_write_count = sum(1 for item in results if item.get("guardrails", {}).get("persistent_memory_write_performed"))
    operational_memory_clear_count = sum(1 for item in results if item.get("guardrails", {}).get("operational_memory_clear_performed"))

    return {
        "schema_version": 1,
        "kind": "agent_runtime_tool_broker",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "request_file": repo_rel(request_path, repo_root),
        "tool_output_dir": repo_rel(out_dir, repo_root),
        "passed": not failed and not dangerous_guardrail,
        "errors": [f"{item.get('id')}: {err}" for item in failed for err in item.get("errors", [])]
        + [f"{item.get('id')}: guardrail violation" for item in dangerous_guardrail],
        "warnings": [f"{item.get('id')}: blocked {item.get('errors')}" for item in blocked],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "sqlite_write_performed": persistent_memory_write_count > 0,
        "persistent_memory_write_performed": persistent_memory_write_count > 0,
        "operational_sqlite_write_performed": operational_sqlite_write_count > 0,
        "operational_sqlite_write_count": operational_sqlite_write_count,
        "persistent_memory_write_count": persistent_memory_write_count,
        "operational_memory_clear_count": operational_memory_clear_count,
        "blender_runtime_execution_performed": False,
        "git_write_performed": False,
        "dry_run": bool(args.dry_run),
        "tool_request_count": len(tool_requests),
        "tool_execution_count": len(executed),
        "blocked_tool_count": len(blocked),
        "failed_tool_count": len(failed),
        "allowlisted_tools": sorted(TOOL_SPECS),
        "tool_results": results,
        "guardrails": {
            "free_shell_exposed": False,
            "allowlist_enforced": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
            "operational_sqlite_write_allowed_under_output": True,
            "operational_sqlite_write_performed": operational_sqlite_write_count > 0,
            "operational_memory_clear_count": operational_memory_clear_count,
            "blender_runtime_touched": False,
            "git_write_performed": False,
            "manual_review_required": True,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agent Runtime Tool Broker", ""]
    for key in (
        "passed",
        "dry_run",
        "tool_request_count",
        "tool_execution_count",
        "blocked_tool_count",
        "failed_tool_count",
        "provider_execution_performed",
        "patch_application_performed",
        "sqlite_write_performed",
        "persistent_memory_write_performed",
        "operational_sqlite_write_performed",
        "operational_sqlite_write_count",
        "operational_memory_clear_count",
        "blender_runtime_execution_performed",
    ):
        lines.append(f"- {key}: `{report.get(key)}`")
    lines.append("")
    lines.append("## Tool results")
    lines.append("")
    for item in report.get("tool_results", []):
        lines.append(f"### `{item.get('id')}` — `{item.get('tool')}`")
        lines.append("")
        lines.append(f"- Executed: `{item.get('executed')}`")
        lines.append(f"- Blocked: `{item.get('blocked')}`")
        lines.append(f"- Return code: `{item.get('returncode')}`")
        lines.append(f"- Outputs: `{item.get('outputs')}`")
        if item.get("errors"):
            lines.append(f"- Errors: `{item.get('errors')}`")
        lines.append("")
    lines.append("## Guardrails")
    lines.append("")
    for key, value in report.get("guardrails", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--tool-output-dir", default=None)
    parser.add_argument("--stamp", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=240)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_report(args)
    output = resolve_path(repo_root, args.output)
    markdown = resolve_path(repo_root, args.markdown_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    write_json_report(report, output)
    markdown.write_text(render_markdown(report), encoding="utf-8")

    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown),
                "tool_request_count": report["tool_request_count"],
                "tool_execution_count": report["tool_execution_count"],
                "blocked_tool_count": report["blocked_tool_count"],
                "failed_tool_count": report["failed_tool_count"],
                "provider_execution_performed": report["provider_execution_performed"],
                "patch_application_performed": report["patch_application_performed"],
                "sqlite_write_performed": report["sqlite_write_performed"],
                "persistent_memory_write_performed": report["persistent_memory_write_performed"],
                "persistent_memory_write_count": report.get("persistent_memory_write_count", 0),
                "operational_sqlite_write_performed": report["operational_sqlite_write_performed"],
                "operational_sqlite_write_count": report["operational_sqlite_write_count"],
                "operational_memory_clear_count": report["operational_memory_clear_count"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
