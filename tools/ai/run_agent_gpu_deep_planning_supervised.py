#!/usr/bin/env python3
"""Run GPU/Ollama deep planning with non-blocking intermediate NPU audits.

This supervised runner is the long-running IA-Carmine planning mode:

- GPU/Ollama performs multi-round reasoning over repository evidence;
- each round writes an intermediate checkpoint JSON/Markdown artifact;
- optional NPU auditor inspects checkpoints as a non-blocking guardrail;
- NPU failures, unusable text or missing OpenVINO are warnings only;
- repeated deterministic NPU dependency failures are circuit-broken;
- no patch is applied and no GitHub PR is created.
"""
from __future__ import annotations

from pathlib import Path

try:
    from Tools.ai.schema_repair_context import build_schema_repair_context_stack
except ImportError:
    import sys as _schema_repair_sys

    _schema_repair_repo_root = Path(__file__).resolve().parents[2]
    if str(_schema_repair_repo_root) not in _schema_repair_sys.path:
        _schema_repair_sys.path.insert(0, str(_schema_repair_repo_root))
    from Tools.ai.schema_repair_context import build_schema_repair_context_stack  # type: ignore

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.ai.run_agent_gpu_deep_planning_review import (
        DEFAULT_EVIDENCE,
        DEFAULT_REFINED,
        aggregate_recommendation_diagnostics,
        build_markdown,
        build_prompt,
        collect_repo_context,
        evidence_ready_for_manual_patch_count,
        extract_evidence_files,
        extract_valid_tool_requests,
        merge_recommendations,
        parse_model_json_with_diagnostics,
        read_json,
        recommendation_diagnostics_for_round,
        resolve_path,
        repo_rel,
        split_batches,
    )
    from Tools.ai.runtime_tool_guidance import deterministic_fallback_tool_requests
    from Tools.npu.ollama_runtime import DEFAULT_BASE_URL, OllamaModelManager, normalize_base_url
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.run_agent_gpu_deep_planning_review import (  # type: ignore
        DEFAULT_EVIDENCE,
        DEFAULT_REFINED,
        aggregate_recommendation_diagnostics,
        build_markdown,
        build_prompt,
        collect_repo_context,
        evidence_ready_for_manual_patch_count,
        extract_evidence_files,
        extract_valid_tool_requests,
        merge_recommendations,
        parse_model_json_with_diagnostics,
        read_json,
        recommendation_diagnostics_for_round,
        resolve_path,
        repo_rel,
        split_batches,
    )
    from Tools.ai.runtime_tool_guidance import deterministic_fallback_tool_requests  # type: ignore
    from Tools.npu.ollama_runtime import DEFAULT_BASE_URL, OllamaModelManager, normalize_base_url  # type: ignore


try:
    from Tools.ai.schema_repair_context import (
        build_schema_repair_retry_prompt,
        should_attempt_schema_repair_retry,
        summarize_schema_repair_retry,
    )
except ImportError:
    from schema_repair_context import (  # type: ignore
        build_schema_repair_retry_prompt,
        should_attempt_schema_repair_retry,
        summarize_schema_repair_retry,
    )

DEFAULT_OUTPUT = "output/ai_pipeline/agent_gpu_deep_planning_supervised.json"
DEFAULT_MARKDOWN = "output/ai_pipeline/agent_gpu_deep_planning_supervised.md"
DEFAULT_CHECKPOINT_DIR = "output/ai_pipeline/gpu_deep_planning_checkpoints"
TERMINAL_NPU_AUDIT_CLASSIFICATIONS = {"dependency_missing_openvino_genai"}

DEFAULT_RUNTIME_TOOL_BOOTSTRAP_REQUESTS: list[dict[str, Any]] = [
    {"id": "bootstrap_tool_inventory", "tool": "build_agent_agnostic_tool_inventory", "reason": "Bootstrap available runtime tools, capabilities and guardrails before GPU planning.", "args": {}},
    {"id": "bootstrap_memory_inventory", "tool": "build_agent_memory_inventory", "reason": "Bootstrap durable project memory inventory before GPU planning.", "args": {}},
    {"id": "bootstrap_persistent_memory_status", "tool": "runtime_sqlite_memory", "reason": "Bootstrap persistent memory status in read-only mode before GPU planning.", "args": {"action": "status", "scope": "persistent"}},
    {"id": "bootstrap_operational_memory_status", "tool": "runtime_sqlite_memory", "reason": "Bootstrap operational scratch memory status before GPU planning.", "args": {"action": "status", "scope": "operational"}},
    {"id": "bootstrap_python_line_count", "tool": "build_python_line_count_csv", "reason": "Bootstrap full Python inventory before refactor planning.", "args": {}},
    {"id": "bootstrap_python_syntax", "tool": "check_python_syntax", "reason": "Bootstrap Python syntax baseline before code planning.", "args": {}},
    {"id": "bootstrap_gpu_contract_smoke", "tool": "run_gpu_planner_json_contract_smoke", "reason": "Bootstrap GPU JSON contract validation, including runtime tool request support.", "args": {}},
]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_command(command: list[str], repo_root: Path, timeout_seconds: int) -> tuple[int, str, str, str | None]:
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
        return completed.returncode, completed.stdout[-12000:], completed.stderr[-12000:], None
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or "", f"TimeoutExpired: {timeout_seconds}s"
    except Exception as exc:  # noqa: BLE001 - non-blocking auditor runner.
        return 1, "", "", f"{type(exc).__name__}: {exc}"


def compact_tool_results_for_context(tool_results: list[dict[str, Any]], *, max_items: int = 8) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for item in tool_results[:max_items]:
        compact.append(
            {
                "id": item.get("id"),
                "tool": item.get("tool"),
                "executed": item.get("executed"),
                "blocked": item.get("blocked"),
                "returncode": item.get("returncode"),
                "outputs": item.get("outputs", {}),
                "summary": item.get("summary", {}),
                "guardrails": item.get("guardrails", {}),
                "errors": item.get("errors", []),
            }
        )
    return compact


def run_runtime_tool_broker_for_round(
    *,
    repo_root: Path,
    args: argparse.Namespace,
    round_index: int,
    tool_requests: list[dict[str, Any]],
) -> dict[str, Any]:
    """Execute valid planner tool requests through the report-only broker."""

    if not args.enable_runtime_tool_broker:
        return {
            "enabled": False,
            "requested_tool_count": len(tool_requests),
            "executed": False,
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
            "requested_tool_count": 0,
            "executed": False,
            "tool_results": [],
            "guardrails": {
                "patch_application_performed": False,
                "persistent_memory_write_performed": False,
            },
        }

    request_sources = {str(item.get("source") or "provider") for item in tool_requests if isinstance(item, dict)}
    request_source = "deterministic_fallback" if request_sources == {"deterministic_fallback"} else "provider"

    output_root = resolve_path(repo_root, args.runtime_tool_output_dir)
    round_dir = output_root / f"round_{round_index:03d}"
    round_dir.mkdir(parents=True, exist_ok=True)
    request_file = round_dir / f"round_{round_index:03d}_tool_requests.json"
    broker_output = round_dir / f"round_{round_index:03d}_runtime_tool_broker.json"
    broker_markdown = round_dir / f"round_{round_index:03d}_runtime_tool_broker.md"
    request_packet = {
        "schema_version": 1,
        "kind": "gpu_planner_runtime_tool_requests",
        "repo_root": str(repo_root),
        "round": round_index,
        "tool_requests": tool_requests,
        "guardrails": {
            "free_shell_allowed": False,
            "broker_allowlist_required": True,
            "patch_application_allowed": False,
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
    returncode, stdout, stderr, error = run_command(command, repo_root, args.runtime_tool_timeout_seconds + 30)
    broker_report: dict[str, Any] = {}
    broker_output_exists = broker_output.exists()
    if broker_output_exists:
        try:
            broker_report = read_json(broker_output)
        except Exception as exc:  # noqa: BLE001
            error = f"{error or ''} {type(exc).__name__}: {exc}".strip()
    elif not error:
        error = "runtime_tool_broker_output_missing"

    return {
        "enabled": True,
        "source": request_source,
        "deterministic_fallback": request_source == "deterministic_fallback",
        "executed": True,
        "requested_tool_count": len(tool_requests),
        "command": command,
        "returncode": returncode,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "error": error or "",
        "request_file": repo_rel(request_file, repo_root),
        "broker_output": repo_rel(broker_output, repo_root),
        "broker_markdown": repo_rel(broker_markdown, repo_root),
        "broker_output_exists": broker_output_exists,
        "passed": broker_report.get("passed"),
        "tool_request_count": broker_report.get("tool_request_count", len(tool_requests)),
        "tool_execution_count": broker_report.get("tool_execution_count", 0),
        "blocked_tool_count": broker_report.get("blocked_tool_count", 0),
        "failed_tool_count": broker_report.get("failed_tool_count", 0),
        "operational_sqlite_write_performed": broker_report.get("operational_sqlite_write_performed", False),
        "provider_execution_performed": broker_report.get("provider_execution_performed", False),
        "patch_application_performed": broker_report.get("patch_application_performed", False),
        "sqlite_write_performed": broker_report.get("sqlite_write_performed", False),
        "persistent_memory_write_performed": broker_report.get("persistent_memory_write_performed", False),
        "tool_results": compact_tool_results_for_context(broker_report.get("tool_results", [])),
        "guardrails": broker_report.get("guardrails", {}),
    }


def runtime_tool_context_report(round_index: int, broker_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": broker_result.get("broker_output"),
        "kind": "agent_runtime_tool_broker",
        "passed": broker_result.get("passed"),
        "summary": {
            "round": round_index,
            "bootstrap": bool(broker_result.get("bootstrap")),
            "tool_request_count": broker_result.get("tool_request_count"),
            "tool_execution_count": broker_result.get("tool_execution_count"),
            "blocked_tool_count": broker_result.get("blocked_tool_count"),
            "failed_tool_count": broker_result.get("failed_tool_count"),
            "operational_sqlite_write_performed": broker_result.get("operational_sqlite_write_performed"),
        },
        "decision": {
            "runtime_tool_results_available": bool(broker_result.get("tool_results")),
            "manual_review_required": True,
        },
        "tool_results": broker_result.get("tool_results", []),
    }


def runtime_tool_feedback_context_report(round_index: int, broker_result: dict[str, Any]) -> dict[str, Any]:
    """Build compact closed-loop context from a runtime broker result."""

    source = str(broker_result.get("source") or "provider")
    tool_results = broker_result.get("tool_results", [])
    if not isinstance(tool_results, list):
        tool_results = []
    return {
        "path": broker_result.get("broker_output"),
        "kind": "runtime_tool_feedback_context",
        "source": source,
        "round": round_index,
        "passed": broker_result.get("passed"),
        "summary": {
            "tool_request_count": broker_result.get("tool_request_count"),
            "requested_tool_count": broker_result.get("requested_tool_count"),
            "tool_execution_count": broker_result.get("tool_execution_count"),
            "blocked_tool_count": broker_result.get("blocked_tool_count"),
            "failed_tool_count": broker_result.get("failed_tool_count"),
            "deterministic_fallback": bool(broker_result.get("deterministic_fallback")),
            "provider_execution_performed": broker_result.get("provider_execution_performed"),
            "patch_application_performed": broker_result.get("patch_application_performed"),
            "sqlite_write_performed": broker_result.get("sqlite_write_performed"),
            "persistent_memory_write_performed": broker_result.get("persistent_memory_write_performed"),
            "operational_sqlite_write_performed": broker_result.get("operational_sqlite_write_performed"),
        },
        "decision": {
            "runtime_tool_results_available": bool(tool_results),
            "feed_into_next_provider_round": True,
            "manual_review_required": True,
            "do_not_treat_fallback_as_provider_emitted": source == "deterministic_fallback",
        },
        "tool_results": tool_results,
        "guardrails": {
            "report_only": True,
            "provider_must_not_execute_tools_directly": True,
            "patch_application_performed": False,
            "persistent_memory_write_performed": False,
        },
    }


def append_runtime_tool_feedback_context(
    context_reports: list[dict[str, Any]],
    round_index: int,
    broker_result: dict[str, Any],
    *,
    max_feedback_reports: int = 24,
) -> bool:
    """Append broker feedback context for subsequent provider rounds."""

    if not isinstance(broker_result, dict):
        return False
    if not broker_result.get("executed"):
        return False
    if broker_result.get("broker_output_exists") is False and not broker_result.get("tool_results"):
        return False

    feedback = runtime_tool_feedback_context_report(round_index, broker_result)
    existing = [
        item
        for item in context_reports
        if isinstance(item, dict) and item.get("kind") == "runtime_tool_feedback_context"
    ]

    if len(existing) >= max_feedback_reports:
        removed = 0
        trimmed: list[dict[str, Any]] = []
        for item in context_reports:
            if (
                isinstance(item, dict)
                and item.get("kind") == "runtime_tool_feedback_context"
                and removed < len(existing) - max_feedback_reports + 1
            ):
                removed += 1
                continue
            trimmed.append(item)
        context_reports[:] = trimmed

    context_reports.append(feedback)
    return True


def run_schema_repair_retry_for_round(
    *,
    manager: Any,
    model: str,
    args: argparse.Namespace,
    round_index: int,
    objective: str,
    raw_response: str,
    parsed_response: dict[str, Any],
    parse_diagnostics: dict[str, Any],
    context_reports: list[dict[str, Any]],
    rounds: list[dict[str, Any]],
    evidence_ready_for_manual_patch_count: int,
) -> dict[str, Any]:
    """Run one JSON-only schema repair pass for a bad provider response."""

    if not raw_response or not raw_response.strip():
        return {"attempted": False, "accepted": False, "reason": "empty_or_missing_raw_response"}

    valid_tool_count = int(parse_diagnostics.get("valid_tool_request_count") or 0)
    if not should_attempt_schema_repair_retry(
        parsed_response=parsed_response,
        parse_diagnostics=parse_diagnostics,
        evidence_ready_for_manual_patch_count=evidence_ready_for_manual_patch_count,
        valid_tool_request_count=valid_tool_count,
    ):
        return {"attempted": False, "accepted": False, "reason": "not_needed"}

    repair_prompt = build_schema_repair_retry_prompt(
        provider="gpu_ollama",
        round_index=round_index,
        objective=objective,
        raw_response=raw_response,
        parsed_response=parsed_response,
        parse_diagnostics=parse_diagnostics,
        context_reports=context_reports,
        rounds=rounds,
        evidence_ready_for_manual_patch_count=evidence_ready_for_manual_patch_count,
    )
    repair_max_tokens = min(max(int(getattr(args, "max_new_tokens", 1600) or 1600), 900), 2200)
    try:
        repair_raw_response, repair_model_used = manager.generate(
            model,
            repair_prompt,
            max_new_tokens=repair_max_tokens,
            temperature=0.03,
            num_thread=getattr(args, "ollama_num_thread", None),
            response_format="json",
        )
    except Exception as exc:  # noqa: BLE001 - provider repair is best-effort.
        return {
            "attempted": True,
            "accepted": False,
            "reason": "repair_provider_error",
            "error": f"{type(exc).__name__}: {exc}",
        }

    repair_parsed, repair_diagnostics = parse_model_json_with_diagnostics(
        repair_raw_response,
        evidence_ready_for_manual_patch_count,
    )
    repair_tool_requests, repair_tool_errors = extract_valid_tool_requests(
        repair_parsed,
        max_requests=getattr(args, "runtime_tool_max_requests_per_round", 8),
    )
    repair_diagnostics["valid_tool_request_count"] = len(repair_tool_requests)
    repair_diagnostics["invalid_tool_request_count"] = len(repair_tool_errors)
    repair_recommendation_diagnostics = recommendation_diagnostics_for_round(
        repair_parsed,
        repair_diagnostics,
        evidence_ready_for_manual_patch_count,
    )
    accepted = bool(
        repair_diagnostics.get("schema_ok")
        and (
            int(repair_recommendation_diagnostics.get("filtered_recommendation_count") or 0) > 0
            or len(repair_tool_requests) > 0
        )
    )
    return {
        "attempted": True,
        "accepted": accepted,
        "reason": "schema_repair_retry_accepted" if accepted else "schema_repair_retry_rejected",
        "model_used": repair_model_used,
        "raw_response_preview": repair_raw_response[:3000],
        "raw_response": repair_raw_response,
        "parsed_response": repair_parsed,
        "parse_diagnostics": repair_diagnostics,
        "tool_requests": repair_tool_requests,
        "tool_request_errors": repair_tool_errors,
        "recommendation_diagnostics": repair_recommendation_diagnostics,
    }


def run_runtime_tool_bootstrap(repo_root: Path, args: argparse.Namespace) -> dict[str, Any]:
    # Run deterministic broker bootstrap before the first GPU planner prompt.
    if not args.enable_runtime_tool_broker:
        return {
            "enabled": False,
            "executed": False,
            "bootstrap": True,
            "requested_tool_count": 0,
            "tool_results": [],
            "guardrails": {
                "bootstrap_requires_enable_runtime_tool_broker": True,
                "patch_application_performed": False,
                "persistent_memory_write_performed": False,
            },
        }
    if args.disable_runtime_tool_bootstrap:
        return {
            "enabled": True,
            "executed": False,
            "bootstrap": True,
            "disabled": True,
            "requested_tool_count": 0,
            "tool_results": [],
            "guardrails": {
                "bootstrap_disabled_by_flag": True,
                "patch_application_performed": False,
                "persistent_memory_write_performed": False,
            },
        }
    result = run_runtime_tool_broker_for_round(
        repo_root=repo_root,
        args=args,
        round_index=0,
        tool_requests=[dict(item) for item in DEFAULT_RUNTIME_TOOL_BOOTSTRAP_REQUESTS],
    )
    result["bootstrap"] = True
    result["bootstrap_tool_ids"] = [item["id"] for item in DEFAULT_RUNTIME_TOOL_BOOTSTRAP_REQUESTS]
    return result


def build_report(
    *,
    repo_root: Path,
    args: argparse.Namespace,
    evidence: dict[str, Any],
    refined: dict[str, Any],
    context_reports: list[dict[str, Any]],
    context_file_count: int,
    rounds: list[dict[str, Any]],
    npu_audits: list[dict[str, Any]],
    model_used: str,
    errors: list[str],
    warnings: list[str],
    started_at: float,
    npu_auditor_disabled_reason: str = "",
) -> dict[str, Any]:
    recommendations = merge_recommendations(rounds)
    diagnostics = aggregate_recommendation_diagnostics(rounds, evidence)
    ready = [rec for rec in recommendations if rec.get("status") == "ready_for_patch_plan"]
    needs_context = [rec for rec in recommendations if rec.get("status") == "needs_more_context"]
    unusable_npu = [audit for audit in npu_audits if audit.get("classification") not in {"usable_audit_text", "not_executed", "metadata_only"}]
    npu_success_count = sum(1 for audit in npu_audits if audit.get("provider_execution_succeeded") is True or audit.get("classification") == "usable_audit_text")
    npu_requested_count = sum(1 for audit in npu_audits if audit.get("provider_execution_requested") is True)
    fallback_recommended = (
        diagnostics["evidence_ready_for_manual_patch_count"] > 0
        and diagnostics["filtered_recommendation_count"] == 0
    )
    runtime_tool_bootstrap = getattr(args, "runtime_tool_bootstrap_result", {})
    runtime_brokers = [round_item.get("runtime_tool_broker", {}) for round_item in rounds if round_item.get("runtime_tool_broker")]
    provider_runtime_brokers = [item for item in runtime_brokers if item.get("source") != "deterministic_fallback"]
    deterministic_runtime_brokers = [item for item in runtime_brokers if item.get("source") == "deterministic_fallback"]
    runtime_tool_request_count = int(runtime_tool_bootstrap.get("requested_tool_count") or 0) + sum(int(item.get("requested_tool_count") or 0) for item in runtime_brokers)
    runtime_tool_execution_count = int(runtime_tool_bootstrap.get("tool_execution_count") or 0) + sum(int(item.get("tool_execution_count") or 0) for item in runtime_brokers)
    runtime_tool_failed_count = int(runtime_tool_bootstrap.get("failed_tool_count") or 0) + sum(int(item.get("failed_tool_count") or 0) for item in runtime_brokers)
    runtime_tool_blocked_count = int(runtime_tool_bootstrap.get("blocked_tool_count") or 0) + sum(int(item.get("blocked_tool_count") or 0) for item in runtime_brokers)
    runtime_tool_result_count = len(runtime_tool_bootstrap.get("tool_results", [])) + sum(len(item.get("tool_results", [])) for item in runtime_brokers)
    runtime_tool_provider_request_count = sum(int(item.get("requested_tool_count") or 0) for item in provider_runtime_brokers)
    runtime_tool_provider_request_execution_count = sum(int(item.get("tool_execution_count") or 0) for item in provider_runtime_brokers)
    deterministic_runtime_tool_fallback_request_count = sum(int(item.get("requested_tool_count") or 0) for item in deterministic_runtime_brokers)
    deterministic_runtime_tool_fallback_execution_count = sum(int(item.get("tool_execution_count") or 0) for item in deterministic_runtime_brokers)
    deterministic_runtime_tool_fallback_failed_count = sum(int(item.get("failed_tool_count") or 0) for item in deterministic_runtime_brokers)
    deterministic_runtime_tool_fallback_blocked_count = sum(int(item.get("blocked_tool_count") or 0) for item in deterministic_runtime_brokers)
    provider_empty_response_count = sum(1 for round_item in rounds if round_item.get("provider_empty_response"))
    provider_error_count = sum(1 for round_item in rounds if round_item.get("provider_error"))
    schema_repair_retry_attempt_count = sum(1 for round_item in rounds if round_item.get("schema_repair_retry", {}).get("attempted"))
    schema_repair_retry_accept_count = sum(1 for round_item in rounds if round_item.get("schema_repair_retry", {}).get("accepted"))
    runtime_tool_feedback_context_report_count = sum(1 for item in context_reports if isinstance(item, dict) and item.get("kind") == "runtime_tool_feedback_context")
    report_errors = list(errors)
    runtime_tool_bootstrap_failed = bool(runtime_tool_bootstrap.get("executed") and runtime_tool_bootstrap.get("passed") is not True)
    if runtime_tool_bootstrap_failed:
        detail = runtime_tool_bootstrap.get("error") or f"returncode={runtime_tool_bootstrap.get('returncode')} broker_output_exists={runtime_tool_bootstrap.get('broker_output_exists')}"
        report_errors.append(f"runtime_tool_bootstrap_failed: {detail}")
    if provider_empty_response_count:
        diagnostics = dict(diagnostics)
        diagnostics["empty_recommendations_reason"] = "provider_empty_response"
        diagnostics["recommended_next_layer"] = "inspect_provider_empty_response"
        fallback_recommended = False
    return {
        "schema_version": 1,
        "kind": "agent_gpu_deep_planning_supervised",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not report_errors,
        "errors": report_errors,
        "warnings": warnings,
        "provider_execution_performed": True,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "apply_mode": "report_only_gpu_deep_planning_with_non_blocking_npu_audit",
        "model_used": model_used,
        "ollama_base_url": normalize_base_url(args.ollama_base_url or DEFAULT_BASE_URL),
        "budget_minutes": args.budget_minutes,
        "elapsed_seconds": round(time.perf_counter() - started_at, 3),
        "context_file_count": context_file_count,
        "round_count": len(rounds),
        "rounds": rounds,
        "npu_audit_count": len(npu_audits),
        "npu_audit_requested_count": npu_requested_count,
        "npu_audit_success_count": npu_success_count,
        "npu_auditor_disabled_reason": npu_auditor_disabled_reason,
        "npu_audits": npu_audits,
        "runtime_tool_broker_enabled": bool(args.enable_runtime_tool_broker),
        "runtime_tool_bootstrap_enabled": bool(args.enable_runtime_tool_broker and not args.disable_runtime_tool_bootstrap),
        "runtime_tool_bootstrap_executed": bool(runtime_tool_bootstrap.get("executed")),
        "runtime_tool_bootstrap_passed": runtime_tool_bootstrap.get("passed"),
        "runtime_tool_bootstrap_request_count": int(runtime_tool_bootstrap.get("requested_tool_count") or 0),
        "runtime_tool_bootstrap_execution_count": int(runtime_tool_bootstrap.get("tool_execution_count") or 0),
        "runtime_tool_bootstrap_failed_count": int(runtime_tool_bootstrap.get("failed_tool_count") or 0),
        "runtime_tool_bootstrap_blocked_count": int(runtime_tool_bootstrap.get("blocked_tool_count") or 0),
        "runtime_tool_bootstrap_result_count": len(runtime_tool_bootstrap.get("tool_results", [])),
        "runtime_tool_bootstrap_output": runtime_tool_bootstrap.get("broker_output", ""),
        "runtime_tool_bootstrap": runtime_tool_bootstrap,
        "runtime_tool_request_count": runtime_tool_request_count,
        "runtime_tool_execution_count": runtime_tool_execution_count,
        "runtime_tool_failed_count": runtime_tool_failed_count,
        "runtime_tool_blocked_count": runtime_tool_blocked_count,
        "runtime_tool_result_count": runtime_tool_result_count,
        "runtime_tool_provider_request_count": runtime_tool_provider_request_count,
        "runtime_tool_provider_request_execution_count": runtime_tool_provider_request_execution_count,
        "runtime_tool_feedback_context_report_count": runtime_tool_feedback_context_report_count,
        "deterministic_runtime_tool_fallback_request_count": deterministic_runtime_tool_fallback_request_count,
        "deterministic_runtime_tool_fallback_execution_count": deterministic_runtime_tool_fallback_execution_count,
        "deterministic_runtime_tool_fallback_failed_count": deterministic_runtime_tool_fallback_failed_count,
        "deterministic_runtime_tool_fallback_blocked_count": deterministic_runtime_tool_fallback_blocked_count,
        "provider_empty_response_count": provider_empty_response_count,
        "provider_error_count": provider_error_count,
        "schema_repair_retry_attempt_count": schema_repair_retry_attempt_count,
        "schema_repair_retry_accept_count": schema_repair_retry_accept_count,
        "recommendation_count": len(recommendations),
        "recommendations": recommendations,
        **diagnostics,
        "decision": {
            "ready_for_patch_plan": bool(ready),
            "ready_count": len(ready),
            "needs_more_context_count": len(needs_context),
            "fallback_patch_plan_recommended": fallback_recommended,
            "npu_auditor_non_blocking": True,
            "npu_unusable_or_failed_count": len(unusable_npu),
            "npu_audit_success_count": npu_success_count,
            "npu_auditor_disabled_reason": npu_auditor_disabled_reason,
            "recommended_next_layer": diagnostics["recommended_next_layer"],
            "manual_review_required": True,
        },
        "inputs": {
            "evidence_kind": evidence.get("kind"),
            "refined_kind": refined.get("kind"),
            "context_report_count": len(context_reports),
        },
        "guardrails": {
            "provider_execution_requires_use_ollama": True,
            "npu_auditor_requires_include_npu_auditor": True,
            "npu_auditor_non_blocking": True,
            "npu_primary_advisory": False,
            "patch_application_performed": False,
            "real_github_pr_created": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
            "runtime_tool_broker_report_only": True,
            "runtime_tool_broker_requires_enable_runtime_tool_broker": True,
            "manual_review_required": True,
        },
    }


def checkpoint_paths(checkpoint_dir: Path, round_index: int) -> tuple[Path, Path, Path]:
    base = checkpoint_dir / f"round_{round_index:03d}"
    return base.with_suffix(".json"), base.with_suffix(".md"), base.with_name(base.name + "_npu_audit.json")


def run_npu_audit_for_checkpoint(repo_root: Path, checkpoint_json: Path, audit_json: Path, args: argparse.Namespace) -> dict[str, Any]:
    command = [
        sys.executable,
        "Tools/ai/run_npu_gpu_deep_review_auditor.py",
        "--repo-root",
        ".",
        "--gpu-review",
        str(checkpoint_json),
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
    ]
    if args.run_npu_auditor_provider:
        command.append("--run-npu")
    else:
        command.extend(["--run-npu", "--metadata-only"])
    returncode, stdout, stderr, error = run_command(command, repo_root, args.npu_auditor_timeout_seconds + 30)
    audit: dict[str, Any] = {
        "checkpoint": repo_rel(checkpoint_json, repo_root),
        "audit_output": repo_rel(audit_json, repo_root),
        "returncode": returncode,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "error": error or "",
        "blocking": False,
        "classification": "missing_audit_output",
        "provider_execution_requested": bool(args.run_npu_auditor_provider),
        "provider_load_attempted": False,
        "provider_execution_succeeded": False,
        "provider_execution_performed": False,
        "dependency_missing": False,
    }
    if audit_json.exists():
        try:
            data = read_json(audit_json)
            nested = data.get("npu_auditor", {})
            audit.update(
                {
                    "kind": data.get("kind"),
                    "passed": data.get("passed"),
                    "provider_execution_requested": data.get("provider_execution_requested", nested.get("provider_execution_requested")),
                    "provider_load_attempted": data.get("provider_load_attempted", nested.get("provider_load_attempted")),
                    "provider_execution_succeeded": data.get("provider_execution_succeeded", nested.get("provider_execution_succeeded")),
                    "provider_execution_performed": data.get("provider_execution_performed", nested.get("provider_execution_performed")),
                    "dependency_missing": data.get("dependency_missing", nested.get("dependency_missing")),
                    "classification": nested.get("classification") or data.get("classification"),
                    "gpu_review_blocked": data.get("decision", {}).get("gpu_review_blocked"),
                    "warnings": data.get("warnings", []),
                }
            )
        except Exception as exc:  # noqa: BLE001
            audit["error"] = f"{audit['error']} {type(exc).__name__}: {exc}".strip()
    return audit


def run_supervised(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    started_at = time.perf_counter()
    evidence = read_json(resolve_path(repo_root, args.evidence))
    refined = read_json(resolve_path(repo_root, args.refined_review)) if resolve_path(repo_root, args.refined_review).exists() else {}
    evidence_ready_count = evidence_ready_for_manual_patch_count(evidence)
    context_reports = []
    runtime_tool_bootstrap = run_runtime_tool_bootstrap(repo_root, args)
    setattr(args, "runtime_tool_bootstrap_result", runtime_tool_bootstrap)
    if runtime_tool_bootstrap.get("executed"):
        context_reports.append(runtime_tool_context_report(0, runtime_tool_bootstrap))
    for report_file in args.report_file:
        path = resolve_path(repo_root, report_file)
        if path.exists():
            try:
                data = read_json(path)
                context_reports.append({"path": repo_rel(path, repo_root), "kind": data.get("kind"), "passed": data.get("passed"), "summary": data.get("summary", {}), "decision": data.get("decision", {})})
            except Exception as exc:  # noqa: BLE001
                provider_error = f"{type(exc).__name__}: {exc}"
                context_reports.append({"path": repo_rel(path, repo_root), "error": str(exc)})
        else:
            context_reports.append({"path": repo_rel(path, repo_root), "error": "missing"})

    if not args.use_ollama:
        return {
            "schema_version": 1,
            "kind": "agent_gpu_deep_planning_supervised",
            "generated_at": now_iso(),
            "repo_root": str(repo_root),
            "passed": False,
            "errors": ["--use-ollama is required"],
            "warnings": [],
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "source_writes_performed": False,
            "apply_mode": "report_only_gpu_deep_planning_with_non_blocking_npu_audit",
            "elapsed_seconds": 0,
            "round_count": 0,
            "npu_audit_count": 0,
            "npu_audit_requested_count": 0,
            "npu_audit_success_count": 0,
            "npu_auditor_disabled_reason": "",
            "recommendation_count": 0,
            "raw_recommendation_candidate_count": 0,
            "filtered_recommendation_count": 0,
            "tool_request_count": 0,
            "valid_tool_request_count": 0,
            "invalid_tool_request_count": 0,
            "provider_empty_response_count": 0,
            "runtime_tool_broker_enabled": bool(args.enable_runtime_tool_broker),
            "runtime_tool_bootstrap_enabled": bool(args.enable_runtime_tool_broker and not args.disable_runtime_tool_bootstrap),
            "runtime_tool_bootstrap_executed": bool(runtime_tool_bootstrap.get("executed")),
            "runtime_tool_bootstrap_passed": runtime_tool_bootstrap.get("passed"),
            "runtime_tool_bootstrap_request_count": int(runtime_tool_bootstrap.get("requested_tool_count") or 0),
            "runtime_tool_bootstrap_execution_count": int(runtime_tool_bootstrap.get("tool_execution_count") or 0),
            "runtime_tool_bootstrap_failed_count": int(runtime_tool_bootstrap.get("failed_tool_count") or 0),
            "runtime_tool_bootstrap_blocked_count": int(runtime_tool_bootstrap.get("blocked_tool_count") or 0),
            "runtime_tool_bootstrap_result_count": len(runtime_tool_bootstrap.get("tool_results", [])),
            "runtime_tool_bootstrap_output": runtime_tool_bootstrap.get("broker_output", ""),
            "runtime_tool_bootstrap": runtime_tool_bootstrap,
            "runtime_tool_request_count": int(runtime_tool_bootstrap.get("requested_tool_count") or 0),
            "runtime_tool_execution_count": int(runtime_tool_bootstrap.get("tool_execution_count") or 0),
            "runtime_tool_failed_count": int(runtime_tool_bootstrap.get("failed_tool_count") or 0),
            "runtime_tool_blocked_count": int(runtime_tool_bootstrap.get("blocked_tool_count") or 0),
            "runtime_tool_result_count": len(runtime_tool_bootstrap.get("tool_results", [])),
            "runtime_tool_provider_request_count": 0,
            "runtime_tool_provider_request_execution_count": 0,
            "deterministic_runtime_tool_fallback_request_count": 0,
            "deterministic_runtime_tool_fallback_execution_count": 0,
            "deterministic_runtime_tool_fallback_failed_count": 0,
            "deterministic_runtime_tool_fallback_blocked_count": 0,
            "json_parse_error_count": 0,
            "repair_attempt_count": 0,
            "empty_recommendations_reason": "valid_json_empty_recommendations",
            "evidence_ready_for_manual_patch_count": evidence_ready_count,
            "recommended_next_layer": "collect_more_evidence",
            "decision": {"ready_for_patch_plan": False, "manual_review_required": True},
            "guardrails": {
                "provider_execution_requires_use_ollama": True,
                "patch_application_performed": False,
                "runtime_tool_bootstrap_report_only": True,
                "runtime_tool_bootstrap_requires_enable_runtime_tool_broker": True,
                "persistent_memory_write_performed": False,
            },
        }

    evidence_paths = extract_evidence_files(evidence)
    context_roots = list(args.context_root or []) + evidence_paths
    if not context_roots:
        context_roots = ["docs", "Tools/ai", "Tools/validation", "Tools/workflow"]
    context_files = collect_repo_context(repo_root, context_roots, args.max_context_files, args.max_chars_per_file)
    batches = split_batches(context_files, args.files_per_round)
    checkpoint_dir = resolve_path(repo_root, args.checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    deadline = started_at + max(1, args.budget_minutes) * 60
    rounds: list[dict[str, Any]] = []
    npu_audits: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []
    model_used = args.ollama_model or ""
    base_url = normalize_base_url(args.ollama_base_url or DEFAULT_BASE_URL)
    npu_auditor_disabled_reason = ""

    with OllamaModelManager(base_url=base_url, keep_alive=args.keep_alive, shutdown_server=False, startup_timeout=args.startup_timeout) as manager:
        for index, batch in enumerate(batches, start=1):
            if index > args.max_rounds:
                break
            if time.perf_counter() >= deadline and rounds:
                break
            context_reports = build_schema_repair_context_stack(
                base_context_reports=context_reports,
                rounds=rounds,
                evidence_ready_for_manual_patch_count=evidence_ready_count,
                provider="gpu_ollama",
            )
            prompt = build_prompt(
                objective=args.objective,
                evidence=evidence,
                refined=refined,
                context_reports=context_reports,
                batch=batch,
                round_index=index,
                elapsed_seconds=time.perf_counter() - started_at,
            )
            round_start = time.perf_counter()
            schema_repair_retry: dict[str, Any] = {"attempted": False, "accepted": False, "reason": "not_attempted"}
            raw_response = ""
            provider_error = ""
            model_used_for_round = model_used if "model_used" in locals() else model
            try:
                response, model_used = manager.generate(
                    args.ollama_model,
                    prompt,
                    max_new_tokens=args.max_new_tokens,
                    temperature=args.temperature,
                    response_format="json",
                )
                raw_response = response
                model_used_for_round = model_used
                if not str(response or "").strip():
                    parsed = {
                        "summary": "provider returned an empty response",
                        "confidence": "low",
                        "recommendations": [],
                        "tool_requests": [],
                        "missing_evidence": ["provider_empty_response"],
                        "next_best_action": "inspect provider runtime, prompt budget and model output settings",
                    }
                    parse_diagnostics = {
                        "json_ok": False,
                        "parse_error": "ProviderEmptyResponse: model returned an empty response",
                        "repair_attempt_count": 0,
                        "model_output_missing_required_fields": False,
                        "provider_empty_response": True,
                        "provider_error": provider_error,
                    }
                    errors.append(f"round {index}: provider_empty_response")
                else:
                    parsed, parse_diagnostics = parse_model_json_with_diagnostics(response, evidence_ready_count)
                    schema_repair_retry = run_schema_repair_retry_for_round(
                        manager=manager,
                        model=model_used,
                        args=args,
                        round_index=index,
                        objective=args.objective,
                        raw_response=raw_response,
                        parsed_response=parsed,
                        parse_diagnostics=parse_diagnostics,
                        context_reports=context_reports,
                        rounds=rounds,
                        evidence_ready_for_manual_patch_count=evidence_ready_count,
                    )
                    if schema_repair_retry.get("accepted"):
                        raw_response = str(schema_repair_retry.get("raw_response") or raw_response)
                        parsed = dict(schema_repair_retry.get("parsed_response") or parsed)
                        parse_diagnostics = dict(schema_repair_retry.get("parse_diagnostics") or parse_diagnostics)
            except Exception as exc:  # noqa: BLE001
                provider_error = f"{type(exc).__name__}: {exc}"
                response = ""
                raw_response = response
                parsed = {"summary": "provider error", "confidence": "low", "recommendations": [], "missing_evidence": [str(exc)], "next_best_action": "inspect provider error"}
                parse_diagnostics = {
                    "json_ok": False,
                    "parse_error": f"{type(exc).__name__}: {exc}",
                    "repair_attempt_count": 0,
                    "model_output_missing_required_fields": False,
                    "provider_empty_response": False,
                }
                errors.append(f"round {index}: {type(exc).__name__}: {exc}")
            round_diagnostics = recommendation_diagnostics_for_round(parsed, parse_diagnostics, evidence_ready_count)
            if parse_diagnostics.get("provider_empty_response"):
                round_diagnostics["empty_recommendations_reason"] = "provider_empty_response"
            valid_tool_requests, invalid_tool_request_errors = extract_valid_tool_requests(
                parsed,
                max_requests=args.runtime_tool_max_requests_per_round,
            )
            deterministic_fallback_used = False
            deterministic_fallback_reason = ""
            deterministic_fallback_requests: list[dict[str, Any]] = []
            broker_tool_requests = valid_tool_requests
            if invalid_tool_request_errors:
                warnings.append(f"round {index}: invalid tool requests: {invalid_tool_request_errors}")
            if not valid_tool_requests and args.enable_runtime_tool_broker:
                fallback_reason = str(round_diagnostics.get("empty_recommendations_reason") or "")
                if fallback_reason in {
                    "context_echo_detected",
                    "json_parse_failure",
                    "model_output_schema_mismatch",
                    "evidence_ready_but_no_tool_requests",
                    "valid_json_empty_recommendations",
                }:
                    deterministic_fallback_requests = deterministic_fallback_tool_requests(
                        fallback_reason,
                        max_requests=args.runtime_tool_max_requests_per_round,
                    )
                    if deterministic_fallback_requests:
                        deterministic_fallback_used = True
                        deterministic_fallback_reason = fallback_reason
                        broker_tool_requests = deterministic_fallback_requests
            runtime_broker = run_runtime_tool_broker_for_round(
                repo_root=repo_root,
                args=args,
                round_index=index,
                tool_requests=broker_tool_requests,
            )
            runtime_tool_feedback_context_appended = append_runtime_tool_feedback_context(
                context_reports,
                index,
                runtime_broker,
            )
            if deterministic_fallback_used:
                runtime_broker["source"] = "deterministic_fallback"
                runtime_broker["provider_generated_tool_requests"] = False
                runtime_broker["deterministic_fallback_reason"] = deterministic_fallback_reason
            elif valid_tool_requests:
                runtime_broker["source"] = "provider_tool_requests"
                runtime_broker["provider_generated_tool_requests"] = True
            if runtime_broker.get("error"):
                warnings.append(f"runtime tool broker round {index}: {runtime_broker.get('error')}")
            if runtime_broker.get("returncode") not in (None, 0):
                warnings.append(f"runtime tool broker round {index}: returncode={runtime_broker.get('returncode')}")
            if runtime_broker.get("executed"):
                context_reports.append(runtime_tool_context_report(index, runtime_broker))
            round_data = {
                "round": index,
                "elapsed_seconds": round(time.perf_counter() - round_start, 3),
                "file_count": len(batch),
                "files": [item.path for item in batch],
                "response_chars": len(response),
                "raw_response_preview": response[:3000],
                "parsed_response": parsed,
                "schema_repair_retry": summarize_schema_repair_retry(schema_repair_retry),
                "provider_empty_response": bool(parse_diagnostics.get("provider_empty_response")),
                "tool_requests": valid_tool_requests,
                "invalid_tool_request_errors": invalid_tool_request_errors,
                "runtime_tool_broker": runtime_broker,
                "provider_tool_request_count": len(valid_tool_requests),
                "deterministic_runtime_tool_fallback_used": deterministic_fallback_used,
                "deterministic_runtime_tool_fallback_reason": deterministic_fallback_reason,
                "deterministic_runtime_tool_fallback_request_count": len(deterministic_fallback_requests),
                **round_diagnostics,
            }
            rounds.append(round_data)
            interim_report = build_report(
                repo_root=repo_root,
                args=args,
                evidence=evidence,
                refined=refined,
                context_reports=context_reports,
                context_file_count=len(context_files),
                rounds=rounds,
                npu_audits=npu_audits,
                model_used=model_used,
                errors=errors,
                warnings=warnings,
                started_at=started_at,
                npu_auditor_disabled_reason=npu_auditor_disabled_reason,
            )
            checkpoint_json, checkpoint_md, audit_json = checkpoint_paths(checkpoint_dir, index)
            write_json(checkpoint_json, interim_report)
            checkpoint_md.write_text(build_markdown(interim_report), encoding="utf-8")
            should_audit = (
                args.include_npu_auditor
                and not npu_auditor_disabled_reason
                and index % max(1, args.npu_auditor_every_rounds) == 0
            )
            if should_audit:
                audit = run_npu_audit_for_checkpoint(repo_root, checkpoint_json, audit_json, args)
                npu_audits.append(audit)
                if audit.get("error"):
                    warnings.append(f"NPU audit round {index}: {audit.get('error')}")
                classification = str(audit.get("classification") or "")
                if classification not in {"usable_audit_text", "metadata_only", "not_executed"}:
                    warnings.append(f"NPU audit round {index}: classification={classification}")
                if classification in TERMINAL_NPU_AUDIT_CLASSIFICATIONS:
                    npu_auditor_disabled_reason = classification
                    warnings.append(f"NPU auditor circuit breaker enabled after round {index}: {classification}")

    return build_report(
        repo_root=repo_root,
        args=args,
        evidence=evidence,
        refined=refined,
        context_reports=context_reports,
        context_file_count=len(context_files),
        rounds=rounds,
        npu_audits=npu_audits,
        model_used=model_used,
        errors=errors,
        warnings=warnings,
        started_at=started_at,
        npu_auditor_disabled_reason=npu_auditor_disabled_reason,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--objective", default="Use explicit local GPU/Ollama reasoning to derive the safest next IA-Carmine patch plan while a non-blocking NPU auditor checks intermediate artifacts.")
    parser.add_argument("--evidence", default=DEFAULT_EVIDENCE)
    parser.add_argument("--refined-review", default=DEFAULT_REFINED)
    parser.add_argument("--report-file", action="append", default=[])
    parser.add_argument("--context-root", action="append", default=[])
    parser.add_argument("--max-context-files", type=int, default=160)
    parser.add_argument("--max-chars-per-file", type=int, default=8000)
    parser.add_argument("--files-per-round", type=int, default=10)
    parser.add_argument("--budget-minutes", type=int, default=30)
    parser.add_argument("--max-rounds", type=int, default=24)
    parser.add_argument("--use-ollama", action="store_true")
    parser.add_argument("--ollama-model", default=None)
    parser.add_argument("--ollama-base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--keep-alive", default="35m")
    parser.add_argument("--startup-timeout", type=float, default=30.0)
    parser.add_argument("--max-new-tokens", type=int, default=1800)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--enable-runtime-tool-broker", action="store_true")
    parser.add_argument("--runtime-tool-output-dir", default="output/ai_runtime_tools/gpu_planner_runtime_tools")
    parser.add_argument("--runtime-tool-timeout-seconds", type=int, default=300)
    parser.add_argument("--runtime-tool-max-requests-per-round", type=int, default=8)
    parser.add_argument("--disable-runtime-tool-bootstrap", action="store_true")
    parser.add_argument("--include-npu-auditor", action="store_true")
    parser.add_argument("--run-npu-auditor-provider", action="store_true", help="Actually execute OpenVINO/NPU auditor. Without this, auditor uses metadata-only mode.")
    parser.add_argument("--npu-auditor-every-rounds", type=int, default=1)
    parser.add_argument("--npu-auditor-timeout-seconds", type=int, default=900)
    parser.add_argument("--checkpoint-dir", default=DEFAULT_CHECKPOINT_DIR)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = run_supervised(args)
    output = resolve_path(repo_root, args.output)
    markdown_output = resolve_path(repo_root, args.markdown_output)
    write_json(output, report)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(build_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown_output),
                "provider_execution_performed": report["provider_execution_performed"],
                "patch_application_performed": report["patch_application_performed"],
                "elapsed_seconds": report["elapsed_seconds"],
                "round_count": report["round_count"],
                "npu_audit_count": report["npu_audit_count"],
                "npu_audit_success_count": report.get("npu_audit_success_count", 0),
                "npu_auditor_disabled_reason": report.get("npu_auditor_disabled_reason", ""),
                "recommendation_count": report["recommendation_count"],
                "raw_recommendation_candidate_count": report.get("raw_recommendation_candidate_count"),
                "filtered_recommendation_count": report.get("filtered_recommendation_count"),
                "tool_request_count": report.get("tool_request_count"),
                "valid_tool_request_count": report.get("valid_tool_request_count"),
                "invalid_tool_request_count": report.get("invalid_tool_request_count"),
                "empty_recommendations_reason": report.get("empty_recommendations_reason"),
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
                "provider_empty_response_count": report.get("provider_empty_response_count"),
                "evidence_ready_for_manual_patch_count": report.get("evidence_ready_for_manual_patch_count"),
                "ready_for_patch_plan": report["decision"].get("ready_for_patch_plan"),
                "recommended_next_layer": report["decision"].get("recommended_next_layer"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
