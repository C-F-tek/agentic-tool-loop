#!/usr/bin/env python3
"""Smoke-test deterministic recommendation synthesis from evidence."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

try:
    from Tools.ai.build_deterministic_recommendations import build_recommendation_report, render_markdown
    from Tools.ai.gpu_planner_json_contract import validate_recommendation_object
    from Tools.validation.report_utils import write_json_report, write_text_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.build_deterministic_recommendations import build_recommendation_report, render_markdown  # type: ignore
    from Tools.ai.gpu_planner_json_contract import validate_recommendation_object  # type: ignore
    from Tools.validation.report_utils import write_json_report, write_text_report  # type: ignore


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve(strict=False)


def write_fixture(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_fixture_reports(repo_root: Path, work_dir: Path) -> tuple[Path, Path, Path]:
    evidence = {
        "schema_version": 1,
        "kind": "agent_review_evidence_sufficiency",
        "passed": True,
        "decision": {
            "ready_for_manual_patch_count": 1,
            "sufficient_for_real_pr": True,
        },
        "areas": {
            "doc_code": {
                "items": [
                    {
                        "doc": "AGENTS.md",
                        "reference": "Tools/ai/build_deterministic_recommendations.py",
                        "existing_candidate": "Tools/ai/build_agent_review_patch_plan.py",
                        "candidate_references": [
                            "Tools/ai/build_agent_review_patch_plan.py",
                            "Tools/ai/gpu_planner_json_contract.py",
                        ],
                        "reason": "The documentation points at a recommendation lane that must be normalized before patch-plan construction.",
                        "confidence": "high",
                        "evidence_sufficient": True,
                        "evidence_files": [
                            {
                                "path": "AGENTS.md",
                                "exists": True,
                                "kind": "markdown",
                                "matched_terms": ["manual-review", "evidence"],
                            }
                        ],
                    }
                ]
            }
        },
    }
    orchestrator = {
        "schema_version": 1,
        "kind": "agent_gpu_npu_parallel_orchestrator",
        "passed": False,
        "gpu_output": str((work_dir / "gpu.json").relative_to(repo_root)),
        "gpu_empty_recommendations_reason": "json_parse_failure",
        "npu_audits": [
            {
                "round": 3,
                "status": "success",
                "classification": "usable_audit_text",
                "runtime_tool_context_seen": True,
                "npu_tool_request_count": 4,
                "npu_runtime_tool_execution_count": 4,
                "npu_runtime_tool_failed_count": 0,
                "npu_runtime_tool_blocked_count": 0,
            }
        ],
    }
    gpu = {
        "schema_version": 1,
        "kind": "agent_gpu_deep_planning_supervised",
        "passed": False,
        "recommendation_count": 0,
        "recommendations": [],
        "empty_recommendations_reason": "json_parse_failure",
        "evidence_ready_for_manual_patch_count": 1,
    }
    evidence_path = work_dir / "evidence.json"
    orchestrator_path = work_dir / "orchestrator.json"
    gpu_path = work_dir / "gpu.json"
    write_fixture(evidence_path, evidence)
    write_fixture(orchestrator_path, orchestrator)
    write_fixture(gpu_path, gpu)
    return evidence_path, orchestrator_path, gpu_path


def run_smoke(repo_root: Path) -> dict[str, Any]:
    work_dir = repo_root / "output" / "validation" / "deterministic_recommendation_synthesizer_smoke"
    evidence_path, orchestrator_path, gpu_path = build_fixture_reports(repo_root, work_dir)
    args = SimpleNamespace(
        repo_root=str(repo_root),
        evidence=str(evidence_path),
        orchestrator=str(orchestrator_path),
        gpu_report=str(gpu_path),
        tool_report=[],
        max_recommendations=4,
    )
    synthesized = build_recommendation_report(args)
    recommendations = synthesized.get("recommendations", [])
    schema_errors: list[str] = []
    for index, rec in enumerate(recommendations):
        schema_errors.extend(validate_recommendation_object(rec, index))

    expected_passed = (
        synthesized.get("passed") is True
        and synthesized.get("recommendation_count") == 1
        and synthesized.get("decision", {}).get("deterministic_synthesizer_used") is True
        and synthesized.get("next_best_action") == "build_agent_review_patch_plan.py"
        and not schema_errors
        and synthesized.get("provider_execution_performed") is False
        and synthesized.get("patch_application_performed") is False
    )
    return {
        "schema_version": 1,
        "kind": "deterministic_recommendation_synthesizer_smoke",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": expected_passed,
        "errors": schema_errors if schema_errors else ([] if expected_passed else ["deterministic synthesizer smoke assertions failed"]),
        "warnings": synthesized.get("warnings", []),
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "blender_runtime_execution_performed": False,
        "sqlite_write_performed": False,
        "manual_review_required": True,
        "recommendation_count": synthesized.get("recommendation_count"),
        "deterministic_synthesizer_used": synthesized.get("decision", {}).get("deterministic_synthesizer_used"),
        "next_best_action": synthesized.get("next_best_action"),
        "synthesized_report": synthesized,
    }


def render_smoke_markdown(report: dict[str, Any]) -> str:
    lines = ["# Deterministic Recommendation Synthesizer Smoke", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Recommendation count: `{report.get('recommendation_count')}`")
    lines.append(f"- Deterministic synthesizer used: `{report.get('deterministic_synthesizer_used')}`")
    lines.append(f"- Next best action: `{report.get('next_best_action')}`")
    lines.append(f"- Patch application performed: `{report.get('patch_application_performed')}`")
    lines.append("")
    lines.append("## Synthesized report preview")
    lines.append("")
    lines.append(render_markdown(report["synthesized_report"]))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/validation/deterministic_recommendation_synthesizer_smoke.json")
    parser.add_argument("--markdown-output", default="output/validation/deterministic_recommendation_synthesizer_smoke.md")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = run_smoke(repo_root)
    output = resolve_path(repo_root, args.output)
    markdown_output = resolve_path(repo_root, args.markdown_output)
    write_json_report(report, output)
    write_text_report(render_smoke_markdown(report), markdown_output)
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown_output),
                "recommendation_count": report["recommendation_count"],
                "deterministic_synthesizer_used": report["deterministic_synthesizer_used"],
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
