#!/usr/bin/env python3
"""Validate deterministic local AI enrichment plans.

The enrichment plan coordinates semantic chunks, selected chunks, context packs,
agent state, GPU advisory and NPU knowledge-broker scheduling. The contract is
report-only and explicitly keeps NPU out of the advisory lane.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from report_utils import resolve_output_path, write_json_report
except ImportError:
    from Tools.validation.report_utils import resolve_output_path, write_json_report  # type: ignore

EXPECTED_KIND = "local_ai_enrichment_plan"
REPORT_KIND = "local_ai_enrichment_plan_contract"
REQUIRED_STEP_IDS = {
    "read_contracts",
    "build_semantic_chunks",
    "select_semantic_chunks",
    "validate_selected_chunks",
    "build_context_pack",
    "build_agent_state",
    "validate_adapter_manifest",
    "validate_npu_broker_packet",
    "generate_manual_review_proposals",
}


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_repo_path(repo_root: Path, raw: str) -> Path:
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
    except OSError as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, f"expected JSON object, got {type(data).__name__}"
    return data, None


def validate_step(step: Any, index: int, known_ids: set[str]) -> dict[str, Any]:
    label = f"steps[{index}]"
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(step, dict):
        return {"id": label, "ok": False, "errors": ["step must be an object"], "warnings": []}
    sid = str(step.get("id") or "")
    if not sid:
        errors.append("id is required")
    for field in ("title", "tool_hint", "timing", "lane"):
        if not isinstance(step.get(field), str) or not step.get(field):
            errors.append(f"{field} is required")
    depends = step.get("depends_on")
    if not isinstance(depends, list):
        errors.append("depends_on must be a list")
        depends = []
    for dep in depends:
        if dep not in known_ids:
            errors.append(f"depends_on references unknown step: {dep}")
    outputs = step.get("outputs")
    if not isinstance(outputs, list):
        errors.append("outputs must be a list")
    for bool_field in ("provider_execution_required", "source_writes_performed", "patch_application_performed"):
        if step.get(bool_field) not in (True, False):
            errors.append(f"{bool_field} must be boolean")
    if step.get("source_writes_performed") is not False:
        errors.append("source_writes_performed must be false")
    if step.get("patch_application_performed") is not False:
        errors.append("patch_application_performed must be false")
    return {"id": sid or label, "ok": not errors, "errors": errors, "warnings": warnings}


def validate_plan(repo_root: Path, plan_path: Path) -> dict[str, Any]:
    rel_path = repo_relative(plan_path, repo_root)
    errors: list[str] = []
    warnings: list[str] = []
    data, parse_error = read_json_object(plan_path)
    if parse_error or data is None:
        return {"path": rel_path, "exists": plan_path.exists(), "json_ok": False, "ok": False, "errors": [parse_error or "unknown JSON parse error"], "warnings": warnings, "step_count": 0, "step_checks": []}

    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if data.get("kind") != EXPECTED_KIND:
        errors.append(f"kind must be {EXPECTED_KIND}")
    if data.get("apply_mode") != "report_only":
        errors.append("apply_mode must be report_only")
    if data.get("provider_execution_performed") is not False:
        errors.append("provider_execution_performed must be false")
    if data.get("source_writes_performed") is not False:
        errors.append("source_writes_performed must be false")
    if data.get("patch_application_performed") is not False:
        errors.append("patch_application_performed must be false")

    complexity = data.get("complexity")
    if not isinstance(complexity, dict):
        errors.append("complexity must be an object")
        complexity = {}
    level = complexity.get("level")
    if level not in {"low", "medium", "high"}:
        errors.append("complexity.level must be low, medium or high")

    lane_policy = data.get("lane_policy")
    if not isinstance(lane_policy, dict):
        errors.append("lane_policy must be an object")
        lane_policy = {}
    if lane_policy.get("primary_advisory_provider") != "ollama_gpu":
        errors.append("lane_policy.primary_advisory_provider must be ollama_gpu")
    if lane_policy.get("npu_role") != "knowledge_broker_context_oracle":
        errors.append("lane_policy.npu_role must be knowledge_broker_context_oracle")
    if lane_policy.get("npu_promoted_to_advisory") is not False:
        errors.append("lane_policy.npu_promoted_to_advisory must be false")
    if lane_policy.get("openvino_gpu_primary_lane") is not False:
        errors.append("lane_policy.openvino_gpu_primary_lane must be false")

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("steps must be a non-empty list")
        steps = []
    declared_step_count = data.get("step_count")
    if not isinstance(declared_step_count, int):
        errors.append("step_count must be an integer")
    elif declared_step_count != len(steps):
        errors.append("step_count must equal len(steps)")
    step_ids = {str(step.get("id")) for step in steps if isinstance(step, dict) and step.get("id")}
    missing_steps = sorted(REQUIRED_STEP_IDS - step_ids)
    if missing_steps:
        errors.append(f"missing required step ids: {', '.join(missing_steps)}")
    if len(step_ids) != len(steps):
        errors.append("step ids must be unique and present")

    step_checks = [validate_step(step, index, step_ids) for index, step in enumerate(steps)]
    for check in step_checks:
        for error in check.get("errors", []):
            errors.append(f"{check.get('id')}: {error}")
        for warning in check.get("warnings", []):
            warnings.append(f"{check.get('id')}: {warning}")

    step_by_id = {step.get("id"): step for step in steps if isinstance(step, dict)}
    if level in {"medium", "high"}:
        if "ollama_gpu_advisory_first" not in step_by_id:
            errors.append("medium/high complexity plans must include ollama_gpu_advisory_first")
        if "npu_knowledge_broker_after_gpu" not in step_by_id:
            errors.append("medium/high complexity plans must include npu_knowledge_broker_after_gpu")
        npu_step = step_by_id.get("npu_knowledge_broker_after_gpu", {})
        if isinstance(npu_step, dict) and "ollama_gpu_advisory_first" not in npu_step.get("depends_on", []):
            errors.append("npu_knowledge_broker_after_gpu must depend on ollama_gpu_advisory_first")
    if level == "low":
        if "npu_knowledge_broker_parallel" not in step_by_id:
            errors.append("low complexity plans must include npu_knowledge_broker_parallel")

    return {
        "path": rel_path,
        "exists": True,
        "json_ok": True,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "complexity_level": level,
        "step_count": len(steps),
        "step_checks": step_checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    plan_path = resolve_repo_path(repo_root, args.plan)
    result = validate_plan(repo_root, plan_path)
    errors = [f"{result['path']}: {error}" for error in result.get("errors", [])]
    warnings = [f"{result['path']}: {warning}" for warning in result.get("warnings", [])]
    report = {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "repo_root": repo_root.as_posix(),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "results": [result],
    }
    output = resolve_output_path(repo_root, args.output) if args.output else None
    print(write_json_report(report, output), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
