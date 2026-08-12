#!/usr/bin/env python3
"""Run GPU deep planning and NPU checkpoint audits in parallel.

This is the non-blocking orchestration prototype:

- GPU/Ollama planner runs continuously in its own process;
- checkpoint files are monitored as they appear;
- NPU audits are launched as separate best-effort subprocesses;
- GPU planning does not wait for NPU audit completion;
- NPU audit concurrency is capped to avoid overloading the NPU/runtime;
- final report joins GPU output plus all completed NPU audits.

No patches are applied and no PR is created.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT = "output/ai_pipeline/agent_gpu_npu_parallel_orchestrator.json"
DEFAULT_MARKDOWN = "output/ai_pipeline/agent_gpu_npu_parallel_orchestrator.md"
DEFAULT_GPU_OUTPUT = "output/ai_pipeline/agent_gpu_deep_planning_parallel_gpu.json"
DEFAULT_GPU_MARKDOWN = "output/ai_pipeline/agent_gpu_deep_planning_parallel_gpu.md"
DEFAULT_CHECKPOINT_DIR = "output/ai_pipeline/gpu_deep_planning_parallel_checkpoints"
ROUND_RE = re.compile(r"round_(\d{3})\.json$")

ORCHESTRATOR_RUNTIME_TOOL_BOOTSTRAP_REQUESTS: list[dict[str, object]] = [
    {"id": "orchestrator_bootstrap_tool_inventory", "tool": "build_agent_agnostic_tool_inventory", "reason": "Bootstrap shared runtime tool inventory before GPU/NPU orchestration.", "args": {}},
    {"id": "orchestrator_bootstrap_memory_inventory", "tool": "build_agent_memory_inventory", "reason": "Bootstrap durable project memory inventory before GPU/NPU orchestration.", "args": {}},
    {"id": "orchestrator_bootstrap_persistent_memory_status", "tool": "runtime_sqlite_memory", "reason": "Bootstrap persistent memory status in read-only mode before GPU/NPU orchestration.", "args": {"action": "status", "scope": "persistent"}},
    {"id": "orchestrator_bootstrap_operational_memory_status", "tool": "runtime_sqlite_memory", "reason": "Bootstrap operational scratch memory status before GPU/NPU orchestration.", "args": {"action": "status", "scope": "operational"}},
    {"id": "orchestrator_bootstrap_python_line_count", "tool": "build_python_line_count_csv", "reason": "Bootstrap Python inventory before orchestration.", "args": {}},
    {"id": "orchestrator_bootstrap_python_syntax", "tool": "check_python_syntax", "reason": "Bootstrap Python syntax baseline before orchestration.", "args": {}},
    {"id": "orchestrator_bootstrap_gpu_contract_smoke", "tool": "run_gpu_planner_json_contract_smoke", "reason": "Bootstrap GPU JSON contract validation before orchestration.", "args": {}},
]


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


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_command_async(command: list[str], repo_root: Path) -> subprocess.Popen[str]:
    return subprocess.Popen(
        command,
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


def run_command_sync(command: list[str], repo_root: Path, timeout_seconds: int) -> tuple[int, str, str, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        return completed.returncode, completed.stdout[-12000:], completed.stderr[-12000:], ""
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or "", f"TimeoutExpired: {timeout_seconds}s"
    except Exception as exc:  # noqa: BLE001 - report-only runtime broker execution must be captured.
        return 1, "", "", f"{type(exc).__name__}: {exc}"




def run_orchestrator_runtime_tool_broker_packet(
    *,
    args: argparse.Namespace,
    repo_root: Path,
    tool_requests: list[dict[str, Any]],
    request_kind: str,
    output_subdir: str,
    output_prefix: str,
    source: str,
) -> dict[str, Any]:
    if not getattr(args, "enable_runtime_tool_broker", False):
        return {"enabled": False, "executed": False, "source": source, "requested_tool_count": len(tool_requests), "tool_execution_count": 0, "blocked_tool_count": 0, "failed_tool_count": 0, "tool_results": [], "guardrails": {"broker_execution_requires_enable_runtime_tool_broker": True, "patch_application_performed": False, "persistent_memory_write_performed": False}}
    if not tool_requests:
        return {"enabled": True, "executed": False, "source": source, "requested_tool_count": 0, "tool_execution_count": 0, "blocked_tool_count": 0, "failed_tool_count": 0, "tool_results": [], "guardrails": {"patch_application_performed": False, "persistent_memory_write_performed": False}}
    output_root = resolve_path(repo_root, args.runtime_tool_output_dir)
    out_dir = output_root / output_subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    request_file = out_dir / f"{output_prefix}_tool_requests.json"
    broker_output = out_dir / f"{output_prefix}_runtime_tool_broker.json"
    broker_markdown = out_dir / f"{output_prefix}_runtime_tool_broker.md"
    request_packet = {"schema_version": 1, "kind": request_kind, "repo_root": str(repo_root), "source": source, "tool_requests": tool_requests, "guardrails": {"free_shell_allowed": False, "broker_allowlist_required": True, "patch_application_allowed": False, "provider_execution_allowed": False, "persistent_memory_write_allowed": False, "manual_review_required": True}}
    write_json(request_file, request_packet)
    command = [sys.executable, "Tools/ai/agent_runtime_tool_broker.py", "--repo-root", ".", "--request-file", str(request_file), "--tool-output-dir", str(out_dir), "--timeout-seconds", str(args.runtime_tool_timeout_seconds), "--output", str(broker_output), "--markdown-output", str(broker_markdown)]
    returncode, stdout, stderr, error = run_command_sync(command, repo_root, args.runtime_tool_timeout_seconds + 30)
    broker_report: dict[str, Any] = {}
    broker_output_exists = broker_output.exists()
    if broker_output_exists:
        try:
            broker_report = read_json(broker_output)
        except Exception as exc:
            error = f"{error} {type(exc).__name__}: {exc}".strip()
    elif not error:
        error = "runtime_tool_broker_output_missing"
    return {"enabled": True, "executed": True, "source": source, "requested_tool_count": len(tool_requests), "command": command, "returncode": returncode, "stdout_tail": stdout, "stderr_tail": stderr, "error": error, "request_file": repo_rel(request_file, repo_root), "broker_output": repo_rel(broker_output, repo_root), "broker_markdown": repo_rel(broker_markdown, repo_root), "broker_output_exists": broker_output_exists, "passed": broker_report.get("passed"), "tool_request_count": broker_report.get("tool_request_count", len(tool_requests)), "tool_execution_count": broker_report.get("tool_execution_count", 0), "blocked_tool_count": broker_report.get("blocked_tool_count", 0), "failed_tool_count": broker_report.get("failed_tool_count", 0), "provider_execution_performed": broker_report.get("provider_execution_performed", False), "patch_application_performed": broker_report.get("patch_application_performed", False), "sqlite_write_performed": broker_report.get("sqlite_write_performed", False), "persistent_memory_write_performed": broker_report.get("persistent_memory_write_performed", False), "operational_sqlite_write_performed": broker_report.get("operational_sqlite_write_performed", False), "tool_results": broker_report.get("tool_results", [])[:8], "guardrails": broker_report.get("guardrails", {})}


def run_orchestrator_runtime_tool_bootstrap(args: argparse.Namespace, repo_root: Path) -> dict[str, Any]:
    if not getattr(args, "enable_runtime_tool_broker", False):
        return {"enabled": False, "executed": False, "bootstrap": True, "requested_tool_count": 0, "tool_results": []}
    if getattr(args, "disable_runtime_tool_bootstrap", False):
        return {"enabled": True, "executed": False, "bootstrap": True, "disabled": True, "requested_tool_count": 0, "tool_results": []}
    result = run_orchestrator_runtime_tool_broker_packet(args=args, repo_root=repo_root, tool_requests=[dict(item) for item in ORCHESTRATOR_RUNTIME_TOOL_BOOTSTRAP_REQUESTS], request_kind="orchestrator_runtime_tool_bootstrap_requests", output_subdir="round_000", output_prefix="round_000", source="orchestrator_bootstrap")
    result["bootstrap"] = True
    result["bootstrap_tool_ids"] = [str(item["id"]) for item in ORCHESTRATOR_RUNTIME_TOOL_BOOTSTRAP_REQUESTS]
    return result


def collect_gpu_tool_request_entries(gpu_report: dict[str, Any], max_requests_per_round: int) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    rounds = gpu_report.get("rounds", [])
    if not isinstance(rounds, list):
        return entries
    for round_item in rounds:
        if not isinstance(round_item, dict):
            continue
        parsed = round_item.get("parsed_response") if isinstance(round_item.get("parsed_response"), dict) else {}
        raw_requests = parsed.get("tool_requests") if isinstance(parsed.get("tool_requests"), list) else []
        tool_requests: list[dict[str, Any]] = []
        for index, item in enumerate(raw_requests[:max_requests_per_round], start=1):
            if not isinstance(item, dict):
                continue
            request = dict(item)
            request.setdefault("id", f"gpu_round_{int(round_item.get('round') or 0):03d}_tool_{index:03d}")
            request.setdefault("reason", "GPU planner requested additional report-only tool evidence.")
            request["source"] = "gpu_planner"
            tool_requests.append(request)
        if tool_requests:
            entries.append({"round": int(round_item.get("round") or 0), "tool_requests": tool_requests})
    return entries


def execute_gpu_runtime_tool_requests_from_report(*, args: argparse.Namespace, repo_root: Path, gpu_report: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for entry in collect_gpu_tool_request_entries(gpu_report, args.runtime_tool_max_requests_per_round):
        round_id = int(entry.get("round") or 0)
        broker = run_orchestrator_runtime_tool_broker_packet(args=args, repo_root=repo_root, tool_requests=entry.get("tool_requests", []), request_kind="gpu_planner_orchestrated_runtime_tool_requests", output_subdir=f"gpu_round_{round_id:03d}", output_prefix=f"gpu_round_{round_id:03d}", source="gpu_planner")
        broker["round"] = round_id
        results.append(broker)
    return results


def checkpoint_round(path: Path) -> int | None:
    match = ROUND_RE.search(path.name)
    if not match:
        return None
    return int(match.group(1))


def collect_stdout_stderr(process: subprocess.Popen[str]) -> tuple[str, str]:
    stdout = ""
    stderr = ""
    try:
        out, err = process.communicate(timeout=1)
        stdout = out or ""
        stderr = err or ""
    except subprocess.TimeoutExpired:
        return "", ""
    return stdout[-12000:], stderr[-12000:]


def build_gpu_command(args: argparse.Namespace, repo_root: Path, checkpoint_dir: Path, gpu_output: Path, gpu_markdown: Path) -> list[str]:
    command = [
        sys.executable,
        "Tools/ai/run_agent_gpu_deep_planning_supervised.py",
        "--repo-root",
        ".",
        "--use-ollama",
        "--budget-minutes",
        str(args.budget_minutes),
        "--max-rounds",
        str(args.max_rounds),
        "--files-per-round",
        str(args.files_per_round),
        "--max-context-files",
        str(args.max_context_files),
        "--max-chars-per-file",
        str(args.max_chars_per_file),
        "--max-new-tokens",
        str(args.max_new_tokens),
        "--keep-alive",
        args.keep_alive,
        "--evidence",
        args.evidence,
        "--refined-review",
        args.refined_review,
        "--checkpoint-dir",
        str(checkpoint_dir),
        "--output",
        str(gpu_output),
        "--markdown-output",
        str(gpu_markdown),
    ]
    if args.ollama_model:
        command.extend(["--ollama-model", args.ollama_model])
    if args.ollama_base_url:
        command.extend(["--ollama-base-url", args.ollama_base_url])
    if args.enable_runtime_tool_broker and getattr(args, "gpu_runner_direct_runtime_tool_broker", False):
        command.append("--enable-runtime-tool-broker")
        command.extend(["--runtime-tool-output-dir", args.runtime_tool_output_dir])
        command.extend(["--runtime-tool-timeout-seconds", str(args.runtime_tool_timeout_seconds)])
        command.extend(["--runtime-tool-max-requests-per-round", str(args.runtime_tool_max_requests_per_round)])
        if args.disable_runtime_tool_bootstrap:
            command.append("--disable-runtime-tool-bootstrap")
    bootstrap_report = getattr(args, "orchestrator_runtime_tool_bootstrap_result", {})
    if args.enable_runtime_tool_broker and isinstance(bootstrap_report, dict) and bootstrap_report.get("broker_output"):
        command.extend(["--report-file", str(bootstrap_report["broker_output"])])
    for report_file in args.report_file:
        command.extend(["--report-file", report_file])
    for context_root in args.context_root:
        command.extend(["--context-root", context_root])
    return command


def collect_runtime_tool_context_reports(args: argparse.Namespace, repo_root: Path, round_id: int) -> list[Path]:
    if not getattr(args, "enable_runtime_tool_broker", False):
        return []
    base = resolve_path(repo_root, args.runtime_tool_output_dir)
    candidates = [
        base / "round_000" / "round_000_runtime_tool_broker.json",
        base / f"round_{round_id:03d}" / f"round_{round_id:03d}_runtime_tool_broker.json",
    ]
    reports: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve(strict=False))
        if key in seen or not candidate.exists():
            continue
        seen.add(key)
        reports.append(candidate)
    return reports


def run_npu_runtime_tool_broker_for_audit(
    *,
    args: argparse.Namespace,
    repo_root: Path,
    audit_record: dict[str, Any],
) -> dict[str, Any]:
    tool_requests = audit_record.get("npu_tool_requests") if isinstance(audit_record.get("npu_tool_requests"), list) else []
    round_id = int(audit_record.get("round") or 0)
    if not getattr(args, "enable_runtime_tool_broker", False):
        return {
            "enabled": False,
            "executed": False,
            "requested_tool_count": len(tool_requests),
            "tool_execution_count": 0,
            "blocked_tool_count": 0,
            "failed_tool_count": 0,
            "tool_results": [],
            "guardrails": {
                "broker_execution_requires_enable_runtime_tool_broker": True,
                "patch_application_performed": False,
                "persistent_memory_write_performed": False,
            },
        }
    if not tool_requests:
        return {
            "enabled": True,
            "executed": False,
            "requested_tool_count": 0,
            "tool_execution_count": 0,
            "blocked_tool_count": 0,
            "failed_tool_count": 0,
            "tool_results": [],
            "guardrails": {
                "patch_application_performed": False,
                "persistent_memory_write_performed": False,
            },
        }

    output_root = resolve_path(repo_root, args.runtime_tool_output_dir)
    round_dir = output_root / f"npu_round_{round_id:03d}"
    round_dir.mkdir(parents=True, exist_ok=True)
    request_file = round_dir / f"npu_round_{round_id:03d}_tool_requests.json"
    broker_output = round_dir / f"npu_round_{round_id:03d}_runtime_tool_broker.json"
    broker_markdown = round_dir / f"npu_round_{round_id:03d}_runtime_tool_broker.md"
    request_packet = {
        "schema_version": 1,
        "kind": "npu_auditor_runtime_tool_requests",
        "repo_root": str(repo_root),
        "round": round_id,
        "source_audit": audit_record.get("audit_output"),
        "tool_requests": tool_requests,
        "guardrails": {
            "free_shell_allowed": False,
            "broker_allowlist_required": True,
            "patch_application_allowed": False,
            "provider_execution_allowed": False,
            "persistent_memory_write_allowed": False,
            "manual_review_required": True,
        },
    }
    write_json(request_file, request_packet)
    command = [
        sys.executable,
        "Tools/ai/agent_runtime_tool_broker.py",
        "--repo-root",
        ".",
        "--request-file",
        str(request_file),
        "--tool-output-dir",
        str(round_dir),
        "--timeout-seconds",
        str(args.runtime_tool_timeout_seconds),
        "--output",
        str(broker_output),
        "--markdown-output",
        str(broker_markdown),
    ]
    returncode, stdout, stderr, error = run_command_sync(command, repo_root, args.runtime_tool_timeout_seconds + 30)
    broker_report: dict[str, Any] = {}
    broker_output_exists = broker_output.exists()
    if broker_output_exists:
        try:
            broker_report = read_json(broker_output)
        except Exception as exc:  # noqa: BLE001
            error = f"{error} {type(exc).__name__}: {exc}".strip()
    elif not error:
        error = "npu_runtime_tool_broker_output_missing"

    return {
        "enabled": True,
        "executed": True,
        "requested_tool_count": len(tool_requests),
        "command": command,
        "returncode": returncode,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "error": error,
        "request_file": repo_rel(request_file, repo_root),
        "broker_output": repo_rel(broker_output, repo_root),
        "broker_markdown": repo_rel(broker_markdown, repo_root),
        "broker_output_exists": broker_output_exists,
        "passed": broker_report.get("passed"),
        "tool_request_count": broker_report.get("tool_request_count", len(tool_requests)),
        "tool_execution_count": broker_report.get("tool_execution_count", 0),
        "blocked_tool_count": broker_report.get("blocked_tool_count", 0),
        "failed_tool_count": broker_report.get("failed_tool_count", 0),
        "provider_execution_performed": broker_report.get("provider_execution_performed", False),
        "patch_application_performed": broker_report.get("patch_application_performed", False),
        "sqlite_write_performed": broker_report.get("sqlite_write_performed", False),
        "persistent_memory_write_performed": broker_report.get("persistent_memory_write_performed", False),
        "operational_sqlite_write_performed": broker_report.get("operational_sqlite_write_performed", False),
        "tool_results": broker_report.get("tool_results", [])[:8],
        "guardrails": broker_report.get("guardrails", {}),
    }


def build_npu_command(args: argparse.Namespace, repo_root: Path, checkpoint: Path, audit_json: Path) -> list[str]:
    command = [
        sys.executable,
        "Tools/ai/run_npu_gpu_deep_review_auditor.py",
        "--repo-root",
        ".",
        "--gpu-review",
        str(checkpoint),
        "--output",
        str(audit_json),
        "--markdown-output",
        str(audit_json.with_suffix(".md")),
        "--context-output",
        str(audit_json.with_name(audit_json.stem + "_context.md")),
        "--npu-output",
        str(audit_json.with_name(audit_json.stem + "_npu.md")),
        "--npu-notes-output",
        str(audit_json.with_name(audit_json.stem + "_npu_notes.md")),
        "--npu-metadata-output",
        str(audit_json.with_name(audit_json.stem + "_metadata.json")),
        "--timeout-seconds",
        str(args.npu_auditor_timeout_seconds),
        "--max-context-chars",
        str(args.npu_max_context_chars),
        "--max-prompt-chars",
        str(args.npu_max_prompt_chars),
        "--max-new-tokens",
        str(args.npu_max_new_tokens),
    ]
    round_id = checkpoint_round(checkpoint) or 0
    for context_report in collect_runtime_tool_context_reports(args, repo_root, round_id):
        command.extend(["--runtime-tool-context-report", str(context_report)])
    if args.run_npu_auditor_provider:
        command.append("--run-npu")
    else:
        command.extend(["--run-npu", "--metadata-only"])
    if args.npu_python:
        command.extend(["--npu-python", args.npu_python])
    return command


def should_launch_npu_audit(round_id: int, every_rounds: int) -> bool:
    return round_id == 1 or round_id % max(1, every_rounds) == 0


def launch_due_audits(
    *,
    args: argparse.Namespace,
    repo_root: Path,
    checkpoint_dir: Path,
    launched_rounds: set[int],
    active_audits: dict[int, subprocess.Popen[str]],
    audit_records: list[dict[str, Any]],
) -> None:
    if len(active_audits) >= args.max_concurrent_npu_audits:
        return
    checkpoints = sorted(checkpoint_dir.glob("round_*.json"), key=lambda path: checkpoint_round(path) or 0)
    for checkpoint in checkpoints:
        round_id = checkpoint_round(checkpoint)
        if round_id is None or round_id in launched_rounds:
            continue
        effective_every_rounds = effective_npu_auditor_every_rounds(args, audit_records)
        if not should_launch_npu_audit(round_id, effective_every_rounds):
            launched_rounds.add(round_id)
            continue
        if len(active_audits) >= args.max_concurrent_npu_audits:
            return
        audit_json = checkpoint.with_name(f"round_{round_id:03d}_npu_async_audit.json")
        command = build_npu_command(args, repo_root, checkpoint, audit_json)
        process = run_command_async(command, repo_root)
        launched_rounds.add(round_id)
        active_audits[round_id] = process
        audit_records.append(
            {
                "round": round_id,
                "checkpoint": repo_rel(checkpoint, repo_root),
                "audit_output": repo_rel(audit_json, repo_root),
                "started_at": now_iso(),
                "status": "running",
                "command": command,
                "npu_lane_mode_at_launch": npu_lane_diagnostics(args, audit_records).get("mode"),
                "npu_effective_auditor_every_rounds_at_launch": effective_npu_auditor_every_rounds(args, audit_records),
            }
        )


def harvest_finished_audits(
    *,
    repo_root: Path,
    active_audits: dict[int, subprocess.Popen[str]],
    audit_records: list[dict[str, Any]],
) -> None:
    for round_id, process in list(active_audits.items()):
        if process.poll() is None:
            continue
        stdout, stderr = collect_stdout_stderr(process)
        for record in audit_records:
            if record.get("round") == round_id and record.get("status") == "running":
                record["finished_at"] = now_iso()
                record["status"] = "finished"
                record["returncode"] = process.returncode
                record["stdout_tail"] = stdout
                record["stderr_tail"] = stderr
                audit_path = resolve_path(repo_root, record["audit_output"])
                if audit_path.exists():
                    try:
                        data = read_json(audit_path)
                        nested = data.get("npu_auditor", {})
                        record.update(
                            {
                                "classification": nested.get("classification"),
                                "provider_execution_requested": data.get("provider_execution_requested", nested.get("provider_execution_requested")),
                                "provider_load_attempted": data.get("provider_load_attempted", nested.get("provider_load_attempted")),
                                "provider_execution_succeeded": data.get("provider_execution_succeeded", nested.get("provider_execution_succeeded")),
                                "provider_execution_performed": data.get("provider_execution_performed", nested.get("provider_execution_performed")),
                                "dependency_missing": data.get("dependency_missing", nested.get("dependency_missing")),
                                "warnings": data.get("warnings", []),
                                "runtime_tool_context_seen": data.get("runtime_tool_context_seen"),
                                "runtime_tool_context_report_count": data.get("runtime_tool_context_report_count"),
                                "npu_tool_request_count": data.get("tool_request_count"),
                                "npu_valid_tool_request_count": data.get("valid_tool_request_count"),
                                "npu_invalid_tool_request_count": data.get("invalid_tool_request_count"),
                                "npu_deterministic_tool_fallback_used": data.get("npu_deterministic_tool_fallback_used"),
                                "npu_deterministic_tool_fallback_count": data.get("npu_deterministic_tool_fallback_count"),
                                "npu_tool_requests": data.get("tool_requests", [])[:8],
                                "gpu_review_blocked": data.get("decision", {}).get("gpu_review_blocked"),
                            }
                        )
                    except Exception as exc:  # noqa: BLE001
                        record["parse_error"] = f"{type(exc).__name__}: {exc}"
                break
        del active_audits[round_id]


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def gpu_direct_runtime_tool_counters(gpu_report: dict[str, Any]) -> dict[str, Any]:
    """Extract direct GPU-runner runtime-tool counters without bootstrap double counting."""

    bootstrap_request_count = safe_int(gpu_report.get("runtime_tool_bootstrap_request_count"))
    bootstrap_execution_count = safe_int(gpu_report.get("runtime_tool_bootstrap_execution_count"))
    bootstrap_failed_count = safe_int(gpu_report.get("runtime_tool_bootstrap_failed_count"))
    bootstrap_blocked_count = safe_int(gpu_report.get("runtime_tool_bootstrap_blocked_count"))
    direct_request_count = max(0, safe_int(gpu_report.get("runtime_tool_request_count")) - bootstrap_request_count)
    direct_execution_count = max(0, safe_int(gpu_report.get("runtime_tool_execution_count")) - bootstrap_execution_count)
    direct_failed_count = max(0, safe_int(gpu_report.get("runtime_tool_failed_count")) - bootstrap_failed_count)
    direct_blocked_count = max(0, safe_int(gpu_report.get("runtime_tool_blocked_count")) - bootstrap_blocked_count)
    return {
        "gpu_direct_runtime_tool_request_count": direct_request_count,
        "gpu_direct_runtime_tool_execution_count": direct_execution_count,
        "gpu_direct_runtime_tool_failed_count": direct_failed_count,
        "gpu_direct_runtime_tool_blocked_count": direct_blocked_count,
        "gpu_direct_runtime_tool_provider_request_count": safe_int(gpu_report.get("runtime_tool_provider_request_count")),
        "gpu_direct_runtime_tool_provider_request_execution_count": safe_int(gpu_report.get("runtime_tool_provider_request_execution_count")),
        "gpu_direct_runtime_tool_feedback_context_report_count": safe_int(gpu_report.get("runtime_tool_feedback_context_report_count")),
        "gpu_direct_deterministic_runtime_tool_fallback_request_count": safe_int(gpu_report.get("deterministic_runtime_tool_fallback_request_count")),
        "gpu_direct_deterministic_runtime_tool_fallback_execution_count": safe_int(gpu_report.get("deterministic_runtime_tool_fallback_execution_count")),
    }


def parse_iso_seconds(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def audit_elapsed_seconds(audit_record: dict[str, Any]) -> float | None:
    explicit = audit_record.get("elapsed_seconds")
    if explicit is not None:
        try:
            return float(explicit)
        except (TypeError, ValueError):
            pass
    start = parse_iso_seconds(audit_record.get("started_at"))
    finish = parse_iso_seconds(audit_record.get("finished_at"))
    if not start or not finish:
        return None
    return max(0.0, (finish - start).total_seconds())


def npu_lane_diagnostics(args: argparse.Namespace, audit_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify the NPU audit lane without making it blocking."""

    provider_requested = bool(getattr(args, "run_npu_auditor_provider", False))
    threshold = float(getattr(args, "npu_slow_audit_threshold_seconds", 60) or 60)
    base_every = max(1, safe_int(getattr(args, "npu_auditor_every_rounds", 1), 1))
    slow_every = max(base_every, safe_int(getattr(args, "npu_slow_auditor_every_rounds", max(base_every, 4)), max(base_every, 4)))
    elapsed_values = [value for value in (audit_elapsed_seconds(item) for item in audit_records) if value is not None]
    finished_count = sum(1 for item in audit_records if item.get("status") == "finished")
    running_count = sum(1 for item in audit_records if item.get("status") == "running")
    success_count = sum(1 for item in audit_records if item.get("provider_execution_succeeded") is True or item.get("classification") == "usable_audit_text")
    failed_count = sum(1 for item in audit_records if item.get("status") == "finished" and item.get("returncode") not in (None, 0))
    avg_elapsed = round(sum(elapsed_values) / len(elapsed_values), 3) if elapsed_values else 0.0
    max_elapsed = round(max(elapsed_values), 3) if elapsed_values else 0.0

    if not provider_requested:
        mode = "metadata_only"
    elif not audit_records:
        mode = "skipped"
    elif running_count:
        mode = "slow"
    elif max_elapsed >= threshold:
        mode = "slow"
    elif failed_count and success_count == 0:
        mode = "degraded"
    else:
        mode = "active"

    effective_every = slow_every if mode in {"slow", "degraded"} else base_every
    return {
        "mode": mode,
        "provider_requested": provider_requested,
        "audit_count": len(audit_records),
        "finished_count": finished_count,
        "running_count": running_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "avg_elapsed_seconds": avg_elapsed,
        "max_elapsed_seconds": max_elapsed,
        "slow_threshold_seconds": threshold,
        "base_auditor_every_rounds": base_every,
        "slow_auditor_every_rounds": slow_every,
        "effective_auditor_every_rounds": effective_every,
        "non_blocking": True,
    }


def effective_npu_auditor_every_rounds(args: argparse.Namespace, audit_records: list[dict[str, Any]]) -> int:
    return safe_int(npu_lane_diagnostics(args, audit_records).get("effective_auditor_every_rounds"), max(1, safe_int(getattr(args, "npu_auditor_every_rounds", 1), 1)))


def apply_orchestrator_direct_gpu_and_lane_diagnostics(
    report: dict[str, Any],
    *,
    args: argparse.Namespace,
    gpu_report: dict[str, Any],
    audit_records: list[dict[str, Any]],
) -> None:
    """Propagate direct GPU-runner counters and adaptive lane state into the orchestrator report."""

    gpu_direct = gpu_direct_runtime_tool_counters(gpu_report)
    npu_lane = npu_lane_diagnostics(args, audit_records)
    gpu_lane = {
        "mode": "primary_fast_loop",
        "provider_execution_performed": bool(gpu_report.get("provider_execution_performed")),
        "round_count": safe_int(gpu_report.get("round_count")),
        "recommendation_count": safe_int(gpu_report.get("recommendation_count")),
        "empty_recommendations_reason": gpu_report.get("empty_recommendations_reason", ""),
        "direct_runtime_tool_execution_count": gpu_direct["gpu_direct_runtime_tool_execution_count"],
        "direct_provider_request_execution_count": gpu_direct["gpu_direct_runtime_tool_provider_request_execution_count"],
        "feedback_context_report_count": gpu_direct["gpu_direct_runtime_tool_feedback_context_report_count"],
    }

    report.update(gpu_direct)
    report["gpu_lane_mode"] = gpu_lane["mode"]
    report["gpu_lane"] = gpu_lane
    report["npu_lane_mode"] = npu_lane["mode"]
    report["npu_lane"] = npu_lane

    report["runtime_tool_provider_request_count"] = max(
        safe_int(report.get("runtime_tool_provider_request_count")),
        gpu_direct["gpu_direct_runtime_tool_provider_request_count"]
        + safe_int(report.get("gpu_orchestrated_runtime_tool_request_count"))
        + safe_int(report.get("npu_runtime_tool_request_count")),
    )
    report["runtime_tool_provider_request_execution_count"] = max(
        safe_int(report.get("runtime_tool_provider_request_execution_count")),
        gpu_direct["gpu_direct_runtime_tool_provider_request_execution_count"]
        + safe_int(report.get("gpu_orchestrated_runtime_tool_execution_count"))
        + safe_int(report.get("npu_runtime_tool_execution_count")),
    )
    report["deterministic_runtime_tool_fallback_execution_count"] = max(
        safe_int(report.get("deterministic_runtime_tool_fallback_execution_count")),
        gpu_direct["gpu_direct_deterministic_runtime_tool_fallback_execution_count"],
    )
    report["runtime_tool_feedback_context_report_count"] = max(
        safe_int(report.get("runtime_tool_feedback_context_report_count")),
        gpu_direct["gpu_direct_runtime_tool_feedback_context_report_count"],
    )

    gpu_summary = report.get("gpu_summary")
    if isinstance(gpu_summary, dict):
        gpu_summary.update(gpu_direct)
        gpu_summary["gpu_lane"] = gpu_lane
        gpu_summary["runtime_tool_feedback_context_report_count"] = report["runtime_tool_feedback_context_report_count"]

    decision = report.get("decision")
    if isinstance(decision, dict):
        decision["gpu_lane_mode"] = gpu_lane["mode"]
        decision["npu_lane_mode"] = npu_lane["mode"]
        decision["gpu_direct_runtime_tool_provider_request_execution_count"] = gpu_direct["gpu_direct_runtime_tool_provider_request_execution_count"]
        decision["runtime_tool_feedback_context_report_count"] = report["runtime_tool_feedback_context_report_count"]
        decision["npu_effective_auditor_every_rounds"] = npu_lane["effective_auditor_every_rounds"]


def build_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agent GPU/NPU Parallel Orchestrator", ""]
    for key in [
        "passed",
        "provider_execution_performed",
        "patch_application_performed",
        "gpu_returncode",
        "elapsed_seconds",
        "npu_audit_count",
        "npu_audit_success_count",
        "npu_tool_context_seen_count",
        "npu_tool_request_count",
        "npu_runtime_tool_request_count",
        "npu_runtime_tool_execution_count",
        "npu_runtime_tool_failed_count",
        "npu_runtime_tool_blocked_count",
        "npu_runtime_tool_result_count",
        "gpu_recommendation_count",
        "gpu_empty_recommendations_reason",
        "gpu_evidence_ready_for_manual_patch_count",
        "runtime_tool_broker_enabled",
        "runtime_tool_request_count",
        "runtime_tool_execution_count",
        "runtime_tool_failed_count",
        "runtime_tool_blocked_count",
        "runtime_tool_result_count",
    ]:
        lines.append(f"- `{key}`: `{report.get(key)}`")
    lines.append("")
    lines.append("## Decision")
    for key, value in report.get("decision", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## NPU Audits")
    for audit in report.get("npu_audits", []):
        lines.append(f"- round `{audit.get('round')}` status=`{audit.get('status')}` class=`{audit.get('classification')}` success=`{audit.get('provider_execution_succeeded')}`")
    return "\n".join(lines) + "\n"


def run_orchestrator(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    start = time.perf_counter()
    checkpoint_dir = resolve_path(repo_root, args.checkpoint_dir)
    gpu_output = resolve_path(repo_root, args.gpu_output)
    gpu_markdown = resolve_path(repo_root, args.gpu_markdown_output)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    orchestrator_runtime_tool_bootstrap = run_orchestrator_runtime_tool_bootstrap(args, repo_root)
    setattr(args, "orchestrator_runtime_tool_bootstrap_result", orchestrator_runtime_tool_bootstrap)
    gpu_command = build_gpu_command(args, repo_root, checkpoint_dir, gpu_output, gpu_markdown)
    gpu_process = run_command_async(gpu_command, repo_root)
    launched_rounds: set[int] = set()
    active_audits: dict[int, subprocess.Popen[str]] = {}
    audit_records: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []

    try:
        while gpu_process.poll() is None:
            launch_due_audits(
                args=args,
                repo_root=repo_root,
                checkpoint_dir=checkpoint_dir,
                launched_rounds=launched_rounds,
                active_audits=active_audits,
                audit_records=audit_records,
            )
            harvest_finished_audits(repo_root=repo_root, active_audits=active_audits, audit_records=audit_records)
            time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        warnings.append("KeyboardInterrupt received; terminating GPU process and active NPU audits")
        gpu_process.terminate()
        for process in active_audits.values():
            process.terminate()

    gpu_stdout, gpu_stderr = collect_stdout_stderr(gpu_process)
    # Launch audits for final checkpoints that appeared just before GPU exit.
    launch_due_audits(
        args=args,
        repo_root=repo_root,
        checkpoint_dir=checkpoint_dir,
        launched_rounds=launched_rounds,
        active_audits=active_audits,
        audit_records=audit_records,
    )
    audit_deadline = time.perf_counter() + max(0, args.npu_final_wait_seconds)
    while active_audits and time.perf_counter() < audit_deadline:
        harvest_finished_audits(repo_root=repo_root, active_audits=active_audits, audit_records=audit_records)
        time.sleep(args.poll_seconds)
    for round_id, process in list(active_audits.items()):
        process.terminate()
        warnings.append(f"NPU audit round {round_id} terminated after final wait budget")
    harvest_finished_audits(repo_root=repo_root, active_audits=active_audits, audit_records=audit_records)

    gpu_report: dict[str, Any] = {}
    if gpu_output.exists():
        try:
            gpu_report = read_json(gpu_output)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"unable to parse GPU report: {type(exc).__name__}: {exc}")
    else:
        errors.append(f"GPU output missing: {repo_rel(gpu_output, repo_root)}")

    for audit in audit_records:
        if audit.get("npu_tool_requests") and not audit.get("npu_runtime_tool_broker"):
            audit["npu_runtime_tool_broker"] = run_npu_runtime_tool_broker_for_audit(
                args=args,
                repo_root=repo_root,
                audit_record=audit,
            )
            broker = audit["npu_runtime_tool_broker"]
            if broker.get("error"):
                warnings.append(f"NPU runtime tool broker round {audit.get('round')}: {broker.get('error')}")
            if broker.get("returncode") not in (None, 0):
                warnings.append(f"NPU runtime tool broker round {audit.get('round')}: returncode={broker.get('returncode')}")

    gpu_runtime_tool_brokers = execute_gpu_runtime_tool_requests_from_report(
        args=args,
        repo_root=repo_root,
        gpu_report=gpu_report,
    ) if getattr(args, "enable_runtime_tool_broker", False) else []
    for broker in gpu_runtime_tool_brokers:
        if broker.get("error"):
            warnings.append(f"GPU runtime tool broker round {broker.get('round')}: {broker.get('error')}")
        if broker.get("returncode") not in (None, 0):
            warnings.append(f"GPU runtime tool broker round {broker.get('round')}: returncode={broker.get('returncode')}")

    npu_success_count = sum(1 for item in audit_records if item.get("provider_execution_succeeded") is True or item.get("classification") == "usable_audit_text")
    npu_tool_context_seen_count = sum(1 for item in audit_records if item.get("runtime_tool_context_seen") is True)
    npu_tool_request_count = sum(int(item.get("npu_tool_request_count") or 0) for item in audit_records)
    npu_deterministic_tool_fallback_count = sum(int(item.get("npu_deterministic_tool_fallback_count") or 0) for item in audit_records)
    npu_runtime_brokers = [item.get("npu_runtime_tool_broker", {}) for item in audit_records if item.get("npu_runtime_tool_broker")]
    npu_runtime_tool_request_count = sum(int(item.get("requested_tool_count") or 0) for item in npu_runtime_brokers)
    npu_runtime_tool_execution_count = sum(int(item.get("tool_execution_count") or 0) for item in npu_runtime_brokers)
    npu_runtime_tool_failed_count = sum(int(item.get("failed_tool_count") or 0) for item in npu_runtime_brokers)
    npu_runtime_tool_blocked_count = sum(int(item.get("blocked_tool_count") or 0) for item in npu_runtime_brokers)
    npu_runtime_tool_result_count = sum(len(item.get("tool_results", [])) for item in npu_runtime_brokers)
    gpu_orchestrated_runtime_tool_request_count = sum(int(item.get("requested_tool_count") or 0) for item in gpu_runtime_tool_brokers)
    gpu_orchestrated_runtime_tool_execution_count = sum(int(item.get("tool_execution_count") or 0) for item in gpu_runtime_tool_brokers)
    gpu_orchestrated_runtime_tool_failed_count = sum(int(item.get("failed_tool_count") or 0) for item in gpu_runtime_tool_brokers)
    gpu_orchestrated_runtime_tool_blocked_count = sum(int(item.get("blocked_tool_count") or 0) for item in gpu_runtime_tool_brokers)
    gpu_orchestrated_runtime_tool_result_count = sum(len(item.get("tool_results", [])) for item in gpu_runtime_tool_brokers)
    orchestrator_runtime_tool_bootstrap_request_count = int(orchestrator_runtime_tool_bootstrap.get("requested_tool_count") or 0)
    orchestrator_runtime_tool_bootstrap_execution_count = int(orchestrator_runtime_tool_bootstrap.get("tool_execution_count") or 0)
    orchestrator_runtime_tool_bootstrap_failed_count = int(orchestrator_runtime_tool_bootstrap.get("failed_tool_count") or 0)
    orchestrator_runtime_tool_bootstrap_blocked_count = int(orchestrator_runtime_tool_bootstrap.get("blocked_tool_count") or 0)
    orchestrator_runtime_tool_bootstrap_result_count = len(orchestrator_runtime_tool_bootstrap.get("tool_results", []))
    gpu_recommendation_count = gpu_report.get("recommendation_count")
    gpu_empty_recommendations_reason = gpu_report.get("empty_recommendations_reason", "")
    gpu_evidence_ready_count = gpu_report.get("evidence_ready_for_manual_patch_count", 0)
    gpu_recommended_next_layer = gpu_report.get("decision", {}).get("recommended_next_layer") or gpu_report.get("recommended_next_layer")
    gpu_runtime_tool_broker_enabled = bool(gpu_report.get("runtime_tool_broker_enabled"))
    gpu_runtime_tool_request_count = int(gpu_report.get("runtime_tool_request_count") or 0)
    gpu_runtime_tool_execution_count = int(gpu_report.get("runtime_tool_execution_count") or 0)
    gpu_runtime_tool_failed_count = int(gpu_report.get("runtime_tool_failed_count") or 0)
    gpu_runtime_tool_blocked_count = int(gpu_report.get("runtime_tool_blocked_count") or 0)
    gpu_runtime_tool_result_count = int(gpu_report.get("runtime_tool_result_count") or 0)

    gpu_runtime_tool_bootstrap_executed = bool(gpu_report.get("runtime_tool_bootstrap_executed"))
    gpu_runtime_tool_bootstrap_passed = gpu_report.get("runtime_tool_bootstrap_passed")
    gpu_runtime_tool_bootstrap_request_count = int(gpu_report.get("runtime_tool_bootstrap_request_count") or 0)
    gpu_runtime_tool_bootstrap_execution_count = int(gpu_report.get("runtime_tool_bootstrap_execution_count") or 0)
    gpu_runtime_tool_bootstrap_failed_count = int(gpu_report.get("runtime_tool_bootstrap_failed_count") or 0)
    gpu_runtime_tool_bootstrap_blocked_count = int(gpu_report.get("runtime_tool_bootstrap_blocked_count") or 0)

    orchestrator_runtime_tool_bootstrap_executed = bool(orchestrator_runtime_tool_bootstrap.get("executed"))
    orchestrator_runtime_tool_bootstrap_enabled = bool(orchestrator_runtime_tool_bootstrap.get("enabled"))

    runtime_tool_bootstrap_executed = bool(
        gpu_runtime_tool_bootstrap_executed or orchestrator_runtime_tool_bootstrap_executed
    )
    runtime_tool_bootstrap_passed = (
        orchestrator_runtime_tool_bootstrap.get("passed")
        if orchestrator_runtime_tool_bootstrap_executed
        else gpu_runtime_tool_bootstrap_passed
    )
    runtime_tool_bootstrap_request_count = (
        gpu_runtime_tool_bootstrap_request_count + orchestrator_runtime_tool_bootstrap_request_count
    )
    runtime_tool_bootstrap_execution_count = (
        gpu_runtime_tool_bootstrap_execution_count + orchestrator_runtime_tool_bootstrap_execution_count
    )
    runtime_tool_bootstrap_failed_count = (
        gpu_runtime_tool_bootstrap_failed_count + orchestrator_runtime_tool_bootstrap_failed_count
    )
    runtime_tool_bootstrap_blocked_count = (
        gpu_runtime_tool_bootstrap_blocked_count + orchestrator_runtime_tool_bootstrap_blocked_count
    )

    runtime_tool_provider_request_count = (
        gpu_orchestrated_runtime_tool_request_count + npu_runtime_tool_request_count
    )
    runtime_tool_provider_request_execution_count = (
        gpu_orchestrated_runtime_tool_execution_count + npu_runtime_tool_execution_count
    )
    runtime_tool_provider_request_failed_count = (
        gpu_orchestrated_runtime_tool_failed_count + npu_runtime_tool_failed_count
    )
    runtime_tool_provider_request_blocked_count = (
        gpu_orchestrated_runtime_tool_blocked_count + npu_runtime_tool_blocked_count
    )
    runtime_tool_provider_request_result_count = (
        gpu_orchestrated_runtime_tool_result_count + npu_runtime_tool_result_count
    )
    deterministic_runtime_tool_fallback_request_count = int(gpu_report.get("deterministic_runtime_tool_fallback_request_count") or 0)
    deterministic_runtime_tool_fallback_execution_count = int(gpu_report.get("deterministic_runtime_tool_fallback_execution_count") or 0)
    deterministic_runtime_tool_fallback_failed_count = int(gpu_report.get("deterministic_runtime_tool_fallback_failed_count") or 0)
    deterministic_runtime_tool_fallback_blocked_count = int(gpu_report.get("deterministic_runtime_tool_fallback_blocked_count") or 0)

    runtime_tool_broker_enabled = bool(
        getattr(args, "enable_runtime_tool_broker", False)
        or gpu_runtime_tool_broker_enabled
        or orchestrator_runtime_tool_bootstrap_enabled
        or orchestrator_runtime_tool_bootstrap_executed
        or gpu_runtime_tool_brokers
        or npu_runtime_brokers
    )
    runtime_tool_request_count = (
        gpu_runtime_tool_request_count
        + runtime_tool_bootstrap_request_count
        + runtime_tool_provider_request_count
    )
    runtime_tool_execution_count = (
        gpu_runtime_tool_execution_count
        + runtime_tool_bootstrap_execution_count
        + runtime_tool_provider_request_execution_count
    )
    runtime_tool_failed_count = (
        gpu_runtime_tool_failed_count
        + runtime_tool_bootstrap_failed_count
        + runtime_tool_provider_request_failed_count
    )
    runtime_tool_blocked_count = (
        gpu_runtime_tool_blocked_count
        + runtime_tool_bootstrap_blocked_count
        + runtime_tool_provider_request_blocked_count
    )
    runtime_tool_result_count = (
        gpu_runtime_tool_result_count
        + orchestrator_runtime_tool_bootstrap_result_count
        + runtime_tool_provider_request_result_count
    )
    gpu_provider_execution_performed = bool(
        gpu_report.get("provider_execution_performed")
        and gpu_process.returncode == 0
        and safe_int(gpu_report.get("round_count")) > 0
        and str(gpu_report.get("classification") or "") != "required_provider_artifact_missing"
    )
    npu_provider_execution_performed = bool(npu_success_count > 0)
    provider_execution_observed = bool(gpu_provider_execution_performed or npu_provider_execution_performed)
    provider_degraded_reasons: list[str] = []
    if not gpu_provider_execution_performed:
        provider_degraded_reasons.append(
            "gpu_provider_not_confirmed:"
            f"returncode={gpu_process.returncode};"
            f"round_count={safe_int(gpu_report.get('round_count'))};"
            f"performed={gpu_report.get('provider_execution_performed')};"
            f"classification={gpu_report.get('classification')}"
        )
    if getattr(args, "run_npu_auditor_provider", False) and not npu_provider_execution_performed:
        provider_degraded_reasons.append(
            "npu_auditor_not_confirmed:"
            f"audit_count={len(audit_records)};success_count={npu_success_count};"
            f"lane_mode={npu_lane_diagnostics(args, audit_records).get('mode')}"
        )
    report = {
        "schema_version": 1,
        "kind": "agent_gpu_npu_parallel_orchestrator",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors and gpu_process.returncode == 0,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": provider_execution_observed,
        "gpu_provider_execution_performed": gpu_provider_execution_performed,
        "npu_provider_execution_performed": npu_provider_execution_performed,
        "provider_degraded_reasons": provider_degraded_reasons,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "apply_mode": "report_only_parallel_gpu_planner_npu_auditor",
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "gpu_returncode": gpu_process.returncode,
        "gpu_stdout_tail": gpu_stdout,
        "gpu_stderr_tail": gpu_stderr,
        "gpu_output": repo_rel(gpu_output, repo_root),
        "gpu_markdown": repo_rel(gpu_markdown, repo_root),
        "gpu_recommendation_count": gpu_recommendation_count,
        "gpu_empty_recommendations_reason": gpu_empty_recommendations_reason,
        "gpu_evidence_ready_for_manual_patch_count": gpu_evidence_ready_count,
        "gpu_recommended_next_layer": gpu_recommended_next_layer,
        "runtime_tool_broker_enabled": runtime_tool_broker_enabled,
        "runtime_tool_bootstrap_executed": runtime_tool_bootstrap_executed,
        "runtime_tool_bootstrap_passed": runtime_tool_bootstrap_passed,
        "runtime_tool_bootstrap_request_count": runtime_tool_bootstrap_request_count,
        "runtime_tool_bootstrap_execution_count": runtime_tool_bootstrap_execution_count,
        "runtime_tool_bootstrap_failed_count": runtime_tool_bootstrap_failed_count,
        "runtime_tool_bootstrap_blocked_count": runtime_tool_bootstrap_blocked_count,
        "runtime_tool_request_count": runtime_tool_request_count,
        "runtime_tool_execution_count": runtime_tool_execution_count,
        "runtime_tool_failed_count": runtime_tool_failed_count,
        "runtime_tool_blocked_count": runtime_tool_blocked_count,
        "runtime_tool_result_count": runtime_tool_result_count,
        "gpu_runtime_tool_broker_enabled": gpu_runtime_tool_broker_enabled,
        "gpu_runtime_tool_request_count": gpu_runtime_tool_request_count,
        "gpu_runtime_tool_execution_count": gpu_runtime_tool_execution_count,
        "gpu_runtime_tool_failed_count": gpu_runtime_tool_failed_count,
        "gpu_runtime_tool_blocked_count": gpu_runtime_tool_blocked_count,
        "gpu_runtime_tool_result_count": gpu_runtime_tool_result_count,
        "runtime_tool_provider_request_count": runtime_tool_provider_request_count,
        "runtime_tool_provider_request_execution_count": runtime_tool_provider_request_execution_count,
        "runtime_tool_provider_request_failed_count": runtime_tool_provider_request_failed_count,
        "runtime_tool_provider_request_blocked_count": runtime_tool_provider_request_blocked_count,
        "runtime_tool_provider_request_result_count": runtime_tool_provider_request_result_count,
        "deterministic_runtime_tool_fallback_request_count": deterministic_runtime_tool_fallback_request_count,
        "deterministic_runtime_tool_fallback_execution_count": deterministic_runtime_tool_fallback_execution_count,
        "deterministic_runtime_tool_fallback_failed_count": deterministic_runtime_tool_fallback_failed_count,
        "deterministic_runtime_tool_fallback_blocked_count": deterministic_runtime_tool_fallback_blocked_count,
        "orchestrator_runtime_tool_bootstrap": orchestrator_runtime_tool_bootstrap,
        "orchestrator_runtime_tool_bootstrap_executed": bool(orchestrator_runtime_tool_bootstrap.get("executed")),
        "orchestrator_runtime_tool_bootstrap_passed": orchestrator_runtime_tool_bootstrap.get("passed"),
        "orchestrator_runtime_tool_bootstrap_request_count": orchestrator_runtime_tool_bootstrap_request_count,
        "orchestrator_runtime_tool_bootstrap_execution_count": orchestrator_runtime_tool_bootstrap_execution_count,
        "orchestrator_runtime_tool_bootstrap_failed_count": orchestrator_runtime_tool_bootstrap_failed_count,
        "orchestrator_runtime_tool_bootstrap_blocked_count": orchestrator_runtime_tool_bootstrap_blocked_count,
        "orchestrator_runtime_tool_bootstrap_result_count": orchestrator_runtime_tool_bootstrap_result_count,
        "gpu_orchestrated_runtime_tool_brokers": gpu_runtime_tool_brokers,
        "gpu_orchestrated_runtime_tool_request_count": gpu_orchestrated_runtime_tool_request_count,
        "gpu_orchestrated_runtime_tool_execution_count": gpu_orchestrated_runtime_tool_execution_count,
        "gpu_orchestrated_runtime_tool_failed_count": gpu_orchestrated_runtime_tool_failed_count,
        "gpu_orchestrated_runtime_tool_blocked_count": gpu_orchestrated_runtime_tool_blocked_count,
        "gpu_orchestrated_runtime_tool_result_count": gpu_orchestrated_runtime_tool_result_count,
        "gpu_runner_direct_runtime_tool_broker": bool(getattr(args, "gpu_runner_direct_runtime_tool_broker", False)),
        "gpu_summary": {
            "passed": gpu_report.get("passed"),
            "round_count": gpu_report.get("round_count"),
            "recommendation_count": gpu_recommendation_count,
            "raw_recommendation_candidate_count": gpu_report.get("raw_recommendation_candidate_count"),
            "filtered_recommendation_count": gpu_report.get("filtered_recommendation_count"),
            "json_parse_error_count": gpu_report.get("json_parse_error_count"),
            "repair_attempt_count": gpu_report.get("repair_attempt_count"),
            "empty_recommendations_reason": gpu_empty_recommendations_reason,
            "evidence_ready_for_manual_patch_count": gpu_evidence_ready_count,
            "recommended_next_layer": gpu_recommended_next_layer,
            "runtime_tool_broker_enabled": runtime_tool_broker_enabled,
            "runtime_tool_request_count": runtime_tool_request_count,
            "runtime_tool_execution_count": runtime_tool_execution_count,
            "runtime_tool_failed_count": runtime_tool_failed_count,
            "runtime_tool_blocked_count": runtime_tool_blocked_count,
            "runtime_tool_result_count": runtime_tool_result_count,
            "decision": gpu_report.get("decision", {}),
        },
        "checkpoint_dir": repo_rel(checkpoint_dir, repo_root),
        "npu_audit_count": len(audit_records),
        "npu_audit_success_count": npu_success_count,
        "npu_tool_context_seen_count": npu_tool_context_seen_count,
        "npu_tool_request_count": npu_tool_request_count,
        "npu_deterministic_tool_fallback_count": npu_deterministic_tool_fallback_count,
        "npu_runtime_tool_request_count": npu_runtime_tool_request_count,
        "npu_runtime_tool_execution_count": npu_runtime_tool_execution_count,
        "npu_runtime_tool_failed_count": npu_runtime_tool_failed_count,
        "npu_runtime_tool_blocked_count": npu_runtime_tool_blocked_count,
        "npu_runtime_tool_result_count": npu_runtime_tool_result_count,
        "npu_audits": audit_records,
        "decision": {
            "gpu_review_blocked_by_npu": False,
            "npu_auditor_mode": "parallel_best_effort",
            "npu_audit_success_count": npu_success_count,
            "npu_tool_context_seen_count": npu_tool_context_seen_count,
            "npu_tool_request_count": npu_tool_request_count,
            "npu_deterministic_tool_fallback_count": npu_deterministic_tool_fallback_count,
            "npu_runtime_tool_request_count": npu_runtime_tool_request_count,
            "npu_runtime_tool_execution_count": npu_runtime_tool_execution_count,
            "npu_runtime_tool_failed_count": npu_runtime_tool_failed_count,
            "npu_runtime_tool_blocked_count": npu_runtime_tool_blocked_count,
            "npu_runtime_tool_result_count": npu_runtime_tool_result_count,
            "ready_for_patch_plan": bool(gpu_report.get("decision", {}).get("ready_for_patch_plan")),
            "fallback_patch_plan_recommended": bool(gpu_report.get("decision", {}).get("fallback_patch_plan_recommended")),
            "recommended_next_layer": gpu_recommended_next_layer,
            "gpu_empty_recommendations_reason": gpu_empty_recommendations_reason,
            "runtime_tool_broker_enabled": runtime_tool_broker_enabled,
            "runtime_tool_bootstrap_executed": runtime_tool_bootstrap_executed,
            "runtime_tool_bootstrap_execution_count": runtime_tool_bootstrap_execution_count,
            "runtime_tool_provider_request_count": runtime_tool_provider_request_count,
            "runtime_tool_provider_request_execution_count": runtime_tool_provider_request_execution_count,
            "deterministic_runtime_tool_fallback_execution_count": deterministic_runtime_tool_fallback_execution_count,
            "runtime_tool_execution_count": runtime_tool_execution_count,
            "runtime_tool_result_count": runtime_tool_result_count,
            "manual_review_required": True,
            "provider_execution_performed": provider_execution_observed,
            "gpu_provider_execution_performed": gpu_provider_execution_performed,
            "npu_provider_execution_performed": npu_provider_execution_performed,
            "provider_degraded_reasons": provider_degraded_reasons,
        },
        "guardrails": {
            "gpu_continues_without_waiting_for_npu": True,
            "npu_auditor_non_blocking": True,
            "npu_primary_advisory": False,
            "patch_application_performed": False,
            "real_github_pr_created": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
            "runtime_tool_broker_report_only": True,
            "provider_execution_performed": provider_execution_observed,
            "gpu_provider_execution_performed": gpu_provider_execution_performed,
            "npu_provider_execution_performed": npu_provider_execution_performed,
            "orchestrator_controls_gpu_runtime_tools": not bool(getattr(args, "gpu_runner_direct_runtime_tool_broker", False)),
            "gpu_runner_direct_runtime_tool_broker": bool(getattr(args, "gpu_runner_direct_runtime_tool_broker", False)),
            "npu_runtime_tools_execute_via_broker": True,
        },
    }
    apply_orchestrator_direct_gpu_and_lane_diagnostics(
        report,
        args=args,
        gpu_report=gpu_report,
        audit_records=audit_records,
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--budget-minutes", type=int, default=30)
    parser.add_argument("--max-rounds", type=int, default=24)
    parser.add_argument("--files-per-round", type=int, default=10)
    parser.add_argument("--max-context-files", type=int, default=300)
    parser.add_argument("--max-chars-per-file", type=int, default=8000)
    parser.add_argument("--max-new-tokens", type=int, default=4800)
    parser.add_argument("--keep-alive", default="35m")
    parser.add_argument("--ollama-model", default=None)
    parser.add_argument("--ollama-base-url", default=None)
    parser.add_argument("--evidence", default="output/ai_pipeline/agent_review_evidence_sufficiency.json")
    parser.add_argument("--refined-review", default="output/ai_pipeline/local_ai_core_tool_activation_megalithic_refined_review_v3.json")
    parser.add_argument("--report-file", action="append", default=[])
    parser.add_argument("--context-root", action="append", default=[])
    parser.add_argument("--enable-runtime-tool-broker", action="store_true")
    parser.add_argument("--gpu-runner-direct-runtime-tool-broker", action="store_true", help="Compatibility mode: let the GPU supervised runner execute runtime tools directly instead of routing GPU requests through the orchestrator.")
    parser.add_argument("--runtime-tool-output-dir", default="output/ai_runtime_tools/gpu_planner_runtime_tools")
    parser.add_argument("--runtime-tool-timeout-seconds", type=int, default=300)
    parser.add_argument("--runtime-tool-max-requests-per-round", type=int, default=8)
    parser.add_argument("--disable-runtime-tool-bootstrap", action="store_true")
    parser.add_argument("--run-npu-auditor-provider", action="store_true")
    parser.add_argument("--npu-python", default=None)
    parser.add_argument("--npu-auditor-every-rounds", type=int, default=4)
    parser.add_argument("--max-concurrent-npu-audits", type=int, default=1)
    parser.add_argument("--npu-auditor-timeout-seconds", type=int, default=600)
    parser.add_argument("--npu-max-context-chars", type=int, default=12000)
    parser.add_argument("--npu-max-prompt-chars", type=int, default=8000)
    parser.add_argument("--npu-max-new-tokens", type=int, default=512)
    parser.add_argument("--npu-final-wait-seconds", type=int, default=120)
    parser.add_argument("--npu-slow-audit-threshold-seconds", type=float, default=60.0)
    parser.add_argument("--npu-slow-auditor-every-rounds", type=int, default=4)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--checkpoint-dir", default=DEFAULT_CHECKPOINT_DIR)
    parser.add_argument("--gpu-output", default=DEFAULT_GPU_OUTPUT)
    parser.add_argument("--gpu-markdown-output", default=DEFAULT_GPU_MARKDOWN)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = run_orchestrator(args)
    output = resolve_path(repo_root, args.output)
    markdown = resolve_path(repo_root, args.markdown_output)
    write_json(output, report)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(build_markdown(report), encoding="utf-8")
    print(json.dumps({
        "passed": report["passed"],
        "output": str(output),
        "markdown": str(markdown),
        "provider_execution_performed": report["provider_execution_performed"],
        "patch_application_performed": report["patch_application_performed"],
        "elapsed_seconds": report["elapsed_seconds"],
        "gpu_returncode": report["gpu_returncode"],
        "gpu_round_count": report["gpu_summary"].get("round_count"),
        "gpu_recommendation_count": report["gpu_summary"].get("recommendation_count"),
        "gpu_empty_recommendations_reason": report.get("gpu_empty_recommendations_reason"),
        "gpu_evidence_ready_for_manual_patch_count": report.get("gpu_evidence_ready_for_manual_patch_count"),
        "gpu_recommended_next_layer": report.get("gpu_recommended_next_layer"),
        "runtime_tool_broker_enabled": report.get("runtime_tool_broker_enabled"),
        "runtime_tool_bootstrap_executed": report.get("runtime_tool_bootstrap_executed"),
        "runtime_tool_bootstrap_passed": report.get("runtime_tool_bootstrap_passed"),
        "runtime_tool_bootstrap_request_count": report.get("runtime_tool_bootstrap_request_count"),
        "runtime_tool_bootstrap_execution_count": report.get("runtime_tool_bootstrap_execution_count"),
        "runtime_tool_bootstrap_failed_count": report.get("runtime_tool_bootstrap_failed_count"),
        "runtime_tool_bootstrap_blocked_count": report.get("runtime_tool_bootstrap_blocked_count"),
        "runtime_tool_request_count": report.get("runtime_tool_request_count"),
        "runtime_tool_execution_count": report.get("runtime_tool_execution_count"),
        "runtime_tool_failed_count": report.get("runtime_tool_failed_count"),
        "runtime_tool_blocked_count": report.get("runtime_tool_blocked_count"),
        "runtime_tool_result_count": report.get("runtime_tool_result_count"),
        "runtime_tool_provider_request_count": report.get("runtime_tool_provider_request_count"),
        "runtime_tool_provider_request_execution_count": report.get("runtime_tool_provider_request_execution_count"),
        "deterministic_runtime_tool_fallback_execution_count": report.get("deterministic_runtime_tool_fallback_execution_count"),
        "orchestrator_runtime_tool_bootstrap_execution_count": report.get("orchestrator_runtime_tool_bootstrap_execution_count"),
        "gpu_orchestrated_runtime_tool_request_count": report.get("gpu_orchestrated_runtime_tool_request_count"),
        "gpu_orchestrated_runtime_tool_execution_count": report.get("gpu_orchestrated_runtime_tool_execution_count"),
        "gpu_orchestrated_runtime_tool_failed_count": report.get("gpu_orchestrated_runtime_tool_failed_count"),
        "gpu_orchestrated_runtime_tool_blocked_count": report.get("gpu_orchestrated_runtime_tool_blocked_count"),
        "npu_audit_count": report["npu_audit_count"],
        "npu_audit_success_count": report["npu_audit_success_count"],
        "npu_tool_context_seen_count": report.get("npu_tool_context_seen_count"),
        "npu_tool_request_count": report.get("npu_tool_request_count"),
        "npu_deterministic_tool_fallback_count": report.get("npu_deterministic_tool_fallback_count"),
        "npu_runtime_tool_request_count": report.get("npu_runtime_tool_request_count"),
        "npu_runtime_tool_execution_count": report.get("npu_runtime_tool_execution_count"),
        "npu_runtime_tool_failed_count": report.get("npu_runtime_tool_failed_count"),
        "npu_runtime_tool_blocked_count": report.get("npu_runtime_tool_blocked_count"),
        "npu_runtime_tool_result_count": report.get("npu_runtime_tool_result_count"),
        "gpu_review_blocked_by_npu": report["decision"]["gpu_review_blocked_by_npu"],
    }, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
