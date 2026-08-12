#!/usr/bin/env python3
"""Build runtime tool usage telemetry from full-toolbox GPU/NPU reports.

Report-only utility. It reads orchestrator, GPU, GPU/NPU sync and runtime broker
reports, then writes a compact committable JSON/MD summary under
docs/LOCAL_VALIDATION_EVIDENCE. It never executes providers or tools.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.ai.code_patch_plan_common import now_iso, read_json_object, repo_rel
    from Tools.validation.report_utils import resolve_output_path, write_json_report, write_text_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.code_patch_plan_common import now_iso, read_json_object, repo_rel  # type: ignore
    from Tools.validation.report_utils import resolve_output_path, write_json_report, write_text_report  # type: ignore

DEFAULT_OUTPUT = "docs/LOCAL_VALIDATION_EVIDENCE/runtime_tool_usage_telemetry.json"
DEFAULT_MARKDOWN = "docs/LOCAL_VALIDATION_EVIDENCE/runtime_tool_usage_telemetry.md"
MAX_SNIPPET_CHARS = 1200


def safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(',', '.'))
        except ValueError:
            return default
    return default


def split_path_values(value: Any) -> list[str]:
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else [value]
    out: list[str] = []
    for item in raw_items:
        for part in str(item).split(","):
            normalized = part.strip().strip("'\"")
            if normalized:
                out.append(normalized)
    return out

def compact_text(value: Any, max_chars: int = MAX_SNIPPET_CHARS) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = str(value)
    text = text.replace('\x00', '').strip()
    return text[:max_chars] + ("...[truncated]" if len(text) > max_chars else "")


def parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def elapsed_from_timestamps(started: Any, finished: Any) -> float:
    start_dt = parse_iso(started)
    finish_dt = parse_iso(finished)
    if not start_dt or not finish_dt:
        return 0.0
    return round(max(0.0, (finish_dt - start_dt).total_seconds()), 3)


def read_optional_json(repo_root: Path, value: str) -> tuple[dict[str, Any], list[str], str]:
    if not value:
        return {}, [], ""
    path = resolve_output_path(repo_root, value)
    rel = repo_rel(repo_root, path)
    if not path.exists():
        return {}, [f"optional input missing: {rel}"], rel
    data, errors = read_json_object(path, missing_is_error=True)
    return data, errors, rel


def maybe_read_broker_report(repo_root: Path, value: Any) -> dict[str, Any]:
    if not value:
        return {}
    path = resolve_output_path(repo_root, str(value))
    if not path.exists():
        return {}
    data, errors = read_json_object(path, missing_is_error=False)
    if errors:
        return {}
    return data


def summarize_result_output(result: dict[str, Any]) -> dict[str, Any]:
    output_paths: list[str] = []
    for key in (
        'output', 'output_file', 'report_output', 'markdown_output', 'csv_written',
        'broker_output', 'broker_markdown', 'request_file', 'path', 'artifact',
    ):
        value = result.get(key)
        if isinstance(value, str) and value and value not in output_paths:
            output_paths.append(value)
    nested_output = result.get('output') if isinstance(result.get('output'), dict) else {}
    for key, value in nested_output.items():
        if isinstance(value, str) and value and value not in output_paths:
            output_paths.append(value)
    return {
        'passed': result.get('passed'),
        'returncode': result.get('returncode'),
        'ok': result.get('ok'),
        'kind': result.get('kind'),
        'output_paths': output_paths[:12],
        'stdout_tail': compact_text(result.get('stdout_tail'), 600),
        'stderr_tail': compact_text(result.get('stderr_tail'), 600),
        'error': compact_text(result.get('error'), 600),
        'summary': compact_text(result.get('summary') or result.get('message') or result.get('result'), 600),
    }


def normalize_tool_result(
    *,
    caller: str,
    phase: str,
    round_id: int | None,
    broker_source: str,
    broker_path: str,
    request: dict[str, Any] | None,
    result: dict[str, Any],
) -> dict[str, Any]:
    request = request or {}
    tool_name = (
        result.get('tool')
        or result.get('tool_name')
        or request.get('tool')
        or request.get('tool_name')
        or result.get('name')
        or 'unknown'
    )
    started = result.get('started_at') or result.get('start_time')
    finished = result.get('finished_at') or result.get('end_time')
    elapsed = safe_float(result.get('elapsed_seconds')) or safe_float(result.get('duration_seconds')) or elapsed_from_timestamps(started, finished)
    return {
        'caller_ai': caller,
        'phase': phase,
        'round': round_id,
        'broker_source': broker_source,
        'broker_report': broker_path,
        'tool_request_id': result.get('id') or result.get('request_id') or request.get('id'),
        'tool': tool_name,
        'reason': request.get('reason') or result.get('reason'),
        'requested_args': request.get('args') if isinstance(request.get('args'), dict) else {},
        'status': result.get('status') or result.get('state'),
        'executed': result.get('executed'),
        'blocked': result.get('blocked'),
        'failed': result.get('failed'),
        'elapsed_seconds': elapsed,
        'started_at': started,
        'finished_at': finished,
        'result': summarize_result_output(result),
    }


def requests_by_id(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for raw in safe_list(report.get('tool_requests')):
        if not isinstance(raw, dict):
            continue
        request_id = str(raw.get('id') or raw.get('request_id') or '')
        if request_id:
            mapping[request_id] = raw
    return mapping


def collect_from_broker_report(
    *,
    repo_root: Path,
    broker_report: dict[str, Any],
    broker_path: str,
    caller: str,
    phase: str,
    round_id: int | None,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    request_map = requests_by_id(broker_report)
    results = safe_list(broker_report.get('tool_results'))
    for index, raw_result in enumerate(results, start=1):
        if not isinstance(raw_result, dict):
            continue
        result_id = str(raw_result.get('id') or raw_result.get('request_id') or '')
        request = request_map.get(result_id) if result_id else None
        entries.append(
            normalize_tool_result(
                caller=caller,
                phase=phase,
                round_id=round_id,
                broker_source=str(broker_report.get('source') or broker_report.get('kind') or phase),
                broker_path=broker_path,
                request=request,
                result=raw_result,
            )
        )
    if not entries and broker_report.get('tool_request_count') or broker_report.get('requested_tool_count'):
        entries.append(
            {
                'caller_ai': caller,
                'phase': phase,
                'round': round_id,
                'broker_source': str(broker_report.get('source') or broker_report.get('kind') or phase),
                'broker_report': broker_path,
                'tool_request_id': None,
                'tool': 'broker_summary_only',
                'status': 'summary_only',
                'requested_args': {},
                'elapsed_seconds': safe_float(broker_report.get('elapsed_seconds')),
                'result': {
                    'passed': broker_report.get('passed'),
                    'tool_request_count': broker_report.get('tool_request_count') or broker_report.get('requested_tool_count'),
                    'tool_execution_count': broker_report.get('tool_execution_count'),
                    'blocked_tool_count': broker_report.get('blocked_tool_count'),
                    'failed_tool_count': broker_report.get('failed_tool_count'),
                    'output_paths': [path for path in (broker_report.get('broker_output'), broker_report.get('broker_markdown')) if path],
                },
            }
        )
    return entries


def collect_broker_pointer_entries(repo_root: Path, raw_items: Any, caller: str, phase: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for raw in safe_list(raw_items):
        if not isinstance(raw, dict):
            continue
        round_id = safe_int(raw.get('round'), -1)
        round_value = round_id if round_id >= 0 else None
        broker_report = safe_dict(raw.get('broker_report'))
        broker_path = str(raw.get('broker_output') or raw.get('broker_report') or '')
        if not broker_report and broker_path:
            broker_report = maybe_read_broker_report(repo_root, broker_path)
        if broker_report:
            entries.extend(
                collect_from_broker_report(
                    repo_root=repo_root,
                    broker_report=broker_report,
                    broker_path=broker_path,
                    caller=caller,
                    phase=phase,
                    round_id=round_value,
                )
            )
            continue
        entries.append(
            {
                'caller_ai': caller,
                'phase': phase,
                'round': round_value,
                'broker_source': str(raw.get('source') or phase),
                'broker_report': broker_path,
                'tool_request_id': None,
                'tool': 'broker_packet_summary',
                'status': 'summary_only',
                'requested_args': {},
                'elapsed_seconds': safe_float(raw.get('elapsed_seconds')),
                'result': {
                    'passed': raw.get('passed'),
                    'tool_request_count': raw.get('tool_request_count') or raw.get('requested_tool_count'),
                    'tool_execution_count': raw.get('tool_execution_count'),
                    'blocked_tool_count': raw.get('blocked_tool_count'),
                    'failed_tool_count': raw.get('failed_tool_count'),
                    'output_paths': [path for path in (raw.get('broker_output'), raw.get('broker_markdown'), raw.get('request_file')) if path],
                    'stdout_tail': compact_text(raw.get('stdout_tail'), 600),
                    'stderr_tail': compact_text(raw.get('stderr_tail'), 600),
                    'error': compact_text(raw.get('error'), 600),
                },
            }
        )
    return entries


def append_default_broker_report_if_present(repo_root: Path, stamp: str, values: Any) -> list[str]:
    # Preserve final broker telemetry even if a caller omits --broker-report.
    paths = split_path_values(values)
    if not stamp:
        return paths

    default_path = repo_root / "output" / "validation" / f"runtime_tool_broker_full_toolbox_{stamp}.json"
    if not default_path.exists():
        return paths

    default_rel = repo_rel(repo_root, default_path)
    normalized_existing = {
        repo_rel(repo_root, resolve_output_path(repo_root, item))
        for item in paths
        if item
    }
    if default_rel not in normalized_existing:
        paths.append(default_rel)
    return paths


def collect_explicit_broker_reports(repo_root: Path, values: Any) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    entries: list[dict[str, Any]] = []
    warnings: list[str] = []
    paths: list[str] = []
    for index, raw_path in enumerate(split_path_values(values), start=1):
        path = resolve_output_path(repo_root, raw_path)
        rel = repo_rel(repo_root, path)
        paths.append(rel)
        if not path.exists():
            warnings.append(f"optional broker report missing: {rel}")
            continue
        data, read_errors = read_json_object(path, missing_is_error=True)
        if read_errors:
            warnings.extend(f"{rel}: {err}" for err in read_errors)
            continue
        if not isinstance(data, dict):
            warnings.append(f"{rel}: broker report is not a JSON object")
            continue
        entries.extend(
            collect_from_broker_report(
                repo_root=repo_root,
                broker_report=data,
                broker_path=rel,
                caller="orchestrator",
                phase="explicit_runtime_tool_broker_bootstrap",
                round_id=index,
            )
        )
    return entries, warnings, paths

def collect_gpu_declared_requests(gpu_report: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for round_item in safe_list(gpu_report.get('rounds')):
        if not isinstance(round_item, dict):
            continue
        round_id = safe_int(round_item.get('round'), -1)
        parsed = safe_dict(round_item.get('parsed_response'))
        for index, request in enumerate(safe_list(parsed.get('tool_requests')), start=1):
            if not isinstance(request, dict):
                continue
            entries.append(
                {
                    'caller_ai': 'gpu',
                    'phase': 'gpu_planner_declared_tool_requests',
                    'round': round_id if round_id >= 0 else None,
                    'broker_source': 'gpu_planner_response',
                    'broker_report': '',
                    'tool_request_id': request.get('id') or f'gpu_round_{round_id:03d}_declared_{index:03d}',
                    'tool': request.get('tool') or request.get('tool_name') or 'unknown',
                    'reason': request.get('reason'),
                    'requested_args': request.get('args') if isinstance(request.get('args'), dict) else {},
                    'status': 'declared_not_necessarily_executed',
                    'executed': False,
                    'blocked': None,
                    'failed': None,
                    'elapsed_seconds': 0.0,
                    'result': {'summary': 'Declared by GPU planner; execution is represented by broker records when available.'},
                }
            )
    return entries


def collect_npu_declared_requests(orchestrator: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for audit in safe_list(orchestrator.get('npu_audits')):
        if not isinstance(audit, dict):
            continue
        round_id = safe_int(audit.get('round'), -1)
        for index, request in enumerate(safe_list(audit.get('npu_tool_requests')), start=1):
            if not isinstance(request, dict):
                continue
            entries.append(
                {
                    'caller_ai': 'npu',
                    'phase': 'npu_auditor_declared_tool_requests',
                    'round': round_id if round_id >= 0 else None,
                    'broker_source': audit.get('audit_output'),
                    'broker_report': '',
                    'tool_request_id': request.get('id') or f'npu_round_{round_id:03d}_declared_{index:03d}',
                    'tool': request.get('tool') or request.get('tool_name') or 'unknown',
                    'reason': request.get('reason'),
                    'requested_args': request.get('args') if isinstance(request.get('args'), dict) else {},
                    'status': 'declared_not_necessarily_executed',
                    'executed': False,
                    'blocked': None,
                    'failed': None,
                    'elapsed_seconds': 0.0,
                    'result': {'summary': 'Declared by NPU auditor; execution is represented by broker records when available.'},
                }
            )
    return entries

def provider_evidence_summary(orchestrator: dict[str, Any], gpu_report: dict[str, Any]) -> dict[str, Any]:
    gpu_round_count = safe_int(gpu_report.get('round_count'))
    gpu_provider_performed = bool(
        gpu_report.get('provider_execution_performed')
        and gpu_round_count > 0
        and str(gpu_report.get('classification') or '') != 'required_provider_artifact_missing'
        and not bool(gpu_report.get('provider_empty_response'))
    )
    npu_success_count = safe_int(orchestrator.get('npu_audit_success_count'))
    npu_audit_count = safe_int(orchestrator.get('npu_audit_count'))
    npu_provider_performed = npu_success_count > 0
    degraded_reasons = []
    raw_reasons = orchestrator.get('provider_degraded_reasons')
    if isinstance(raw_reasons, list):
        degraded_reasons.extend(str(item) for item in raw_reasons)
    if not gpu_provider_performed and (orchestrator or gpu_report):
        degraded_reasons.append(
            'gpu_not_confirmed:'
            f"performed={gpu_report.get('provider_execution_performed')};"
            f"round_count={gpu_round_count};"
            f"classification={gpu_report.get('classification')};"
            f"passed={gpu_report.get('passed')}"
        )
    if orchestrator.get('npu_lane_mode') in {'skipped', 'metadata_only', 'degraded'} and npu_success_count == 0:
        degraded_reasons.append(
            'npu_auditor_not_confirmed:'
            f"audit_count={npu_audit_count};success_count={npu_success_count};"
            f"lane_mode={orchestrator.get('npu_lane_mode')}"
        )
    return {
        'provider_execution_performed': bool(gpu_provider_performed or npu_provider_performed),
        'gpu_provider_execution_performed': gpu_provider_performed,
        'gpu_round_count': gpu_round_count,
        'gpu_classification': gpu_report.get('classification'),
        'gpu_provider_empty_response': bool(gpu_report.get('provider_empty_response')),
        'npu_provider_execution_performed': npu_provider_performed,
        'npu_audit_count': npu_audit_count,
        'npu_audit_success_count': npu_success_count,
        'npu_lane_mode': orchestrator.get('npu_lane_mode'),
        'provider_degraded_reasons': degraded_reasons,
    }


def extract_declared_runtime_tool_counters(gpu_report: dict[str, Any], gpu_npu_sync: dict[str, Any]) -> dict[str, int]:
    # Extract planner-declared runtime tool counters even when no broker entry exists.
    candidates: list[dict[str, Any]] = []

    performance = safe_dict(safe_dict(gpu_npu_sync.get("performance")).get("gpu"))
    counters = safe_dict(performance.get("runtime_tool_counters"))
    if counters:
        candidates.append(counters)

    sync_metrics = safe_dict(gpu_npu_sync.get("metrics")) or safe_dict(gpu_npu_sync.get("sync_metrics"))
    if sync_metrics:
        candidates.append(sync_metrics)

    candidates.append(gpu_report)

    def first_int(*names: str) -> int:
        for source in candidates:
            for name in names:
                value = safe_int(source.get(name), -1)
                if value >= 0:
                    return value
        return 0

    request_count = first_int("runtime_tool_request_count", "runtime_tool_provider_request_count")
    execution_count = first_int("runtime_tool_execution_count", "runtime_tool_provider_request_execution_count")
    failed_count = first_int("runtime_tool_failed_count")
    blocked_count = first_int("runtime_tool_blocked_count")
    fallback_request_count = first_int("deterministic_runtime_tool_fallback_request_count")
    fallback_execution_count = first_int("deterministic_runtime_tool_fallback_execution_count")

    return {
        "runtime_tool_request_count": request_count,
        "runtime_tool_execution_count": execution_count,
        "runtime_tool_failed_count": failed_count,
        "runtime_tool_blocked_count": blocked_count,
        "runtime_tool_provider_request_count": first_int("runtime_tool_provider_request_count"),
        "runtime_tool_provider_request_execution_count": first_int("runtime_tool_provider_request_execution_count"),
        "deterministic_runtime_tool_fallback_request_count": fallback_request_count,
        "deterministic_runtime_tool_fallback_execution_count": fallback_execution_count,
        "declared_not_executed_count": max(0, request_count - execution_count),
    }


def build_declared_runtime_tool_counter_entry(counters: dict[str, int]) -> dict[str, Any]:
    # Create a single summary telemetry entry when only aggregate planner counters exist.
    return {
        "caller_ai": "gpu",
        "phase": "gpu_planner_declared_tool_request_counters",
        "round": None,
        "broker_source": "gpu_report_or_gpu_npu_sync_counters",
        "broker_report": "",
        "tool_request_id": "gpu_declared_runtime_tool_request_counter_summary",
        "tool": "declared_runtime_tool_request_summary",
        "reason": "GPU planner reported runtime tool request counters without broker-executed per-tool entries.",
        "requested_args": {},
        "status": "declared_counter_summary_not_broker_executed",
        "executed": False,
        "blocked": False,
        "failed": False,
        "elapsed_seconds": 0.0,
        "declared_counts": counters,
        "result": {
            "summary": "Planner declared runtime tool requests; broker execution count is reported separately.",
            **counters,
        },
    }

def summarize_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    by_caller: dict[str, dict[str, Any]] = {}
    by_tool: dict[str, dict[str, Any]] = {}
    by_phase: dict[str, dict[str, Any]] = {}
    total_elapsed = 0.0
    executed_count = 0
    failed_count = 0
    blocked_count = 0
    for entry in entries:
        caller = str(entry.get('caller_ai') or 'unknown')
        phase = str(entry.get('phase') or 'unknown')
        tool = str(entry.get('tool') or 'unknown')
        elapsed = safe_float(entry.get('elapsed_seconds'))
        total_elapsed += elapsed
        result = safe_dict(entry.get('result'))
        executed = entry.get('executed') is True or result.get('returncode') == 0 or result.get('passed') is True
        failed = entry.get('failed') is True or result.get('failed') is True or result.get('returncode') not in (None, 0)
        blocked = entry.get('blocked') is True
        executed_count += 1 if executed else 0
        failed_count += 1 if failed else 0
        blocked_count += 1 if blocked else 0
        for table, key in ((by_caller, caller), (by_tool, tool), (by_phase, phase)):
            item = table.setdefault(key, {'count': 0, 'executed': 0, 'failed': 0, 'blocked': 0, 'elapsed_seconds': 0.0})
            item['count'] += 1
            item['executed'] += 1 if executed else 0
            item['failed'] += 1 if failed else 0
            item['blocked'] += 1 if blocked else 0
            item['elapsed_seconds'] = round(float(item['elapsed_seconds']) + elapsed, 3)
    return {
        'tool_call_entry_count': len(entries),
        'executed_count': executed_count,
        'failed_count': failed_count,
        'blocked_count': blocked_count,
        'total_reported_tool_elapsed_seconds': round(total_elapsed, 3),
        'by_caller_ai': by_caller,
        'by_tool': by_tool,
        'by_phase': by_phase,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    orchestrator, orch_errors, orch_path = read_optional_json(repo_root, args.orchestrator)
    gpu_report, gpu_errors, gpu_path = read_optional_json(repo_root, args.gpu_report)
    gpu_npu_sync, sync_errors, sync_path = read_optional_json(repo_root, args.gpu_npu_sync)
    decision_loop, decision_errors, decision_path = read_optional_json(repo_root, args.decision_loop)
    warnings.extend(orch_errors + gpu_errors + sync_errors + decision_errors)

    entries: list[dict[str, Any]] = []
    entries.extend(collect_broker_pointer_entries(repo_root, orchestrator.get('runtime_tool_bootstrap_results'), 'orchestrator', 'orchestrator_bootstrap'))
    entries.extend(collect_broker_pointer_entries(repo_root, orchestrator.get('runtime_tool_bootstrap_result'), 'orchestrator', 'orchestrator_bootstrap'))
    broker_report_values = append_default_broker_report_if_present(repo_root, args.stamp, getattr(args, 'broker_report', []))
    explicit_broker_entries, explicit_broker_warnings, explicit_broker_paths = collect_explicit_broker_reports(repo_root, broker_report_values)
    entries.extend(explicit_broker_entries)
    warnings.extend(explicit_broker_warnings)
    entries.extend(collect_broker_pointer_entries(repo_root, orchestrator.get('gpu_runtime_tool_results'), 'gpu', 'gpu_runtime_tool_broker'))
    entries.extend(collect_broker_pointer_entries(repo_root, orchestrator.get('npu_runtime_tool_results'), 'npu', 'npu_runtime_tool_broker'))
    entries.extend(collect_gpu_declared_requests(gpu_report))
    entries.extend(collect_npu_declared_requests(orchestrator))
    declared_counters = extract_declared_runtime_tool_counters(gpu_report, gpu_npu_sync)
    if declared_counters["runtime_tool_request_count"] and not entries:
        entries.append(build_declared_runtime_tool_counter_entry(declared_counters))

    max_entries = max(1, int(args.max_entries))
    summary = summarize_entries(entries)
    summary.update(declared_counters)
    provider_evidence = provider_evidence_summary(orchestrator, gpu_report)
    return {
        'schema_version': 1,
        'kind': 'runtime_tool_usage_telemetry',
        'generated_at': now_iso(),
        'repo_root': str(repo_root),
        'stamp': args.stamp,
        'passed': not errors,
        'errors': errors,
        'warnings': warnings,
        'provider_execution_performed': provider_evidence['provider_execution_performed'],
        'provider_evidence': provider_evidence,
        'patch_application_performed': False,
        'source_writes_performed': False,
        'sqlite_write_performed': False,
        'persistent_memory_write_performed': False,
        'manual_review_required': True,
        'inputs': {
            'orchestrator': orch_path,
            'gpu_report': gpu_path,
            'gpu_npu_sync': sync_path,
            'decision_loop': decision_path,
            'broker_reports': explicit_broker_paths,
        },
        'decision_loop_summary': {
            'passed': decision_loop.get('passed'),
            'recommendation_count': decision_loop.get('recommendation_count'),
            'patch_plan_count': decision_loop.get('patch_plan_count'),
        },
        'gpu_npu_sync_metrics': gpu_npu_sync.get('metrics'),
        'summary': summary,
        'declared_runtime_tool_counters': declared_counters,
        'tool_calls': entries[:max_entries],
        'truncated_tool_call_count': max(0, len(entries) - max_entries),
        'guardrails': {
            'report_only': True,
            'committable_location': 'docs/LOCAL_VALIDATION_EVIDENCE',
            'raw_output_commit_allowed': False,
            'provider_execution_performed': provider_evidence['provider_execution_performed'],
            'gpu_provider_execution_performed': provider_evidence['gpu_provider_execution_performed'],
            'npu_provider_execution_performed': provider_evidence['npu_provider_execution_performed'],
            'patch_application_performed': False,
            'source_writes_performed': False,
            'sqlite_write_performed': False,
            'persistent_memory_write_performed': False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ['# Runtime Tool Usage Telemetry', '']
    lines.append(f"- Passed: `{report.get('passed')}`")
    lines.append(f"- Stamp: `{report.get('stamp')}`")
    provider_evidence = safe_dict(report.get('provider_evidence'))
    lines.append(f"- Provider execution performed: `{report.get('provider_execution_performed')}`")
    lines.append(f"- GPU provider execution performed: `{provider_evidence.get('gpu_provider_execution_performed')}`")
    lines.append(f"- NPU provider execution performed: `{provider_evidence.get('npu_provider_execution_performed')}`")
    if provider_evidence.get('provider_degraded_reasons'):
        lines.append(f"- Provider degraded reasons: `{provider_evidence.get('provider_degraded_reasons')}`")
    summary = safe_dict(report.get('summary'))
    lines.append(f"- Tool call entries: `{summary.get('tool_call_entry_count')}`")
    lines.append(f"- Executed count: `{summary.get('executed_count')}`")
    lines.append(f"- Failed count: `{summary.get('failed_count')}`")
    lines.append(f"- Blocked count: `{summary.get('blocked_count')}`")
    lines.append(f"- Total reported tool elapsed seconds: `{summary.get('total_reported_tool_elapsed_seconds')}`")
    lines.append(f"- Declared runtime tool requests: `{summary.get('runtime_tool_request_count')}`")
    lines.append(f"- Broker runtime tool executions: `{summary.get('runtime_tool_execution_count')}`")
    lines.append(f"- Declared not executed count: `{summary.get('declared_not_executed_count')}`")
    lines.append('')
    lines.append('## By caller AI')
    lines.append('')
    for caller, item in safe_dict(summary.get('by_caller_ai')).items():
        lines.append(f"- `{caller}`: count=`{item.get('count')}` executed=`{item.get('executed')}` failed=`{item.get('failed')}` elapsed=`{item.get('elapsed_seconds')}`")
    lines.append('')
    lines.append('## By phase')
    lines.append('')
    for phase, item in safe_dict(summary.get('by_phase')).items():
        lines.append(f"- `{phase}`: count=`{item.get('count')}` executed=`{item.get('executed')}` failed=`{item.get('failed')}` elapsed=`{item.get('elapsed_seconds')}`")
    lines.append('')
    lines.append('## By tool')
    lines.append('')
    for tool, item in safe_dict(summary.get('by_tool')).items():
        lines.append(f"- `{tool}`: count=`{item.get('count')}` executed=`{item.get('executed')}` failed=`{item.get('failed')}` elapsed=`{item.get('elapsed_seconds')}`")
    lines.append('')
    lines.append('## First tool call entries')
    lines.append('')
    for entry in safe_list(report.get('tool_calls'))[:25]:
        lines.append(f"- `{entry.get('caller_ai')}` `{entry.get('phase')}` round=`{entry.get('round')}` tool=`{entry.get('tool')}` status=`{entry.get('status')}` elapsed=`{entry.get('elapsed_seconds')}`")
    if report.get('warnings'):
        lines.append('')
        lines.append('## Warnings')
        lines.append('')
        for warning in safe_list(report.get('warnings'))[:30]:
            lines.append(f"- {warning}")
    lines.append('')
    return '\n'.join(lines) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', default='.')
    parser.add_argument('--stamp', required=True)
    parser.add_argument('--orchestrator', required=True)
    parser.add_argument('--gpu-report', required=True)
    parser.add_argument('--gpu-npu-sync', default='')
    parser.add_argument('--decision-loop', default='')
    parser.add_argument('--broker-report', action='append', default=[], help='Explicit agent_runtime_tool_broker JSON report. Repeatable or comma-separated.')
    parser.add_argument('--max-entries', type=int, default=400)
    parser.add_argument('--output', default=DEFAULT_OUTPUT)
    parser.add_argument('--markdown-output', default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    report = build_report(args)
    output = resolve_output_path(repo_root, args.output)
    markdown_output = resolve_output_path(repo_root, args.markdown_output)
    print(write_json_report(report, output), end='')
    write_text_report(render_markdown(report), markdown_output)
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
