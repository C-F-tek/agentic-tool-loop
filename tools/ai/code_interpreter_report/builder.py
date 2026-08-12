"""Report builder for static code interpreter reports."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from Tools.ai.code_edit_proposal_helpers import default_validation_commands_for
from Tools.ai.code_interpreter_report.constants import REPORT_KIND
from Tools.ai.code_interpreter_report.scanner import analyze_file, iter_python_files
from Tools.ai.code_patch_plan_common import now_iso, report_only_guardrails


def classify_file_risk(item: dict[str, Any]) -> str:
    """Classify static review risk for one file."""
    if not item.get("parse_ok"):
        return "high"
    if item.get("risk_signal_count", 0) >= 5 or item.get("line_count", 0) >= 800:
        return "high"
    if item.get("large_function_count", 0) or item.get("complex_function_count", 0) or item.get("line_count", 0) >= 400:
        return "medium"
    return "low"


def recommendation_reasons(item: dict[str, Any], risk: str) -> list[str]:
    """Return non-empty reasons for every medium/high static recommendation."""
    reasons: list[str] = []
    if not item.get("parse_ok"):
        reasons.append("file does not parse")
    if item.get("line_count", 0) >= 800:
        reasons.append("large Python module")
    elif risk in {"medium", "high"} and item.get("line_count", 0) >= 400:
        reasons.append("medium-size Python module")
    if item.get("large_function_count", 0):
        reasons.append("large functions detected")
    if item.get("complex_function_count", 0):
        reasons.append("complex functions detected")
    if item.get("risk_signal_count", 0):
        reasons.append("static risk calls detected")
    if item.get("todo_count", 0):
        reasons.append("TODO/FIXME markers detected")
    if risk in {"medium", "high"} and not reasons:
        branch_count = item.get("branch_count", 0)
        function_count = item.get("function_count", 0)
        line_count_value = item.get("line_count", 0)
        reasons.append(f"risk classified as {risk} from aggregate static metrics: lines={line_count_value}, functions={function_count}, branches={branch_count}")
    return reasons


def recommendation_record(index: int, item: dict[str, Any], risk: str, reasons: list[str]) -> dict[str, Any]:
    """Build one static recommendation record."""
    target_file = str(item.get("path") or "")
    return {
        "id": f"code_static_{index:03d}",
        "target_file": item.get("path"),
        "risk": risk,
        "status": "candidate_for_manual_review",
        "reasons": reasons,
        "recommended_next_layer": "agent_review_code_patch_plan" if item.get("parse_ok") else "syntax_fix_before_patch_plan",
        "validation_commands": default_validation_commands_for(target_file),
    }


def build_recommendations(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build static recommendations suitable for later patch-plan review."""
    recommendations: list[dict[str, Any]] = []
    for item in files:
        risk = classify_file_risk(item)
        if risk == "low" and not item.get("todo_count"):
            continue
        recommendations.append(recommendation_record(len(recommendations) + 1, item, risk, recommendation_reasons(item, risk)))
    return recommendations


def aggregate_imports(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return top imported modules."""
    counter: Counter[str] = Counter()
    for item in files:
        for imp in item.get("imports", []):
            if isinstance(imp, dict):
                module = imp.get("module") or imp.get("name") or ""
                if module:
                    counter[str(module).split(".")[0]] += 1
    return [{"module": module, "count": count} for module, count in counter.most_common(40)]


def aggregate_file_metrics(files: list[dict[str, Any]]) -> dict[str, int]:
    """Return aggregate report counters for analyzed files."""
    return {
        "file_count": len(files),
        "parsed_file_count": sum(1 for item in files if item.get("parse_ok")),
        "total_lines": sum(int(item.get("line_count") or 0) for item in files),
        "total_functions": sum(int(item.get("function_count") or 0) for item in files),
        "total_classes": sum(int(item.get("class_count") or 0) for item in files),
        "total_risk_signals": sum(int(item.get("risk_signal_count") or 0) for item in files),
        "total_todos": sum(int(item.get("todo_count") or 0) for item in files),
    }


def largest_file_entries(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return largest-file summary entries."""
    return sorted(
        [{"path": item.get("path"), "line_count": item.get("line_count"), "risk": classify_file_risk(item)} for item in files],
        key=lambda value: int(value.get("line_count") or 0),
        reverse=True,
    )[:30]


def build_report(repo_root: Path, roots: list[Path], excluded_dirs: set[str]) -> dict[str, Any]:
    """Build full static code interpreter report."""
    files = [analyze_file(repo_root, path) for path in iter_python_files(repo_root, roots, excluded_dirs)]
    errors = [f"{item.get('path')}: {'; '.join(item.get('errors') or [])}" for item in files if item.get("errors")]
    recommendations = build_recommendations(files)
    metrics = aggregate_file_metrics(files)
    return {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": [],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "manual_review_required": True,
        "apply_mode": "report_only_static_code_interpreter",
        **metrics,
        "top_imports": aggregate_imports(files),
        "largest_files": largest_file_entries(files),
        "risk_summary": dict(Counter(classify_file_risk(item) for item in files)),
        "recommendation_count": len(recommendations),
        "recommendations": recommendations[:80],
        "files": files,
        "guardrails": report_only_guardrails(
            static_analysis_only=True,
            project_code_executed=False,
            providers_executed=False,
            blender_runtime_executed=False,
            patches_applied=False,
            source_files_written=False,
        ),
    }
