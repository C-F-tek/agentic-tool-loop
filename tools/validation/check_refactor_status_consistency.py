#!/usr/bin/env python3
"""Check consistency of AI pipeline refactor status documentation.

This validator is intentionally lightweight. It verifies that the machine-readable
status marker and the primary Markdown documents agree on the current pipeline
state and point to the same core files.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

EXPECTED_STATUS = "modular_schedule_complete_pending_local_validation"
EXPECTED_ENTRYPOINT = "Tools/ai/run_parallel_artifact_pipeline.py"
EXPECTED_STATUS_FILE = "Tools/ai/pipeline/refactor_status.py"
EXPECTED_DOCS = (
    "docs/AI_PIPELINE_REFACTOR_STATUS.md",
    "docs/AI_PIPELINE_ARCHITECTURE.md",
    "docs/PROJECT_AI_CONSCIOUSNESS.md",
    "AGENTS.md",
)
EXPECTED_MODULES = (
    "Tools/ai/pipeline/defaults.py",
    "Tools/ai/pipeline/models.py",
    "Tools/ai/pipeline/runner.py",
    "Tools/ai/pipeline/compat.py",
    "Tools/ai/pipeline/artifact_contracts.py",
    "Tools/ai/pipeline/cli.py",
    "Tools/ai/pipeline/preflight.py",
    "Tools/ai/pipeline/steps.py",
    "Tools/ai/pipeline/scheduler.py",
    "Tools/ai/pipeline/orchestrator.py",
    "Tools/ai/pipeline/schema_report.py",
    "Tools/ai/pipeline/markdown_report.py",
    "Tools/ai/pipeline/guardrail_models.py",
    "Tools/ai/pipeline/remediation.py",
    "Tools/ai/pipeline/refactor_status.py",
)


def load_status_module(repo_root: Path) -> dict[str, Any]:
    path = repo_root / EXPECTED_STATUS_FILE
    spec = importlib.util.spec_from_file_location("pipeline_refactor_status", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    status_func = getattr(module, "get_pipeline_refactor_status", None)
    if not callable(status_func):
        raise RuntimeError("get_pipeline_refactor_status is missing or not callable")
    payload = status_func()
    if not isinstance(payload, dict):
        raise RuntimeError("get_pipeline_refactor_status did not return a dict")
    return payload


def read_text(repo_root: Path, rel_path: str) -> str:
    return (repo_root / rel_path).read_text(encoding="utf-8", errors="replace")


def check_contains(text: str, needles: tuple[str, ...]) -> list[str]:
    return [needle for needle in needles if needle not in text]


def check_status(repo_root: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}

    try:
        status = load_status_module(repo_root)
    except Exception as exc:
        return {
            "schema_version": 1,
            "kind": "refactor_status_consistency",
            "repo_root": str(repo_root),
            "passed": False,
            "errors": [f"failed to load status module: {type(exc).__name__}: {exc}"],
            "warnings": warnings,
            "checks": checks,
        }

    checks["status"] = status.get("status")
    checks["entrypoint"] = status.get("entrypoint")
    checks["schema_version"] = status.get("schema_version")
    checks["local_validation_required"] = status.get("local_validation_required")
    checks["module_count"] = len(status.get("modules") or [])

    if status.get("status") != EXPECTED_STATUS:
        errors.append(f"status mismatch: expected {EXPECTED_STATUS}, got {status.get('status')}")
    if status.get("entrypoint") != EXPECTED_ENTRYPOINT:
        errors.append(f"entrypoint mismatch: expected {EXPECTED_ENTRYPOINT}, got {status.get('entrypoint')}")
    if status.get("schema_version") != 6:
        errors.append(f"schema_version mismatch: expected 6, got {status.get('schema_version')}")

    modules = tuple(status.get("modules") or [])
    for module_path in EXPECTED_MODULES:
        if module_path not in modules:
            errors.append(f"status module list missing {module_path}")
        if not (repo_root / module_path).exists():
            errors.append(f"expected module file missing: {module_path}")

    for doc in EXPECTED_DOCS:
        doc_path = repo_root / doc
        if not doc_path.exists():
            errors.append(f"expected document missing: {doc}")
            continue
        text = read_text(repo_root, doc)
        missing = check_contains(text, (EXPECTED_STATUS_FILE, "AI_PIPELINE_ARCHITECTURE.md"))
        if EXPECTED_STATUS not in text:
            warnings.append(f"{doc} does not include exact status marker {EXPECTED_STATUS}")
        for needle in missing:
            warnings.append(f"{doc} does not include {needle}")

    return {
        "schema_version": 1,
        "kind": "refactor_status_consistency",
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = check_status(repo_root)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
