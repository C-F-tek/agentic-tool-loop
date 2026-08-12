#!/usr/bin/env python3
"""Build a report-only code patch plan from review evidence.

This builder turns `code_contract_drift` reports and optional
`code_interpreter_report` static recommendations into small, manual-review code
patch plan entries. It does not apply patches, execute providers, run Blender,
write source files, write SQLite databases or touch runtime output artifacts.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[2]
if str(REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORTS))

from Tools.ai.code_patch_plan_common import (  # noqa: E402
    line_count_for,
    load_line_counts,
    normalize_repo_path,
    now_iso,
    read_json_object,
    repo_rel,
    report_only_guardrails,
    resolve_output_path,
    target_path_errors,
    write_json_and_markdown,
)


PLAN_KIND = "agent_review_code_patch_plan"
APPLY_MODE = "report_only_manual_review_code_patch_plan"
DEFAULT_CODE_DRIFT_REPORT = "output/validation/code_contract_drift.json"
DEFAULT_OUTPUT = "output/patch_specs/agent_review_code_patch_plan.json"
DEFAULT_MARKDOWN = "output/patch_specs/agent_review_code_patch_plan.md"
DEFAULT_LINE_COUNT_CSV = "docs/LOCAL_VALIDATION_EVIDENCE/python_line_count_20260501-215122.csv"
DEFAULT_VALIDATION_COMMANDS = [
    "python .\\Tools\\validation\\check_python_syntax.py --repo-root . --output .\\output\\validation\\python_syntax.json",
    "python .\\Tools\\validation\\check_validation_report_contract.py --repo-root . --output .\\output\\validation\\validation_report_contract.json",
    "git diff --check",
]
COMMON_STOP_CONDITIONS = [
    "Stop if the edit requires provider execution, Blender runtime execution, or patch auto-apply.",
    "Stop if the patch touches output/**, generated indexes, full analysis JSON, SQLite, secrets, permissions, billing, or repository visibility.",
    "Stop if local validation fails.",
]
MAX_STATIC_RECOMMENDATIONS = 30


def list_len(value: Any) -> int:
    """Return list length only when the value is a list."""
    return len(value) if isinstance(value, list) else 0


def list_field(check: dict[str, Any], field: str) -> list[Any]:
    """Return a list-valued check field or an empty list."""
    value = check.get(field)
    return value if isinstance(value, list) else []


def stop_conditions_for(source_label: str) -> list[str]:
    """Return shared manual-review stop conditions for one evidence source."""
    return [f"Stop if the target file changed since {source_label} was generated.", *COMMON_STOP_CONDITIONS]


def source_kind_for(plan: dict[str, Any]) -> Any:
    """Return the source kind recorded on a code patch plan."""
    source_evidence = plan.get("source_evidence")
    return source_evidence.get("source_kind") if isinstance(source_evidence, dict) else None


def risk_for(path_value: str, check: dict[str, Any], counts: dict[str, int]) -> str:
    """Classify patch-plan risk from drift severity and file size."""
    lines = line_count_for(path_value, counts)
    base = "medium" if list_len(check.get("missing_required_terms")) or list_len(check.get("errors")) else "low"
    if lines is not None and lines >= 600:
        return "high" if base == "medium" else "medium"
    if list_len(check.get("warnings")) >= 5 and base == "low":
        return "medium"
    return base


def status_for(check: dict[str, Any]) -> str:
    """Return review status for one contract-drift check."""
    if check.get("ok") is False:
        return "ready_for_manual_review"
    if check.get("missing_recommended_terms") or check.get("warnings"):
        return "candidate_for_manual_review"
    return "informational"


def rationale_for(check: dict[str, Any]) -> str:
    """Build a concise rationale from one contract-drift check."""
    contract = check.get("contract") or "code contract"
    parts = [f"Contract drift check `{contract}` reported a code-review candidate."]
    for label, field in (
        ("Missing required terms", "missing_required_terms"),
        ("Missing recommended terms", "missing_recommended_terms"),
        ("Forbidden terms present", "forbidden_terms_present"),
    ):
        values = list_field(check, field)
        if values:
            parts.append(f"{label}: " + ", ".join(f"`{term}`" for term in values[:8]) + ".")
    return " ".join(parts)


def edit_strategy_for(path_value: str, check: dict[str, Any], counts: dict[str, int]) -> str:
    """Build the manual-review edit strategy for one code patch plan."""
    hint = first_safe_action_hint(check)
    lines = line_count_for(path_value, counts)
    size_note = f" Current CSV sizing hint: {lines} lines; verify current count locally before editing." if lines is not None else ""
    return (
        (hint or "Apply the smallest targeted code/config change that restores the documented contract terms.")
        + size_note
        + " Do not apply this plan automatically."
    )


def first_safe_action_hint(check: dict[str, Any]) -> str:
    """Return the first safe-action hint if present."""
    for action in list_field(check, "safe_actions"):
        if isinstance(action, dict) and action.get("hint"):
            return str(action["hint"])
    return ""


def validation_commands_for(path_value: str) -> list[str]:
    """Return validation commands recommended after manually applying a patch."""
    commands = list(DEFAULT_VALIDATION_COMMANDS)
    if Path(path_value).suffix.lower() == ".py":
        ps_path = path_value.replace("/", "\\")
        commands.insert(0, f"python -m py_compile .\\{ps_path}")
    return commands


def should_consider_check(check: Any) -> bool:
    """Return true when a contract-drift check can become a patch-plan candidate."""
    if not isinstance(check, dict):
        return False
    if check.get("ok") is False:
        return True
    return any(list_field(check, field) for field in ("missing_required_terms", "missing_recommended_terms", "errors", "warnings"))


def check_is_clean(check: dict[str, Any]) -> bool:
    """Return true when a check has no actionable drift."""
    return (
        not list_field(check, "missing_required_terms")
        and not list_field(check, "missing_recommended_terms")
        and not list_field(check, "errors")
        and not list_field(check, "warnings")
        and check.get("ok") is not False
    )


def plan_from_check(index: int, repo_root: Path, check: dict[str, Any], counts: dict[str, int]) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    """Convert one contract-drift check into one manual-review code patch plan."""
    path_value = normalize_repo_path(check.get("path"))
    skipped_id = f"code_contract_{index:03d}"
    if not path_value:
        return None, {"id": skipped_id, "reason": "check has no path"}
    errors = target_path_errors(repo_root, path_value)
    if errors:
        return None, {"id": skipped_id, "path": path_value, "reason": "; ".join(errors)}
    if check_is_clean(check):
        return None, {"id": skipped_id, "path": path_value, "reason": "check is already clean"}
    return build_plan(skipped_id, path_value, check, counts), None


def build_plan(plan_id: str, path_value: str, check: dict[str, Any], counts: dict[str, int]) -> dict[str, Any]:
    """Build the code patch-plan JSON object for one target file."""
    return {
        "id": plan_id,
        "area": str(check.get("owner_lane") or check.get("contract") or "validation"),
        "risk": risk_for(path_value, check, counts),
        "status": status_for(check),
        "target_files": [path_value],
        "rationale": rationale_for(check),
        "edit_strategy": edit_strategy_for(path_value, check, counts),
        "proposed_patch": "",
        "validation_commands": validation_commands_for(path_value),
        "stop_conditions": stop_conditions_for("the drift report"),
        "manual_review_required": True,
        "source_evidence": {
            "contract": check.get("contract"),
            "owner_lane": check.get("owner_lane"),
            "consumed_by_lanes": list_field(check, "consumed_by_lanes"),
            "missing_required_terms": list_field(check, "missing_required_terms"),
            "missing_recommended_terms": list_field(check, "missing_recommended_terms"),
            "errors": list_field(check, "errors"),
            "warnings": list_field(check, "warnings"),
            "line_count_csv_hint": line_count_for(path_value, counts),
            "source_kind": "code_contract_drift",
        },
    }


def validate_code_drift_report(code_drift: dict[str, Any], errors: list[str]) -> list[dict[str, Any]]:
    """Validate the code_contract_drift source report and return its checks."""
    if code_drift.get("kind") != "code_contract_drift":
        errors.append("code drift report kind must be code_contract_drift")
    for field in ("provider_execution_performed", "patch_application_performed", "source_writes_performed"):
        if code_drift.get(field) is not False:
            errors.append(f"code drift report {field} must be false")
    checks = code_drift.get("checks", [])
    if not isinstance(checks, list):
        errors.append("code drift report checks must be a list")
        return []
    return [check for check in checks if isinstance(check, dict)]


def validate_code_interpreter_report(code_report: dict[str, Any], errors: list[str]) -> list[dict[str, Any]]:
    """Validate optional code_interpreter_report and return recommendations."""
    if code_report.get("kind") != "code_interpreter_report":
        errors.append("code interpreter report kind must be code_interpreter_report")
    for field in ("provider_execution_performed", "patch_application_performed", "source_writes_performed"):
        if code_report.get(field) is not False:
            errors.append(f"code interpreter report {field} must be false")
    recommendations = code_report.get("recommendations", [])
    if not isinstance(recommendations, list):
        errors.append("code interpreter report recommendations must be a list")
        return []
    return [item for item in recommendations if isinstance(item, dict)]


def static_rationale_for(recommendation: dict[str, Any]) -> str:
    """Build rationale for static interpreter recommendations."""
    reasons = recommendation.get("reasons") if isinstance(recommendation.get("reasons"), list) else []
    reason_text = ", ".join(str(item) for item in reasons[:8]) or "static interpreter review signal"
    return f"Static code interpreter recommendation `{recommendation.get('id')}` flagged `{recommendation.get('target_file')}` for manual review: {reason_text}."


def static_strategy_for(path_value: str, recommendation: dict[str, Any], counts: dict[str, int]) -> str:
    """Build manual-review strategy for static interpreter recommendations."""
    lines = line_count_for(path_value, counts)
    size_note = f" Current CSV sizing hint: {lines} lines; verify current count locally before editing." if lines is not None else ""
    next_layer = recommendation.get("recommended_next_layer") or "agent_review_code_patch_plan"
    return (
        f"Inspect the static interpreter signals and decide whether a focused refactor, split, simplification, or guardrail improvement is warranted. Next layer: `{next_layer}`."
        + size_note
        + " Do not apply this plan automatically."
    )


def plan_from_static_recommendation(
    index: int,
    repo_root: Path,
    recommendation: dict[str, Any],
    counts: dict[str, int],
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    """Convert one static interpreter recommendation into one patch-plan candidate."""
    path_value = normalize_repo_path(recommendation.get("target_file"))
    skipped_id = f"code_static_{index:03d}"
    if not path_value:
        return None, {"id": skipped_id, "reason": "static recommendation has no target_file"}
    errors = target_path_errors(repo_root, path_value)
    if errors:
        return None, {"id": skipped_id, "path": path_value, "reason": "; ".join(errors)}
    risk = str(recommendation.get("risk") or "medium")
    status = str(recommendation.get("status") or "candidate_for_manual_review")
    plan = {
        "id": skipped_id,
        "area": "static_code_interpreter",
        "risk": risk if risk in {"low", "medium", "high"} else "medium",
        "status": status,
        "target_files": [path_value],
        "rationale": static_rationale_for(recommendation),
        "edit_strategy": static_strategy_for(path_value, recommendation, counts),
        "proposed_patch": "",
        "validation_commands": validation_commands_for(path_value),
        "stop_conditions": stop_conditions_for("the static code interpreter report"),
        "manual_review_required": True,
        "source_evidence": {
            "source_kind": "code_interpreter_report",
            "static_recommendation_id": recommendation.get("id"),
            "reasons": recommendation.get("reasons") if isinstance(recommendation.get("reasons"), list) else [],
            "recommended_next_layer": recommendation.get("recommended_next_layer"),
            "line_count_csv_hint": line_count_for(path_value, counts),
        },
    }
    return plan, None


def build_static_plans(
    repo_root: Path,
    code_interpreter_path: Path | None,
    counts: dict[str, int],
    errors: list[str],
    warnings: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, str]], bool]:
    """Build static interpreter patch-plan candidates when a report is supplied."""
    if code_interpreter_path is None:
        return [], [], False
    code_report, load_errors = read_json_object(code_interpreter_path)
    errors.extend(f"code interpreter report: {error}" for error in load_errors)
    if not code_report:
        return [], [], True
    recommendations = validate_code_interpreter_report(code_report, errors)
    plans: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for index, recommendation in enumerate(recommendations[:MAX_STATIC_RECOMMENDATIONS], start=1):
        plan, skip = plan_from_static_recommendation(index, repo_root, recommendation, counts)
        if plan:
            plans.append(plan)
        if skip:
            skipped.append(skip)
    if len(recommendations) > MAX_STATIC_RECOMMENDATIONS:
        warnings.append(f"static recommendations capped at {MAX_STATIC_RECOMMENDATIONS} of {len(recommendations)}")
    return plans, skipped, True


def build_code_patch_plan(
    repo_root: Path,
    code_drift_path: Path,
    line_count_csv: Path,
    code_interpreter_path: Path | None = None,
) -> dict[str, Any]:
    """Build the full agent_review_code_patch_plan report."""
    errors: list[str] = []
    warnings: list[str] = []
    code_drift, load_errors = read_json_object(code_drift_path)
    errors.extend(f"code drift report: {error}" for error in load_errors)
    counts, count_warnings = load_line_counts(repo_root, line_count_csv)
    warnings.extend(count_warnings)

    plans: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    if code_drift:
        checks = validate_code_drift_report(code_drift, errors)
        for index, check in enumerate(checks, start=1):
            if not should_consider_check(check):
                continue
            plan, skip = plan_from_check(index, repo_root, check, counts)
            if plan:
                plans.append(plan)
            if skip:
                skipped.append(skip)

    static_plans, static_skipped, static_report_loaded = build_static_plans(repo_root, code_interpreter_path, counts, errors, warnings)
    plans.extend(static_plans)
    skipped.extend(static_skipped)

    if code_drift and not plans:
        warnings.append("no code patch plans were produced from supplied evidence")

    return build_report(
        repo_root,
        code_drift_path,
        line_count_csv,
        code_interpreter_path,
        static_report_loaded,
        counts,
        plans,
        skipped,
        errors,
        warnings,
    )


def build_report(
    repo_root: Path,
    code_drift_path: Path,
    line_count_csv: Path,
    code_interpreter_path: Path | None,
    static_report_loaded: bool,
    counts: dict[str, int],
    plans: list[dict[str, Any]],
    skipped: list[dict[str, str]],
    errors: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    """Assemble the final report object."""
    static_count = sum(1 for plan in plans if source_kind_for(plan) == "code_interpreter_report")
    drift_count = sum(1 for plan in plans if source_kind_for(plan) == "code_contract_drift")
    return {
        "schema_version": 1,
        "kind": PLAN_KIND,
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "manual_review_required": True,
        "apply_mode": APPLY_MODE,
        "inputs": {
            "code_contract_drift_report": repo_rel(repo_root, code_drift_path),
            "line_count_csv": repo_rel(repo_root, line_count_csv),
            "line_count_csv_loaded": bool(counts),
            "code_interpreter_report": repo_rel(repo_root, code_interpreter_path) if code_interpreter_path else None,
            "code_interpreter_report_loaded": static_report_loaded,
        },
        "patch_plan_count": len(plans),
        "code_contract_patch_plan_count": drift_count,
        "static_code_patch_plan_count": static_count,
        "code_patch_plans": plans,
        "skipped_candidate_count": len(skipped),
        "skipped_candidates": skipped,
        "decision": {
            "ready_for_manual_review": bool(plans) and not errors,
            "patch_plan_count": len(plans),
            "manual_review_required": True,
            "recommended_next_layer": "manual_review_then_targeted_code_pr" if plans and not errors else "collect_or_fix_code_review_evidence",
        },
        "guardrails": report_only_guardrails(
            npu_primary_advisory=False,
            openvino_gpu_primary_lane=False,
            static_code_interpreter_consumed=static_report_loaded,
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render the code patch-plan report as Markdown."""
    lines = ["# Agent Review Code Patch Plan", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Apply mode: `{report['apply_mode']}`")
    lines.append(f"- Manual review required: `{report['manual_review_required']}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append(f"- Source writes performed: `{report['source_writes_performed']}`")
    lines.append(f"- Patch plan count: `{report['patch_plan_count']}`")
    lines.append(f"- Contract-drift plan count: `{report.get('code_contract_patch_plan_count')}`")
    lines.append(f"- Static-code plan count: `{report.get('static_code_patch_plan_count')}`")
    lines.append("")
    lines.extend(render_inputs(report))
    lines.extend(render_plans(report.get("code_patch_plans", [])))
    lines.extend(render_skipped(report.get("skipped_candidates", [])))
    lines.append("## Guardrail")
    lines.append("")
    lines.append("This artifact is a code patch plan only. It contains no replacements and must not be treated as an apply queue.")
    return "\n".join(lines) + "\n"


def render_inputs(report: dict[str, Any]) -> list[str]:
    """Render report input metadata."""
    lines = ["## Inputs", ""]
    for key, value in report.get("inputs", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    return lines


def render_plans(plans: Any) -> list[str]:
    """Render code patch plans."""
    lines = ["## Plans", ""]
    if not plans:
        return lines + ["- none", ""]
    for plan in plans:
        lines.append(f"### `{plan['id']}`")
        lines.append("")
        lines.append(f"- Area: `{plan['area']}`")
        lines.append(f"- Source kind: `{source_kind_for(plan)}`")
        lines.append(f"- Risk: `{plan['risk']}`")
        lines.append(f"- Status: `{plan['status']}`")
        lines.append(f"- Target files: `{', '.join(plan['target_files'])}`")
        lines.append(f"- Rationale: {plan['rationale']}")
        lines.append(f"- Strategy: {plan['edit_strategy']}")
        lines.append("")
    return lines


def render_skipped(skipped: Any) -> list[str]:
    """Render skipped candidate diagnostics."""
    if not skipped:
        return []
    lines = ["## Skipped candidates", ""]
    for item in skipped:
        lines.append(f"- `{item.get('id')}` `{item.get('path', '')}`: {item.get('reason')}")
    lines.append("")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--code-contract-drift-report", default=DEFAULT_CODE_DRIFT_REPORT)
    parser.add_argument("--line-count-csv", default=DEFAULT_LINE_COUNT_CSV)
    parser.add_argument("--code-interpreter-report", help="Optional code_interpreter_report JSON to turn static recommendations into patch-plan candidates.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    code_drift_path = resolve_output_path(repo_root, args.code_contract_drift_report)
    line_count_csv = resolve_output_path(repo_root, args.line_count_csv)
    code_interpreter_path = resolve_output_path(repo_root, args.code_interpreter_report) if args.code_interpreter_report else None
    report = build_code_patch_plan(repo_root, code_drift_path, line_count_csv, code_interpreter_path)
    print(write_json_and_markdown(repo_root, report, args.output, args.markdown_output, render_markdown(report)), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
