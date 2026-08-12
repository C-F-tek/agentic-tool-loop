#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve(repo_root: Path, value: str | None, stamp: str = "") -> Path | None:
    if not value:
        return None
    raw = str(value).format(stamp=stamp)
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def rel(repo_root: Path, path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path)


def load_json(path: Path | None) -> tuple[dict[str, Any] | None, str]:
    if path is None:
        return None, "not_configured"
    if not path.exists():
        return None, "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return None, f"invalid_json:{type(exc).__name__}: {exc}"
    if not isinstance(data, dict):
        return None, "json_not_object"
    return data, ""


def read_text(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def add_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def evidence_item(repo_root: Path, name: str, path: Path | None) -> dict[str, Any]:
    data, error = load_json(path)
    item: dict[str, Any] = {
        "name": name,
        "path": rel(repo_root, path),
        "exists": bool(path and path.exists()),
        "passed": None,
        "error": error,
    }
    if data is not None:
        for key in (
            "schema_version",
            "kind",
            "passed",
            "provider_execution_performed",
            "production_support",
            "production_role",
            "semantic_execution_mode",
            "selected_device",
            "iterations",
            "min_seconds",
            "elapsed_seconds",
            "classifications",
            "errors",
            "warnings",
            "companion_task_count",
            "tool_request_count",
            "gpu0_workload_passed",
        ):
            if key in data:
                item[key] = data.get(key)
    return item


def classify_gpu0_provider_support(data: dict[str, Any] | None, error: str, classifications: list[str], errors: list[str], warnings: list[str]) -> None:
    if data is None:
        add_unique(classifications, "gpu0_support_lane_not_integrated")
        errors.append(f"gpu0_provider_support_missing_or_unreadable: {error}")
        return
    if data.get("passed") is not True:
        add_unique(classifications, "gpu0_support_lane_not_integrated")
        errors.append("gpu0_provider_support_not_passed")
    if data.get("selected_device") != "GPU.0":
        add_unique(classifications, "gpu0_support_lane_not_integrated")
        errors.append(f"gpu0_provider_support_selected_device_not_gpu0: {data.get('selected_device')!r}")
    if data.get("production_support") is not True:
        add_unique(classifications, "gpu0_support_lane_not_integrated")
        errors.append("gpu0_provider_support_missing_production_support_true")
    if data.get("openvino_gpu0_workload_performed") is not True:
        add_unique(classifications, "gpu0_sustained_workload_not_performed")
        errors.append("gpu0_provider_support_workload_not_performed")
    if data.get("openvino_gpu0_workload_passed") is not True:
        add_unique(classifications, "gpu0_sustained_workload_not_performed")
        errors.append("gpu0_provider_support_workload_not_passed")
    if data.get("iterations") is None:
        add_unique(classifications, "gpu0_sustained_workload_not_performed")
        errors.append("gpu0_provider_support_missing_iterations")
    if data.get("min_seconds") is None:
        add_unique(classifications, "gpu0_sustained_workload_not_performed")
        errors.append("gpu0_provider_support_missing_min_seconds")
    elapsed = data.get("elapsed_seconds")
    min_seconds = data.get("min_seconds")
    try:
        if elapsed is not None and min_seconds is not None and float(elapsed) + 0.0001 < float(min_seconds):
            add_unique(classifications, "gpu0_sustained_workload_not_performed")
            errors.append(f"gpu0_provider_support_elapsed_lt_min_seconds: elapsed={elapsed} min_seconds={min_seconds}")
    except Exception as exc:
        warnings.append(f"could_not_compare_gpu0_elapsed_seconds: {type(exc).__name__}: {exc}")


def classify_gpu0_final_workload(data: dict[str, Any] | None, error: str, classifications: list[str], errors: list[str], warnings: list[str], *, required: bool) -> None:
    if data is None:
        msg = f"gpu0_final_workload_not_available_at_gate_time: {error}"
        if required:
            add_unique(classifications, "gpu0_final_workload_missing")
            errors.append(msg)
        else:
            warnings.append(msg)
        return
    if data.get("passed") is not True:
        add_unique(classifications, "gpu0_final_workload_failed")
        errors.append("gpu0_final_workload_not_passed")
    if data.get("selected_device") != "GPU.0":
        add_unique(classifications, "gpu0_final_workload_failed")
        errors.append(f"gpu0_final_workload_selected_device_not_gpu0: {data.get('selected_device')!r}")


def classify_gpu0_companion(data: dict[str, Any] | None, error: str, classifications: list[str], errors: list[str]) -> None:
    if data is None:
        add_unique(classifications, "gpu0_companion_lane_not_integrated")
        errors.append(f"gpu0_companion_lane_missing_or_unreadable: {error}")
        return
    if data.get("kind") != "gpu0_companion_worker_lane":
        add_unique(classifications, "gpu0_companion_lane_not_integrated")
        errors.append("gpu0_companion_invalid_kind")
    if data.get("passed") is not True:
        add_unique(classifications, "gpu0_companion_lane_failed")
        errors.append("gpu0_companion_report_not_passed")
    if data.get("production_role") != "companion_worker":
        add_unique(classifications, "gpu0_companion_lane_not_integrated")
        errors.append("gpu0_companion_role_not_companion_worker")
    if int(data.get("companion_task_count") or 0) <= 0:
        add_unique(classifications, "gpu0_companion_lane_not_integrated")
        errors.append("gpu0_companion_no_tasks")
    if int(data.get("tool_request_count") or 0) <= 0:
        add_unique(classifications, "gpu0_companion_lane_not_integrated")
        errors.append("gpu0_companion_no_tool_requests")
    if data.get("gpu0_workload_passed") is not True:
        add_unique(classifications, "gpu0_companion_lane_failed")
        errors.append("gpu0_companion_workload_not_passed")


def classify_evidence_sufficiency(data: dict[str, Any] | None, error: str, classifications: list[str], errors: list[str]) -> None:
    if data is None:
        add_unique(classifications, "blocked_missing_refined_review_input")
        errors.append(f"evidence_sufficiency_missing_or_unreadable: {error}")
        return
    if data.get("passed") is True:
        return
    for item in data.get("classifications") or []:
        add_unique(classifications, str(item))
    text = json.dumps(data, ensure_ascii=False)
    if "blocked_missing_refined_review_input" in text or "missing refined review" in text or "missing file" in text:
        add_unique(classifications, "blocked_missing_refined_review_input")
        errors.append("blocked_missing_refined_review_input: output/ai_pipeline/local_ai_core_tool_activation_megalithic_refined_review_v3.json")
    else:
        add_unique(classifications, "evidence_sufficiency_failed")
        errors.append("evidence_sufficiency_failed")


def classify_primary_provider_text(text: str, classifications: list[str], errors: list[str], warnings: list[str]) -> None:
    if not text.strip():
        warnings.append("repository_update_suggestions_markdown_missing_or_empty")
        return
    if "Primary advisory provider execution requested: False" in text:
        add_unique(classifications, "primary_advisory_not_executed")
        errors.append("primary_advisory_not_executed: repository_update_suggestions.md reports requested False")
    if "Ollama advisory execution used: False" in text:
        add_unique(classifications, "ollama_probe_failed")
        errors.append("ollama_probe_failed: repository_update_suggestions.md reports Ollama advisory execution used False")
    if "These reports are advisory only" in text and "Primary advisory provider execution requested: False" in text:
        add_unique(classifications, "provider_lane_degraded")


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Full0To10 Provider Acceptance Gate",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Stamp: `{report['stamp']}`",
        f"- Classifications: `{report['classifications']}`",
        "",
        "## Errors",
    ]
    lines.extend([f"- {item}" for item in report.get("errors") or []] or ["- none"])
    lines.append("")
    lines.append("## Warnings")
    lines.extend([f"- {item}" for item in report.get("warnings") or []] or ["- none"])
    lines.append("")
    lines.append("## Evidence")
    for item in report.get("evidence", []):
        lines.append(f"- `{item['name']}` exists=`{item.get('exists')}` passed=`{item.get('passed')}` path=`{item.get('path')}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--stamp", required=True)
    parser.add_argument("--gpu0-provider-support", default="")
    parser.add_argument("--gpu0-final-workload", default="")
    parser.add_argument("--gpu0-companion-lane", default="output/validation/gpu0_companion_task_lane_{stamp}.json")
    parser.add_argument("--evidence-sufficiency", default="output/ai_pipeline/agent_review_evidence_sufficiency.json")
    parser.add_argument("--repository-suggestions-md", default="output/ai_pipeline/repository_update_suggestions.md")
    parser.add_argument("--workload-quality", default="output/validation/ai_workload_quality_lane_routing.json")
    parser.add_argument("--require-final-workload", action="store_true")
    parser.add_argument("--output", default="")
    parser.add_argument("--markdown-output", default="")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output = resolve(repo_root, args.output or f"output/validation/full0to10_provider_acceptance_{args.stamp}.json", args.stamp)
    markdown_output = resolve(repo_root, args.markdown_output or f"output/validation/full0to10_provider_acceptance_{args.stamp}.md", args.stamp)

    gpu0_provider_path = resolve(repo_root, args.gpu0_provider_support or f"output/validation/openvino_gpu0_provider_support_{args.stamp}.json", args.stamp)
    gpu0_final_path = resolve(repo_root, args.gpu0_final_workload or f"output/validation/openvino_gpu0_workload_{args.stamp}.json", args.stamp)
    gpu0_companion_path = resolve(repo_root, args.gpu0_companion_lane, args.stamp)
    evidence_path = resolve(repo_root, args.evidence_sufficiency, args.stamp)
    suggestions_md_path = resolve(repo_root, args.repository_suggestions_md, args.stamp)
    workload_quality_path = resolve(repo_root, args.workload_quality, args.stamp)

    gpu0_provider, gpu0_provider_error = load_json(gpu0_provider_path)
    gpu0_final, gpu0_final_error = load_json(gpu0_final_path)
    gpu0_companion, gpu0_companion_error = load_json(gpu0_companion_path)
    evidence_sufficiency, evidence_error = load_json(evidence_path)
    workload_quality, workload_error = load_json(workload_quality_path)
    suggestions_text = read_text(suggestions_md_path)

    classifications: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []

    classify_gpu0_provider_support(gpu0_provider, gpu0_provider_error, classifications, errors, warnings)
    classify_gpu0_final_workload(gpu0_final, gpu0_final_error, classifications, errors, warnings, required=bool(args.require_final_workload))
    classify_gpu0_companion(gpu0_companion, gpu0_companion_error, classifications, errors)
    classify_evidence_sufficiency(evidence_sufficiency, evidence_error, classifications, errors)
    classify_primary_provider_text(suggestions_text, classifications, errors, warnings)

    if workload_quality is None:
        warnings.append(f"workload_quality_missing_or_unreadable: {workload_error}")
    elif workload_quality.get("passed") is False:
        add_unique(classifications, "provider_lane_degraded")
        errors.append("workload_quality_failed")

    evidence = [
        evidence_item(repo_root, "gpu0_provider_support", gpu0_provider_path),
        evidence_item(repo_root, "gpu0_final_workload", gpu0_final_path),
        evidence_item(repo_root, "gpu0_companion_lane", gpu0_companion_path),
        evidence_item(repo_root, "evidence_sufficiency", evidence_path),
        evidence_item(repo_root, "workload_quality", workload_quality_path),
    ]

    report = {
        "schema_version": 4,
        "kind": "full0to10_provider_acceptance_gate",
        "generated_at": now_iso(),
        "stamp": args.stamp,
        "repo_root": str(repo_root),
        "passed": not classifications,
        "classifications": classifications,
        "errors": errors,
        "warnings": warnings,
        "evidence": evidence,
        "primary_advisory_markdown": rel(repo_root, suggestions_md_path),
        "provider_execution_performed": bool(gpu0_provider and gpu0_provider.get("provider_execution_performed") is True),
        "patch_application_performed": False,
        "source_writes_performed": False,
        "guardrails": {
            "report_only": True,
            "acceptance_requires_empty_classifications": True,
            "gpu0_peer_worker_required": True,
            "companion_evidence_required": True,
        },
    }

    assert output is not None
    assert markdown_output is not None
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "classifications": classifications, "evidence_names": [item["name"] for item in evidence], "output": str(output), "markdown": str(markdown_output)}, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
