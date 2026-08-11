#!/usr/bin/env python3
"""Normalize warning/error severity across agent-review levels.

The policy is report-only. It keeps diagnostic failures visible as structured
warnings when a later authoritative layer recovers them into valid output.

Levels covered by the ledger:

- tool
- app
- workflow
- ai
- provider
- validator
- evidence
- memory
- runtime
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
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
    from Tools.ai.code_patch_plan_common import read_json_object  # type: ignore
    from Tools.validation.report_utils import write_json_report, write_text_report  # type: ignore

LEVELS = {
    "tool",
    "app",
    "workflow",
    "ai",
    "provider",
    "validator",
    "evidence",
    "memory",
    "runtime",
}
FINAL_KINDS = {
    "agent_review_decision_loop",
    "agent_review_full_toolbox_decision_loop_integrated",
    "github_evidence_bundle_validation",
    "python_syntax",
    "validation_report_contract",
}
DEFAULT_OUTPUT = "output/validation/agent_review_warning_policy.json"
DEFAULT_MARKDOWN_OUTPUT = "output/validation/agent_review_warning_policy.md"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve(strict=False)


def repo_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return path.resolve(strict=False).as_posix()


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_report(repo_root: Path, value: str | Path, *, missing_is_error: bool = True) -> tuple[Path, dict[str, Any], list[str]]:
    path = resolve_path(repo_root, value)
    data, errors = read_json_object(path, missing_is_error=missing_is_error)
    return path, data, [f"{repo_rel(path, repo_root)}: {error}" for error in errors]


def infer_level(path: str, report: dict[str, Any]) -> str:
    kind = str(report.get("kind") or "").lower()
    normalized_path = path.lower().replace("\\", "/")
    if "workflow" in kind:
        return "workflow"
    if "npu" in kind or "gpu" in kind or "provider" in kind or "parallel_gpu" in normalized_path:
        return "provider"
    if "broker" in kind or "runtime_tool" in kind:
        return "runtime"
    if "memory" in kind or "sqlite" in kind:
        return "memory"
    if "validation" in kind or "syntax" in kind or "/validation/" in normalized_path:
        return "validator"
    if "evidence" in kind or "/local_validation_evidence/" in normalized_path:
        return "evidence"
    if "decision_loop" in kind or "planner" in kind or "review" in kind or "ai" in kind:
        return "ai"
    if "app" in kind:
        return "app"
    return "tool"


def extract_reason(report: dict[str, Any]) -> str:
    for key in (
        "empty_recommendations_reason",
        "gpu_empty_recommendations_reason",
        "reason",
        "status_reason",
        "failure_reason",
    ):
        value = report.get(key)
        if value:
            return str(value)
    decision = report.get("decision")
    if isinstance(decision, dict):
        for key in ("gpu_empty_recommendations_reason", "reason", "failure_reason"):
            value = decision.get(key)
            if value:
                return str(value)
    errors = report.get("errors")
    if isinstance(errors, list) and errors:
        return "; ".join(str(item) for item in errors[:5])
    if isinstance(errors, dict) and errors:
        return json.dumps(errors, sort_keys=True, ensure_ascii=False)[:500]
    return "passed=false diagnostic report without explicit reason"


def extract_next_layer(report: dict[str, Any]) -> str:
    for key in ("recommended_next_layer", "next_best_action"):
        value = report.get(key)
        if value:
            return str(value)
    decision = report.get("decision")
    if isinstance(decision, dict):
        for key in ("recommended_next_layer", "next_best_action"):
            value = decision.get(key)
            if value:
                return str(value)
    return ""


def extract_existing_warnings(path: str, report: dict[str, Any], level: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    raw_warnings = report.get("warnings")
    if isinstance(raw_warnings, list):
        for index, item in enumerate(raw_warnings):
            result.append(
                {
                    "path": path,
                    "kind": report.get("kind"),
                    "level": level,
                    "severity": "warning",
                    "classification": "reported_warning",
                    "recoverable": True,
                    "message": str(item),
                    "index": index,
                }
            )
    elif isinstance(raw_warnings, dict) and raw_warnings:
        result.append(
            {
                "path": path,
                "kind": report.get("kind"),
                "level": level,
                "severity": "warning",
                "classification": "reported_warning",
                "recoverable": True,
                "message": json.dumps(raw_warnings, sort_keys=True, ensure_ascii=False)[:500],
                "index": 0,
            }
        )
    return result


def final_decision_recovered(decision_report: dict[str, Any], *, min_recommendations: int, min_patch_plans: int) -> bool:
    if not decision_report:
        return False
    if decision_report.get("passed") is not True:
        return False
    if as_int(decision_report.get("recommendation_count")) < min_recommendations:
        return False
    if as_int(decision_report.get("patch_plan_count")) < min_patch_plans:
        return False
    if decision_report.get("patch_application_performed") is not False:
        return False
    if decision_report.get("provider_execution_performed") not in (False, None):
        return False
    if decision_report.get("sqlite_write_performed") not in (False, None):
        return False
    if decision_report.get("persistent_memory_write_performed") not in (False, None):
        return False
    return True


def is_final_authoritative(path: str, report: dict[str, Any], final_report_paths: set[str]) -> bool:
    if path in final_report_paths:
        return True
    return str(report.get("kind") or "") in FINAL_KINDS


def build_policy_report(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    ledger: list[dict[str, Any]] = []
    input_nonfatal: list[dict[str, Any]] = []
    fatal_failures: list[dict[str, Any]] = []

    decision_path, decision_report, decision_errors = load_report(repo_root, args.decision_report, missing_is_error=True)
    errors.extend(decision_errors)
    final_paths = {repo_rel(decision_path, repo_root)}
    for value in args.final_report:
        final_paths.add(repo_rel(resolve_path(repo_root, value), repo_root))

    recovered = final_decision_recovered(
        decision_report,
        min_recommendations=args.min_recommendations,
        min_patch_plans=args.min_patch_plans,
    )
    if not recovered:
        errors.append(
            "decision report did not recover workflow: expected passed=true, recommendation_count >= minimum, patch_plan_count >= minimum and guardrails false"
        )

    report_values = list(args.report_file)
    for value in args.final_report:
        if value not in report_values:
            report_values.append(value)
    if args.decision_report not in report_values:
        report_values.append(args.decision_report)

    seen_paths: set[str] = set()
    for value in report_values:
        path, report, load_errors = load_report(repo_root, value, missing_is_error=False)
        rel_path = repo_rel(path, repo_root)
        if rel_path in seen_paths:
            continue
        seen_paths.add(rel_path)
        if load_errors:
            for error in load_errors:
                fatal_failures.append(
                    {
                        "path": rel_path,
                        "kind": None,
                        "level": "tool",
                        "severity": "error",
                        "classification": "missing_or_invalid_report",
                        "recoverable": False,
                        "reason": error,
                    }
                )
            continue
        if not report:
            continue
        level = infer_level(rel_path, report)
        ledger.extend(extract_existing_warnings(rel_path, report, level))
        passed = report.get("passed")
        if passed is False:
            entry = {
                "path": rel_path,
                "kind": report.get("kind"),
                "level": level,
                "severity": "warning" if recovered and not is_final_authoritative(rel_path, report, final_paths) else "error",
                "classification": "input_nonfatal" if recovered and not is_final_authoritative(rel_path, report, final_paths) else "fatal_report_failure",
                "recoverable": bool(recovered and not is_final_authoritative(rel_path, report, final_paths)),
                "reason": extract_reason(report),
                "recommended_next_layer": extract_next_layer(report),
                "recovered_by": repo_rel(decision_path, repo_root) if recovered else "",
            }
            if entry["classification"] == "input_nonfatal":
                input_nonfatal.append(entry)
                ledger.append(entry)
            else:
                fatal_failures.append(entry)
                ledger.append(entry)

    if input_nonfatal:
        warnings.append(
            f"input_nonfatal_warnings present: {len(input_nonfatal)} diagnostic report(s) had passed=false but were recovered by the final decision layer"
        )
    if fatal_failures:
        errors.extend(f"{item['path']}: {item['classification']}: {item.get('reason', '')}" for item in fatal_failures)

    level_counts = Counter(str(item.get("level")) for item in ledger)
    classification_counts = Counter(str(item.get("classification")) for item in ledger)
    return {
        "schema_version": 1,
        "kind": "agent_review_warning_policy",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "manual_review_required": True,
        "decision_recovered": recovered,
        "decision_report": repo_rel(decision_path, repo_root),
        "recommendation_count": decision_report.get("recommendation_count"),
        "patch_plan_count": decision_report.get("patch_plan_count"),
        "warning_count": len(ledger),
        "input_nonfatal_warning_count": len(input_nonfatal),
        "fatal_report_failure_count": len(fatal_failures),
        "warning_level_counts": dict(sorted(level_counts.items())),
        "warning_classification_counts": dict(sorted(classification_counts.items())),
        "input_nonfatal_warnings": input_nonfatal,
        "fatal_report_failures": fatal_failures,
        "warning_ledger": ledger,
        "policy": {
            "scope": sorted(LEVELS),
            "final_authoritative_kinds": sorted(FINAL_KINDS),
            "input_nonfatal_condition": "final decision layer recovered into valid recommendations and patch plans under guardrails",
            "fatal_condition": "final authoritative report failed, required report is invalid, or guardrail was violated",
        },
        "guardrails": {
            "report_only": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agent Review Warning Policy", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Decision recovered: `{report['decision_recovered']}`")
    lines.append(f"- Warning count: `{report['warning_count']}`")
    lines.append(f"- Input-nonfatal warning count: `{report['input_nonfatal_warning_count']}`")
    lines.append(f"- Fatal report failure count: `{report['fatal_report_failure_count']}`")
    lines.append(f"- Recommendation count: `{report.get('recommendation_count')}`")
    lines.append(f"- Patch plan count: `{report.get('patch_plan_count')}`")
    lines.append("")
    lines.append("## Warning level counts")
    lines.append("")
    for key, value in report.get("warning_level_counts", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Input-nonfatal warnings")
    lines.append("")
    if not report.get("input_nonfatal_warnings"):
        lines.append("- none")
    for item in report.get("input_nonfatal_warnings", []):
        lines.append(f"- `{item.get('level')}` `{item.get('path')}`: {item.get('reason')}")
    if report.get("fatal_report_failures"):
        lines.append("")
        lines.append("## Fatal report failures")
        lines.append("")
        for item in report.get("fatal_report_failures", []):
            lines.append(f"- `{item.get('level')}` `{item.get('path')}`: {item.get('reason')}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--decision-report", required=True)
    parser.add_argument("--report-file", action="append", default=[])
    parser.add_argument("--final-report", action="append", default=[])
    parser.add_argument("--min-recommendations", type=int, default=1)
    parser.add_argument("--min-patch-plans", type=int, default=1)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN_OUTPUT)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_policy_report(args)
    output = resolve_path(repo_root, args.output)
    markdown_output = resolve_path(repo_root, args.markdown_output)
    write_json_report(report, output)
    write_text_report(render_markdown(report), markdown_output)
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown_output),
                "decision_recovered": report["decision_recovered"],
                "warning_count": report["warning_count"],
                "input_nonfatal_warning_count": report["input_nonfatal_warning_count"],
                "fatal_report_failure_count": report["fatal_report_failure_count"],
                "provider_execution_performed": report["provider_execution_performed"],
                "patch_application_performed": report["patch_application_performed"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
