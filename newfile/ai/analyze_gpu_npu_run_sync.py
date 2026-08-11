#!/usr/bin/env python3
"""Analyze GPU/NPU timing skew from an orchestrator report.

Report-only utility. It reads a completed GPU/NPU orchestrator JSON and produces
sync diagnostics, performance timing summaries, operational opinions and
balanced-run parameter suggestions. It does not run providers, apply patches,
write source files, execute Blender, write SQLite databases or change Git state.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.ai.code_patch_plan_common import read_json_object
    from Tools.validation.report_utils import write_json_report, write_text_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.code_patch_plan_common import read_json_object
    from Tools.validation.report_utils import write_json_report, write_text_report

GPU_ROUND_ELAPSED_SOURCE = "gpu_round_elapsed_seconds"
GPU_ROUND_ALIAS_SOURCE = "gpu_round_duration_fields"
GPU_ELAPSED_FALLBACK_SOURCE = "gpu_elapsed_divided_by_round_count"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def elapsed_seconds(started: float) -> float:
    return round(time.perf_counter() - started, 3)


def resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    return (repo_root / path).resolve() if not path.is_absolute() else path.resolve()


def repo_rel(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path)


def nested_dict(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def list_of_dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return default
    return default


def safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def first_int(default: int, *values: Any) -> int:
    for value in values:
        parsed = safe_int(value, default=-1)
        if parsed >= 0:
            return parsed
    return default


def parse_iso_seconds(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def duration_from_timestamps(started: Any, finished: Any) -> float:
    start_dt = parse_iso_seconds(started)
    finish_dt = parse_iso_seconds(finished)
    if not start_dt or not finish_dt:
        return 0.0
    return max(0.0, (finish_dt - start_dt).total_seconds())


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100.0) * (len(ordered) - 1))))
    return ordered[index]


def rounded_sum(values: list[float]) -> float:
    return round(sum(values), 3) if values else 0.0


def numeric_round_field(round_item: dict[str, Any], key: str) -> float:
    value = safe_float(round_item.get(key))
    return value if value > 0 else 0.0


def collect_round_field_durations(rounds: list[dict[str, Any]], key: str) -> list[float]:
    durations: list[float] = []
    for item in rounds:
        value = numeric_round_field(item, key)
        if value > 0:
            durations.append(value)
    return durations


def extract_round_duration_alias(round_item: dict[str, Any]) -> float:
    for key in ("round_elapsed_seconds", "duration_seconds", "provider_elapsed_seconds"):
        value = numeric_round_field(round_item, key)
        if value > 0:
            return value
    return duration_from_timestamps(round_item.get("started_at"), round_item.get("finished_at"))


def extract_gpu_round_durations(
    report: dict[str, Any],
    rounds: list[dict[str, Any]],
    round_count: int,
    gpu_elapsed: float,
) -> tuple[list[float], str]:
    """Prefer real ``rounds[*].elapsed_seconds`` over synthetic total/round timing."""
    elapsed_durations = collect_round_field_durations(rounds, "elapsed_seconds")
    if elapsed_durations:
        return elapsed_durations, GPU_ROUND_ELAPSED_SOURCE

    alias_durations = [extract_round_duration_alias(item) for item in rounds]
    alias_durations = [value for value in alias_durations if value > 0]
    if alias_durations:
        return alias_durations, GPU_ROUND_ALIAS_SOURCE

    if round_count > 0 and gpu_elapsed > 0:
        return [gpu_elapsed / round_count], GPU_ELAPSED_FALLBACK_SOURCE

    return [], "unavailable"


def audit_duration_seconds(audit: dict[str, Any]) -> float:
    explicit = safe_float(audit.get("elapsed_seconds"))
    if explicit > 0:
        return explicit
    return duration_from_timestamps(audit.get("started_at"), audit.get("finished_at"))


def compact_performance_source(data: dict[str, Any]) -> dict[str, Any]:
    performance = data.get("performance")
    if not isinstance(performance, dict):
        return {}
    return {
        str(key): value
        for key, value in performance.items()
        if isinstance(value, (int, float, str, bool)) or value is None
    }


def runtime_tool_counters(report: dict[str, Any]) -> dict[str, int]:
    keys = (
        "runtime_tool_request_count",
        "runtime_tool_execution_count",
        "runtime_tool_failed_count",
        "runtime_tool_blocked_count",
        "runtime_tool_provider_request_count",
        "runtime_tool_provider_request_execution_count",
        "deterministic_runtime_tool_fallback_request_count",
        "deterministic_runtime_tool_fallback_execution_count",
    )
    return {key: safe_int(report.get(key)) for key in keys}


def summarize_gpu_timing(
    *,
    report: dict[str, Any],
    gpu_summary: dict[str, Any],
    rounds: list[dict[str, Any]],
    round_count: int,
) -> dict[str, Any]:
    gpu_elapsed = (
        safe_float(report.get("gpu_elapsed_seconds"))
        or safe_float(gpu_summary.get("elapsed_seconds"))
        or safe_float(report.get("elapsed_seconds"))
    )
    round_durations, source = extract_gpu_round_durations(report, rounds, round_count, gpu_elapsed)
    return {
        "elapsed_seconds": round(gpu_elapsed, 3),
        "round_count": round_count,
        "round_duration_source": source,
        "round_duration_sample_count": len(round_durations),
        "avg_round_seconds": round(sum(round_durations) / len(round_durations), 3) if round_durations else 0.0,
        "p50_round_seconds": round(percentile(round_durations, 50), 3),
        "p90_round_seconds": round(percentile(round_durations, 90), 3),
        "max_round_seconds": round(max(round_durations), 3) if round_durations else 0.0,
        "round_durations_total_seconds": rounded_sum(round_durations),
        "provider_empty_response_count": safe_int(report.get("provider_empty_response_count")),
        "schema_repair_retry_attempt_count": safe_int(report.get("schema_repair_retry_attempt_count")),
        "schema_repair_retry_accept_count": safe_int(report.get("schema_repair_retry_accept_count")),
        "runtime_tool_counters": runtime_tool_counters(report),
        "embedded_performance": compact_performance_source(gpu_summary) or compact_performance_source(report),
    }


def summarize_npu_timing(report: dict[str, Any], npu_audits: list[dict[str, Any]]) -> dict[str, Any]:
    durations = [audit_duration_seconds(item) for item in npu_audits]
    durations = [value for value in durations if value > 0]
    status_counts: dict[str, int] = {}
    classification_counts: dict[str, int] = {}
    for item in npu_audits:
        status = str(item.get("status") or "unknown")
        classification = str(item.get("classification") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        classification_counts[classification] = classification_counts.get(classification, 0) + 1

    return {
        "audit_count": len(npu_audits),
        "audit_requested_count": safe_int(report.get("npu_audit_requested_count")),
        "audit_success_count": safe_int(report.get("npu_audit_success_count")),
        "duration_sample_count": len(durations),
        "avg_audit_seconds": round(sum(durations) / len(durations), 3) if durations else 0.0,
        "p50_audit_seconds": round(percentile(durations, 50), 3),
        "p90_audit_seconds": round(percentile(durations, 90), 3),
        "max_audit_seconds": round(max(durations), 3) if durations else 0.0,
        "audit_durations_total_seconds": rounded_sum(durations),
        "status_counts": status_counts,
        "classification_counts": classification_counts,
        "lane_diagnostics": nested_dict(report, "npu_lane_diagnostics"),
    }


def build_performance_summary(
    *,
    analyzer_started: float,
    report: dict[str, Any],
    gpu_summary: dict[str, Any],
    rounds: list[dict[str, Any]],
    npu_audits: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "analyzer_elapsed_seconds": elapsed_seconds(analyzer_started),
        "gpu": summarize_gpu_timing(
            report=report,
            gpu_summary=gpu_summary,
            rounds=rounds,
            round_count=metrics["gpu_round_count"],
        ),
        "npu": summarize_npu_timing(report, npu_audits),
        "sync": {
            "npu_to_gpu_avg_duration_ratio": metrics["npu_to_gpu_avg_duration_ratio"],
            "npu_audit_round_coverage": metrics["npu_audit_round_coverage"],
            "gpu_metrics_source": metrics["gpu_metrics_source"],
        },
        "guardrails": {
            "report_only": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "source_writes_performed": False,
            "blender_runtime_execution_performed": False,
            "sqlite_write_performed": False,
        },
    }


def build_suggestions(report: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    avg_gpu = metrics["avg_gpu_round_seconds"]
    avg_npu = metrics["avg_npu_audit_seconds"]
    suggested_every = max(2, min(8, round(avg_npu / avg_gpu))) if avg_gpu > 0 and avg_npu > 0 else 4
    reasoning: list[str] = []

    if metrics["npu_audit_count"] == 0:
        reasoning.append("No NPU audits were observed; first verify provider availability before tuning cadence.")
    if metrics["npu_audit_round_coverage"] < 0.35 and metrics["gpu_round_count"] >= 12:
        reasoning.append("NPU audit coverage is low compared with GPU round count; keep checkpoint auditing sampled, not per-round.")
    if metrics["gpu_metrics_source"] == GPU_ELAPSED_FALLBACK_SOURCE:
        reasoning.append("GPU per-round elapsed_seconds was unavailable; using total GPU elapsed divided by round count as estimate.")
    if metrics["npu_to_gpu_avg_duration_ratio"] > 2.0:
        reasoning.append("Average NPU audit duration is much slower than one GPU round; reduce NPU prompt/context/tokens and audit every several rounds.")
    if metrics["npu_audit_success_count"] == metrics["npu_audit_count"] and metrics["npu_audit_count"] > 0:
        reasoning.append("NPU audits are usable; tune cadence rather than disabling the lane.")
    if report.get("gpu_empty_recommendations_reason") == "repair_attempt_failed" or report.get("empty_recommendations_reason") == "repair_attempt_failed":
        reasoning.append("GPU JSON contract hardening should be tested before increasing GPU token budget further.")

    return {
        "recommended_profile": "gpu_npu_balanced_advisory",
        "reasoning": reasoning,
        "parameters": {
            "npu_auditor_every_rounds": suggested_every,
            "max_concurrent_npu_audits": 1,
            "npu_auditor_timeout_seconds": 420,
            "npu_max_context_chars": 8000,
            "npu_max_prompt_chars": 1200,
            "npu_max_new_tokens": 384,
            "npu_final_wait_seconds": 180,
            "gpu_max_new_tokens": 3600,
            "gpu_files_per_round": 8,
            "gpu_max_chars_per_file": 6000,
        },
        "guardrails": {
            "do_not_change_provider_model_settings_first": True,
            "keep_npu_auditor_non_blocking": True,
            "keep_max_concurrent_npu_audits": 1,
            "do_not_promote_npu_advisory": True,
            "do_not_make_openvino_gpu_primary": True,
        },
    }


def has_real_gpu_round_timing(metrics: dict[str, Any]) -> bool:
    return metrics.get("gpu_metrics_source") == GPU_ROUND_ELAPSED_SOURCE


def build_operational_opinions(metrics: dict[str, Any], performance: dict[str, Any]) -> list[str]:
    opinions: list[str] = []
    ratio = safe_float(metrics.get("npu_to_gpu_avg_duration_ratio"))
    coverage = safe_float(metrics.get("npu_audit_round_coverage"))
    runtime = nested_dict(nested_dict(performance, "gpu"), "runtime_tool_counters")
    runtime_failed = safe_int(runtime.get("runtime_tool_failed_count"))
    runtime_blocked = safe_int(runtime.get("runtime_tool_blocked_count"))

    if ratio > 2.0:
        opinions.append("NPU should remain an advisory sampled auditor, not a lockstep reviewer for every GPU round.")
    elif ratio > 0:
        opinions.append("GPU/NPU cadence is measurable; tune audit frequency from timing evidence rather than intuition.")
    if coverage < 0.5:
        opinions.append("Audit coverage is intentionally sparse; this is acceptable only if findings are high-signal and evidence-backed.")
    if not has_real_gpu_round_timing(metrics):
        opinions.append("GPU round timing is not sourced from rounds[*].elapsed_seconds; keep diagnostics degraded until real samples are present.")
    if runtime_failed or runtime_blocked:
        opinions.append("Runtime tool execution had failed or blocked requests; recommendations should reference broker evidence before proposing patches.")
    if not opinions:
        opinions.append("GPU/NPU timing is healthy enough for the current advisory workflow; keep the lane report-only.")
    return opinions


def build_refactoring_suggestions(metrics: dict[str, Any], performance: dict[str, Any]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    runtime = nested_dict(nested_dict(performance, "gpu"), "runtime_tool_counters")
    runtime_failed = safe_int(runtime.get("runtime_tool_failed_count"))
    runtime_blocked = safe_int(runtime.get("runtime_tool_blocked_count"))

    if not has_real_gpu_round_timing(metrics):
        suggestions.append(
            {
                "priority": "high",
                "area": "gpu_runner_timing",
                "recommendation": "Use rounds[*].elapsed_seconds as the primary GPU round timing source.",
                "evidence": f"gpu_metrics_source={metrics.get('gpu_metrics_source')}",
                "guardrail": "report_only_no_provider_setting_change",
            }
        )
    if safe_int(nested_dict(performance, "npu").get("duration_sample_count")) == 0 and safe_int(metrics.get("npu_audit_count")) > 0:
        suggestions.append(
            {
                "priority": "high",
                "area": "npu_auditor_timing",
                "recommendation": "Persist elapsed_seconds on every NPU audit record instead of relying only on timestamps.",
                "evidence": "NPU audits exist but no duration samples were extracted.",
                "guardrail": "do_not_promote_npu_advisory",
            }
        )
    if safe_float(metrics.get("npu_to_gpu_avg_duration_ratio")) > 2.0:
        suggestions.append(
            {
                "priority": "medium",
                "area": "npu_cadence",
                "recommendation": "Increase npu_auditor_every_rounds or reduce NPU context/tokens before increasing GPU budget.",
                "evidence": f"npu_to_gpu_avg_duration_ratio={metrics.get('npu_to_gpu_avg_duration_ratio')}",
                "guardrail": "keep_max_concurrent_npu_audits_1",
            }
        )
    if runtime_failed or runtime_blocked:
        suggestions.append(
            {
                "priority": "medium",
                "area": "runtime_tool_broker",
                "recommendation": "Surface failed/blocked runtime tool IDs in the next decision-loop patch plan input.",
                "evidence": f"failed={runtime_failed}, blocked={runtime_blocked}",
                "guardrail": "broker_report_only",
            }
        )
    if not suggestions:
        suggestions.append(
            {
                "priority": "low",
                "area": "observability",
                "recommendation": "Keep collecting GPU/NPU performance summaries and compare them across full-toolbox runs.",
                "evidence": "No immediate timing defect detected from available report fields.",
                "guardrail": "no_source_changes_without_evidence",
            }
        )
    return suggestions


def analyze(repo_root: Path, orchestrator_path: Path) -> dict[str, Any]:
    analyzer_started = time.perf_counter()
    report, read_errors = read_json_object(orchestrator_path)
    if read_errors:
        raise ValueError("; ".join(read_errors))

    gpu_summary = nested_dict(report, "gpu_summary")
    rounds = list_of_dicts(report.get("rounds"))
    npu_audits = list_of_dicts(report.get("npu_audits"))
    round_count = first_int(len(rounds), report.get("round_count"), gpu_summary.get("round_count"))
    audit_count = first_int(len(npu_audits), report.get("npu_audit_count"))
    success_count = first_int(0, report.get("npu_audit_success_count"))
    gpu_elapsed = safe_float(report.get("gpu_elapsed_seconds")) or safe_float(gpu_summary.get("elapsed_seconds")) or safe_float(report.get("elapsed_seconds"))
    gpu_round_durations, gpu_metrics_source = extract_gpu_round_durations(report, rounds, round_count, gpu_elapsed)
    npu_durations = [audit_duration_seconds(item) for item in npu_audits]
    npu_durations = [value for value in npu_durations if value > 0]
    avg_gpu = sum(gpu_round_durations) / len(gpu_round_durations) if gpu_round_durations else 0.0
    avg_npu = sum(npu_durations) / len(npu_durations) if npu_durations else 0.0

    metrics = {
        "gpu_round_count": round_count,
        "npu_audit_count": audit_count,
        "npu_audit_success_count": success_count,
        "npu_audit_round_coverage": round(audit_count / round_count, 3) if round_count else 0.0,
        "avg_gpu_round_seconds": round(avg_gpu, 3),
        "p50_gpu_round_seconds": round(percentile(gpu_round_durations, 50), 3),
        "p90_gpu_round_seconds": round(percentile(gpu_round_durations, 90), 3),
        "avg_npu_audit_seconds": round(avg_npu, 3),
        "p50_npu_audit_seconds": round(percentile(npu_durations, 50), 3),
        "p90_npu_audit_seconds": round(percentile(npu_durations, 90), 3),
        "npu_to_gpu_avg_duration_ratio": round(avg_npu / avg_gpu, 3) if avg_gpu else 0.0,
        "gpu_elapsed_seconds": round(gpu_elapsed, 3),
        "provider_execution_performed": bool(report.get("provider_execution_performed")),
        "patch_application_performed": bool(report.get("patch_application_performed")),
        "source_writes_performed": bool(report.get("source_writes_performed")),
        "gpu_metrics_source": gpu_metrics_source,
    }
    performance = build_performance_summary(
        analyzer_started=analyzer_started,
        report=report,
        gpu_summary=gpu_summary,
        rounds=rounds,
        npu_audits=npu_audits,
        metrics=metrics,
    )
    suggestions = build_suggestions(report, metrics)
    return {
        "schema_version": 1,
        "kind": "gpu_npu_run_sync_analysis",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": True,
        "errors": [],
        "warnings": [],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "blender_runtime_execution_performed": False,
        "sqlite_write_performed": False,
        "manual_review_required": True,
        "inputs": {"orchestrator": repo_rel(repo_root, orchestrator_path)},
        "metrics": metrics,
        "performance": performance,
        "suggestions": suggestions,
        "operational_opinions": build_operational_opinions(metrics, performance),
        "refactoring_suggestions": build_refactoring_suggestions(metrics, performance),
        "decision": {
            "npu_too_slow_for_per_round_lockstep": metrics["npu_to_gpu_avg_duration_ratio"] > 1.5,
            "recommended_next_layer": "feed timing-backed GPU/NPU suggestions into decision-loop patch planning",
            "manual_review_required": True,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# GPU/NPU Run Sync Analysis", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append(f"- Source writes performed: `{report['source_writes_performed']}`")
    lines.append("")
    lines.append("## Metrics")
    lines.append("")
    for key, value in report["metrics"].items():
        lines.append(f"- `{key}`: `{value}`")

    gpu = nested_dict(report["performance"], "gpu")
    npu = nested_dict(report["performance"], "npu")
    lines.extend(
        [
            "",
            "## Performance",
            "",
            f"- Analyzer elapsed seconds: `{report['performance'].get('analyzer_elapsed_seconds')}`",
            f"- GPU elapsed seconds: `{gpu.get('elapsed_seconds')}`",
            f"- GPU average round seconds: `{gpu.get('avg_round_seconds')}`",
            f"- GPU timing source: `{gpu.get('round_duration_source')}`",
            f"- GPU timing sample count: `{gpu.get('round_duration_sample_count')}`",
            f"- GPU round durations total seconds: `{gpu.get('round_durations_total_seconds')}`",
            f"- NPU average audit seconds: `{npu.get('avg_audit_seconds')}`",
            f"- NPU duration sample count: `{npu.get('duration_sample_count')}`",
            "",
            "## Operational opinions",
            "",
        ]
    )
    for item in report.get("operational_opinions", []):
        lines.append(f"- {item}")

    lines.extend(["", "## Refactoring suggestions", ""])
    for item in report.get("refactoring_suggestions", []):
        lines.append(f"- `{item.get('priority')}` `{item.get('area')}`: {item.get('recommendation')} Evidence: {item.get('evidence')}")

    lines.extend(["", "## Suggested balanced profile", ""])
    for key, value in report["suggestions"]["parameters"].items():
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(["", "## Reasoning", ""])
    for item in report["suggestions"].get("reasoning", []):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--orchestrator", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output", required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = analyze(repo_root, resolve_path(repo_root, args.orchestrator))
    output = resolve_path(repo_root, args.output)
    markdown_output = resolve_path(repo_root, args.markdown_output)
    write_json_report(report, output)
    write_text_report(render_markdown(report) + "\n", markdown_output)
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown_output),
                "npu_to_gpu_avg_duration_ratio": report["metrics"]["npu_to_gpu_avg_duration_ratio"],
                "npu_too_slow_for_per_round_lockstep": report["decision"]["npu_too_slow_for_per_round_lockstep"],
                "performance": report["performance"],
                "refactoring_suggestion_count": len(report["refactoring_suggestions"]),
                "patch_application_performed": report["patch_application_performed"],
                "source_writes_performed": report["source_writes_performed"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
