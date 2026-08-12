#!/usr/bin/env python3
"""Validate the full-context golden-path documentation contract.

This validator is intentionally docs-only and report-only. It verifies that the
repository keeps a stable full-context golden-path contract across the task
entrypoint, bootstrap, local workflow docs and the dedicated P3 contract doc.
It does not run providers, build context packs, apply patches, invoke Blender or
read ignored runtime outputs.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

try:
    from report_utils import resolve_output_path, write_json_report
except ImportError:
    from Tools.validation.report_utils import resolve_output_path, write_json_report  # type: ignore


REPORT_KIND = "full_context_golden_docs_contract_validation"

REQUIRED_DOCS = (
    "AGENTS.md",
    "docs/LOCAL_AI_RUN_BOOTSTRAP.md",
    "docs/LOCAL_AI_WORKFLOW.md",
    "docs/LOCAL_AI_TASKS/README.md",
    "docs/LOCAL_AI_TASKS/full-context-ai-npu-golden-path.md",
    "docs/LOCAL_AI_TASKS/full-context-golden-docs-contract.md",
    "docs/JSON_SCHEMAS.md",
)

TASK_REQUIRED_TERMS = (
    "report-only",
    "proposal-only",
    "manual-review-only",
    "no automatic patch apply",
    "Provider execution is allowed only when explicitly requested by wrapper flags.",
    "NPU knowledge-broker concept",
    "Ollama/GPU",
    "OpenVINO/NPU",
    "selected chunks validator/evidence",
    "SQLite-backed agent state packet",
)

BOOTSTRAP_REQUIRED_TERMS = (
    "A local AI runner started from a task file must still read `AGENTS.md` first",
    "docs/LOCAL_AI_TASKS/full-context-ai-npu-golden-path.md",
    "Do not execute Ollama/OpenVINO/GPU/NPU providers implicitly.",
    "Provider execution is valid only with explicit local commands",
    "branch name",
    "validators run",
)

WORKFLOW_REQUIRED_TERMS = (
    "Ollama -> GPU/CUDA -> primary advisory provider",
    "OpenVINO -> NPU -> probe / guardrail / decode diagnostic",
    "report-only/proposal-only by default",
    "Selected semantic chunks belong under ignored `output/ai_context_packs/`",
    "compact selected-chunks evidence may be committed under `docs/LOCAL_VALIDATION_EVIDENCE/`",
)

CONTRACT_DOC_REQUIRED_TERMS = (
    "Full-Context Golden Docs Contract",
    "P3",
    "docs-only",
    "report-only",
    "provider execution explicit-only",
    "no automatic patch apply",
    "Ollama/GPU remains primary advisory",
    "NPU remains knowledge broker",
    "OpenVINO GPU must not become primary lane",
    "Validation command",
)

FORBIDDEN_DOC_TERMS = (
    "NPU as primary advisory",
    "OpenVINO GPU primary lane",
    "automatic patch apply is allowed",
    "provider execution by default",
)

P_FAMILIES = ("P1", "P2", "P3", "P4", "P5", "P6")


def read_text(path: Path) -> tuple[str, str | None]:
    try:
        return path.read_text(encoding="utf-8-sig"), None
    except OSError as exc:
        return "", str(exc)


def check_file_exists(repo_root: Path, rel_path: str) -> dict[str, Any]:
    path = repo_root / rel_path
    return {
        "path": rel_path,
        "exists": path.exists(),
        "ok": path.is_file(),
        "errors": [] if path.is_file() else ["required file is missing"],
        "warnings": [],
    }


def check_terms(repo_root: Path, rel_path: str, required_terms: tuple[str, ...]) -> dict[str, Any]:
    path = repo_root / rel_path
    text, error = read_text(path)
    errors: list[str] = []
    warnings: list[str] = []
    if error:
        errors.append(error)
    missing = [term for term in required_terms if term not in text]
    if missing:
        errors.extend(f"missing required term: {term}" for term in missing)

    forbidden = [term for term in FORBIDDEN_DOC_TERMS if term in text]
    if forbidden:
        errors.extend(f"forbidden term present: {term}" for term in forbidden)

    return {
        "path": rel_path,
        "exists": path.exists(),
        "ok": not errors,
        "checked_terms": len(required_terms),
        "missing_terms": missing,
        "forbidden_terms": forbidden,
        "errors": errors,
        "warnings": warnings,
    }


def check_p_family_coverage(repo_root: Path) -> dict[str, Any]:
    rel_paths = (
        "docs/LOCAL_AI_TASKS/full-context-ai-npu-golden-path.md",
        "docs/LOCAL_AI_TASKS/full-context-golden-docs-contract.md",
    )
    texts: list[str] = []
    errors: list[str] = []
    for rel_path in rel_paths:
        text, error = read_text(repo_root / rel_path)
        if error:
            errors.append(f"{rel_path}: {error}")
        texts.append(text)
    combined = "\n".join(texts)
    coverage = {family: family in combined for family in P_FAMILIES}
    missing = [family for family, present in coverage.items() if not present]
    if missing:
        errors.append(f"missing proposal families: {', '.join(missing)}")
    return {
        "path": "full_context_golden_p_family_coverage",
        "ok": not errors,
        "coverage": coverage,
        "errors": errors,
        "warnings": [],
    }


def check_command_alignment(repo_root: Path) -> dict[str, Any]:
    """Check the dedicated contract exposes the safe preset and guardrails."""

    rel_path = "docs/LOCAL_AI_TASKS/full-context-golden-docs-contract.md"
    text, error = read_text(repo_root / rel_path)
    errors: list[str] = []
    warnings: list[str] = []
    if error:
        errors.append(error)
        flags: dict[str, bool] = {}
    else:
        lower = text.lower()
        flags = {
            "mentions_full_context_preset": "-FullContextGoldenPath" in text,
            "mentions_provider_explicit": "provider execution explicit-only" in lower,
            "mentions_no_patch_apply": "no automatic patch apply" in lower,
            "mentions_no_blender_runtime": "blender runtime" in lower,
        }
        for key, present in flags.items():
            if not present:
                errors.append(f"missing contract flag: {key}")

    return {
        "path": rel_path,
        "ok": not errors,
        "details": flags,
        "errors": errors,
        "warnings": warnings,
    }


def check_bootstrap_duplicate_index(repo_root: Path) -> dict[str, Any]:
    rel_path = "docs/LOCAL_AI_RUN_BOOTSTRAP.md"
    text, error = read_text(repo_root / rel_path)
    errors: list[str] = []
    warnings: list[str] = []
    if error:
        errors.append(error)
        line_count = 0
    else:
        line_count = text.count("Current task index:")
        if line_count > 1:
            warnings.append("Current task index block is duplicated; keep one block in a future docs cleanup")
    return {
        "path": rel_path,
        "ok": not errors,
        "current_task_index_count": line_count,
        "errors": errors,
        "warnings": warnings,
    }


def validate_docs_contract(repo_root: Path) -> dict[str, Any]:
    file_checks = [check_file_exists(repo_root, rel_path) for rel_path in REQUIRED_DOCS]
    term_checks = [
        check_terms(repo_root, "docs/LOCAL_AI_TASKS/full-context-ai-npu-golden-path.md", TASK_REQUIRED_TERMS),
        check_terms(repo_root, "docs/LOCAL_AI_RUN_BOOTSTRAP.md", BOOTSTRAP_REQUIRED_TERMS),
        check_terms(repo_root, "docs/LOCAL_AI_WORKFLOW.md", WORKFLOW_REQUIRED_TERMS),
        check_terms(repo_root, "docs/LOCAL_AI_TASKS/full-context-golden-docs-contract.md", CONTRACT_DOC_REQUIRED_TERMS),
    ]
    consistency_checks = [
        check_p_family_coverage(repo_root),
        check_command_alignment(repo_root),
        check_bootstrap_duplicate_index(repo_root),
    ]

    all_checks = file_checks + term_checks + consistency_checks
    errors = [
        f"{check['path']}: {error}"
        for check in all_checks
        for error in check.get("errors", [])
    ]
    warnings = [
        f"{check['path']}: {warning}"
        for check in all_checks
        for warning in check.get("warnings", [])
    ]

    return {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "repo_root": repo_root.as_posix(),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "file_checks": file_checks,
        "term_checks": term_checks,
        "consistency_checks": consistency_checks,
        "guardrails": {
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "blender_runtime_touched": False,
            "npu_promoted_to_advisory": False,
            "openvino_gpu_primary_lane": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = validate_docs_contract(repo_root)
    output = resolve_output_path(repo_root, args.output) if args.output else None
    print(write_json_report(report, output), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
