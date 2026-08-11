#!/usr/bin/env python3
"""Replay GPU planner raw responses through the JSON contract helper.

This report-only tool bridges the new contract helper into existing GPU planner
artifacts without re-running providers. It is intended as the safe validation
step before wiring the helper directly into long-running GPU providers.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.ai.gpu_planner_json_contract import result_to_dict, validate_model_response_contract
except ImportError:  # Script-style execution from Tools/ai.
    import sys

    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.gpu_planner_json_contract import result_to_dict, validate_model_response_contract  # type: ignore


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def repo_rel(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON root must be object: {path}")
    return value


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return default


def evidence_ready_count(gpu_report: dict[str, Any]) -> int:
    return safe_int(
        gpu_report.get("evidence_ready_for_manual_patch_count"),
        safe_int(gpu_report.get("gpu_evidence_ready_for_manual_patch_count"), 0),
    )


def round_raw_response(round_item: dict[str, Any]) -> str:
    for key in ("raw_response", "raw_response_preview", "response", "model_response"):
        value = round_item.get(key)
        if isinstance(value, str) and value:
            return value
    parsed = round_item.get("parsed_response")
    if isinstance(parsed, dict):
        summary = parsed.get("summary")
        if isinstance(summary, str) and summary:
            return summary
    return ""


def collect_rounds(gpu_report: dict[str, Any]) -> list[dict[str, Any]]:
    rounds = gpu_report.get("rounds")
    return [item for item in rounds if isinstance(item, dict)] if isinstance(rounds, list) else []


def classify_aggregate(replayed_rounds: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for item in replayed_rounds:
        reason = str(item.get("contract", {}).get("empty_recommendations_reason") or "")
        if not reason:
            reason = "valid_recommendation_output"
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def build_report(repo_root: Path, gpu_report_path: Path) -> dict[str, Any]:
    gpu_report = read_json(gpu_report_path)
    ready_count = evidence_ready_count(gpu_report)
    rounds = collect_rounds(gpu_report)
    replayed: list[dict[str, Any]] = []
    warnings: list[str] = []
    for item in rounds:
        raw = round_raw_response(item)
        if not raw:
            warnings.append(f"round {item.get('round')}: no raw response text available")
            continue
        result = validate_model_response_contract(raw, evidence_ready_for_manual_patch_count=ready_count)
        replayed.append(
            {
                "round": item.get("round"),
                "original_empty_recommendations_reason": item.get("empty_recommendations_reason"),
                "original_json_ok": item.get("json_ok"),
                "original_parse_error": item.get("parse_error"),
                "original_response_chars": item.get("response_chars"),
                "contract": result_to_dict(result),
            }
        )
    aggregate = classify_aggregate(replayed)
    return {
        "schema_version": 1,
        "kind": "gpu_planner_json_contract_replay",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": True,
        "errors": [],
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "blender_runtime_execution_performed": False,
        "sqlite_write_performed": False,
        "manual_review_required": True,
        "inputs": {"gpu_report": repo_rel(repo_root, gpu_report_path)},
        "source_summary": {
            "kind": gpu_report.get("kind"),
            "passed": gpu_report.get("passed"),
            "round_count": gpu_report.get("round_count"),
            "recommendation_count": gpu_report.get("recommendation_count"),
            "json_parse_error_count": gpu_report.get("json_parse_error_count"),
            "repair_attempt_count": gpu_report.get("repair_attempt_count"),
            "empty_recommendations_reason": gpu_report.get("empty_recommendations_reason"),
            "evidence_ready_for_manual_patch_count": ready_count,
        },
        "replayed_round_count": len(replayed),
        "contract_reason_counts": aggregate,
        "context_echo_detected_count": aggregate.get("context_echo_detected", 0),
        "json_parse_failure_count": aggregate.get("json_parse_failure", 0),
        "model_output_schema_mismatch_count": aggregate.get("model_output_schema_mismatch", 0),
        "valid_recommendation_output_count": aggregate.get("valid_recommendation_output", 0),
        "rounds": replayed,
        "decision": {
            "contract_helper_replay_available": True,
            "safe_to_wire_runner_after_replay": True,
            "recommended_next_layer": "wire validate_model_response_contract into run_agent_gpu_deep_planning_review.py",
            "manual_review_required": True,
        },
        "guardrails": {
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "source_writes_performed": False,
            "blender_runtime_execution_performed": False,
            "sqlite_write_performed": False,
            "manual_review_required": True,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# GPU Planner JSON Contract Replay", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Replayed rounds: `{report['replayed_round_count']}`")
    lines.append(f"- Context echo detected: `{report['context_echo_detected_count']}`")
    lines.append(f"- JSON parse failures: `{report['json_parse_failure_count']}`")
    lines.append(f"- Schema mismatches: `{report['model_output_schema_mismatch_count']}`")
    lines.append(f"- Valid recommendation outputs: `{report['valid_recommendation_output_count']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append(f"- Source writes performed: `{report['source_writes_performed']}`")
    lines.append("")
    lines.append("## Contract reason counts")
    lines.append("")
    for key, value in sorted(report["contract_reason_counts"].items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    for key, value in report["decision"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--gpu-report", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output", required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_report(repo_root, resolve_path(repo_root, args.gpu_report))
    output = resolve_path(repo_root, args.output)
    markdown_output = resolve_path(repo_root, args.markdown_output)
    write_json(output, report)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(render_markdown(report) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown_output),
                "replayed_round_count": report["replayed_round_count"],
                "contract_reason_counts": report["contract_reason_counts"],
                "patch_application_performed": report["patch_application_performed"],
                "source_writes_performed": report["source_writes_performed"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
