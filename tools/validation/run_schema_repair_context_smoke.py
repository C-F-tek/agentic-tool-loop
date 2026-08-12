#!/usr/bin/env python3
"""Smoke-test schema-repair provider context."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.ai.schema_repair_context import (
        SCHEMA_REPAIR_CONTEXT_KIND,
        build_schema_repair_context_stack,
    )
except ImportError:
    import sys

    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.schema_repair_context import (  # type: ignore
        SCHEMA_REPAIR_CONTEXT_KIND,
        build_schema_repair_context_stack,
    )


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Schema Repair Context Smoke", ""]
    for key in (
        "passed",
        "case_count",
        "failed_case_count",
        "schema_repair_context_count",
        "runtime_tool_evidence_count",
        "provider_execution_performed",
        "patch_application_performed",
        "sqlite_write_performed",
        "persistent_memory_write_performed",
    ):
        lines.append(f"- `{key}`: `{report.get(key)}`")
    if report.get("errors"):
        lines.append("")
        lines.append("## Errors")
        for error in report["errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/validation/schema_repair_context_smoke.json")
    parser.add_argument("--markdown-output", default="output/validation/schema_repair_context_smoke.md")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    base_context_reports = [
        {
            "kind": "runtime_tool_feedback_context",
            "source": "provider_tool_requests",
            "round": 1,
            "passed": True,
            "summary": {
                "tool_execution_count": 4,
                "failed_tool_count": 0,
                "blocked_tool_count": 0,
            },
            "tool_results": [
                {
                    "id": "syntax",
                    "tool": "check_python_syntax",
                    "executed": True,
                    "blocked": False,
                    "returncode": 0,
                    "summary": {"passed": True, "checked_count": 298, "failed_count": 0},
                    "outputs": {"json_report": "output/validation/python_syntax.json"},
                }
            ],
        }
    ]
    rounds = [
        {
            "round": 1,
            "json_ok": True,
            "schema_ok": False,
            "model_output_schema_mismatch": True,
            "empty_recommendations_reason": "model_output_schema_mismatch",
            "schema_errors": ["missing top-level keys: recommendations"],
        }
    ]

    stack = build_schema_repair_context_stack(
        base_context_reports=base_context_reports,
        rounds=rounds,
        evidence_ready_for_manual_patch_count=12,
        provider="gpu_ollama",
    )
    repair_reports = [item for item in stack if isinstance(item, dict) and item.get("kind") == SCHEMA_REPAIR_CONTEXT_KIND]
    errors: list[str] = []
    if len(repair_reports) != 1:
        errors.append(f"expected exactly one schema repair report, got {len(repair_reports)}")
    repair = repair_reports[0] if repair_reports else {}
    directive = repair.get("directive", {}) if isinstance(repair.get("directive"), dict) else {}
    if repair.get("runtime_tool_evidence_count") != 1:
        errors.append("runtime tool evidence count was not preserved")
    if "recommendations" not in directive.get("required_top_level_keys", []):
        errors.append("required_top_level_keys does not include recommendations")
    if not repair.get("decision", {}).get("schema_repair_required"):
        errors.append("schema repair required decision missing")
    if repair.get("guardrails", {}).get("patch_application_performed") is not False:
        errors.append("patch application guardrail not false")

    report = {
        "schema_version": 1,
        "kind": "schema_repair_context_smoke",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "case_count": 1,
        "failed_case_count": 1 if errors else 0,
        "errors": errors,
        "warnings": [],
        "schema_repair_context_count": len(repair_reports),
        "runtime_tool_evidence_count": repair.get("runtime_tool_evidence_count"),
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "blender_runtime_touched": False,
        "git_write_performed": False,
        "context_stack": stack,
        "guardrails": {
            "report_only": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "sqlite_write_performed": False,
            "persistent_memory_write_performed": False,
        },
    }

    output = resolve_path(repo_root, args.output)
    markdown = resolve_path(repo_root, args.markdown_output)
    write_json(output, report)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "output": str(output), "markdown": str(markdown)}, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
