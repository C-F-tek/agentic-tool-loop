#!/usr/bin/env python3
"""Helpers for report-only code edit proposals.

This module models complete code-edit proposals without applying them. It is
intended to support future code-editor lanes where an AI can describe a precise
source edit, validators and stop conditions while preserving manual review.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[2]
if str(REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORTS))

from Tools.ai.code_patch_plan_common import (  # noqa: E402
    compact_text,
    normalize_repo_path,
    target_path_errors,
)
from Tools.ai.github_evidence_bundle_io import line_count, read_text, sha256_file  # noqa: E402

EDIT_KIND_STRUCTURED = "structured_edit"
EDIT_KIND_UNIFIED_DIFF = "unified_diff"
EDIT_KIND_NOOP = "no_op"
ALLOWED_EDIT_KINDS = {EDIT_KIND_STRUCTURED, EDIT_KIND_UNIFIED_DIFF, EDIT_KIND_NOOP}
MAX_PROPOSAL_TEXT_CHARS = 12000
MAX_SNIPPET_CHARS = 4000
FORBIDDEN_DIFF_FRAGMENTS = ("output/", "renders/", ".sqlite", ".db", "full_analysis", "analysis_full")
DEFAULT_CODE_STOP_CONDITIONS = [
    "Stop if the target file changed since the proposal was generated.",
    "Stop if the edit touches output/**, generated indexes, full analysis JSON, SQLite, secrets, permissions, billing, or repository visibility.",
    "Stop if the edit requires provider execution, Blender runtime execution, deployment, or patch auto-apply.",
    "Stop if any validation command fails.",
]
DEFAULT_CODE_VALIDATION_COMMANDS = [
    "python .\\Tools\\validation\\check_python_syntax.py --repo-root . --output .\\output\\validation\\python_syntax.json",
    "python .\\Tools\\validation\\check_validation_report_contract.py --repo-root . --output .\\output\\validation\\validation_report_contract.json",
    "git diff --check",
]


def physical_line_count(path: Path) -> int | None:
    """Return physical line count for an existing text file."""
    if not path.is_file():
        return None
    text, error = read_text(path)
    return None if error else line_count(text)


def default_validation_commands_for(path_value: str) -> list[str]:
    """Return default validators for a target file."""
    commands = list(DEFAULT_CODE_VALIDATION_COMMANDS)
    if Path(path_value).suffix.lower() == ".py":
        ps_path = path_value.replace("/", "\\")
        commands.insert(0, f"python -m py_compile .\\{ps_path}")
    return commands


def target_metadata(repo_root: Path, path_value: str) -> dict[str, Any]:
    """Build stable metadata for a code-edit target."""
    normalized = normalize_repo_path(path_value)
    full = repo_root / normalized
    return {
        "path": normalized,
        "exists": full.is_file(),
        "sha256": sha256_file(full),
        "line_count": physical_line_count(full),
        "suffix": full.suffix.lower(),
    }


def validate_edit_kind(edit_kind: str) -> list[str]:
    """Validate edit kind."""
    return [] if edit_kind in ALLOWED_EDIT_KINDS else [f"unsupported edit kind: {edit_kind}"]


def forbidden_diff_fragment_errors(diff_text: str) -> list[str]:
    """Return forbidden-fragment errors for a normalized diff body."""
    lower = diff_text.lower().replace("\\", "/")
    return [f"unified diff references forbidden fragment: {fragment}" for fragment in FORBIDDEN_DIFF_FRAGMENTS if fragment in lower]


def validate_unified_diff_text(diff_text: str, target_file: str) -> list[str]:
    """Validate a proposed unified diff without applying it."""
    errors: list[str] = []
    if not diff_text.strip():
        return errors
    if len(diff_text) > MAX_PROPOSAL_TEXT_CHARS:
        errors.append(f"unified diff exceeds max chars: {len(diff_text)} > {MAX_PROPOSAL_TEXT_CHARS}")
    normalized_target = normalize_repo_path(target_file)
    required_markers = ("--- ", "+++ ", "@@")
    for marker in required_markers:
        if marker not in diff_text:
            errors.append(f"unified diff missing marker: {marker.strip()}")
    errors.extend(forbidden_diff_fragment_errors(diff_text))
    if normalized_target and normalized_target not in diff_text.lower().replace("\\", "/"):
        errors.append("unified diff does not reference the normalized target file")
    return errors


def normalize_structured_operations(operations: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """Normalize structured edit operations for report metadata."""
    if operations is None:
        return [], []
    if not isinstance(operations, list):
        return [], ["structured operations must be a list"]

    normalized: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, item in enumerate(operations, start=1):
        if not isinstance(item, dict):
            errors.append(f"operation {index}: must be an object")
            continue
        operation = str(item.get("operation") or "").strip()
        if operation not in {"replace", "insert_after", "insert_before", "delete", "append"}:
            errors.append(f"operation {index}: unsupported operation `{operation}`")
        normalized.append(
            {
                "operation": operation,
                "anchor": compact_text(item.get("anchor"), MAX_SNIPPET_CHARS),
                "replacement": compact_text(item.get("replacement"), MAX_SNIPPET_CHARS),
                "rationale": compact_text(item.get("rationale"), 1000),
            }
        )
    return normalized, errors


def build_code_edit_proposal(
    repo_root: Path,
    *,
    proposal_id: str,
    target_file: str,
    rationale: str,
    edit_strategy: str,
    edit_kind: str = EDIT_KIND_NOOP,
    unified_diff: str = "",
    structured_operations: Any = None,
    validation_commands: list[str] | None = None,
    stop_conditions: list[str] | None = None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Build one complete report-only code edit proposal.

    The returned proposal is metadata only. No file content is modified.
    """
    normalized_target = normalize_repo_path(target_file)
    errors = target_path_errors(repo_root, normalized_target)
    errors.extend(validate_edit_kind(edit_kind))
    warnings: list[str] = []

    operations, operation_errors = normalize_structured_operations(structured_operations)
    errors.extend(operation_errors)
    if edit_kind == EDIT_KIND_UNIFIED_DIFF:
        errors.extend(validate_unified_diff_text(unified_diff, normalized_target))
    if edit_kind == EDIT_KIND_STRUCTURED and not operations:
        errors.append("structured edit kind requires at least one operation")
    if edit_kind == EDIT_KIND_NOOP and (unified_diff.strip() or operations):
        warnings.append("no_op proposal contains edit content that will remain advisory only")

    commands = validation_commands or default_validation_commands_for(normalized_target)
    stops = stop_conditions or list(DEFAULT_CODE_STOP_CONDITIONS)
    proposal = {
        "id": proposal_id,
        "kind": "code_edit_proposal",
        "apply_mode": "report_only_manual_review_code_edit_proposal",
        "manual_review_required": True,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "target_file": normalized_target,
        "target_metadata": target_metadata(repo_root, normalized_target),
        "edit_kind": edit_kind,
        "rationale": compact_text(rationale, 2000),
        "edit_strategy": compact_text(edit_strategy, 2000),
        "unified_diff": compact_text(unified_diff, MAX_PROPOSAL_TEXT_CHARS),
        "structured_operations": operations,
        "validation_commands": commands,
        "stop_conditions": stops,
        "ready_for_manual_review": not errors,
    }
    return proposal, errors, warnings


def proposal_summary(proposal: dict[str, Any]) -> dict[str, Any]:
    """Return compact summary for evidence bundles."""
    metadata = proposal.get("target_metadata") if isinstance(proposal.get("target_metadata"), dict) else {}
    return {
        "id": proposal.get("id"),
        "target_file": proposal.get("target_file"),
        "edit_kind": proposal.get("edit_kind"),
        "manual_review_required": proposal.get("manual_review_required"),
        "ready_for_manual_review": proposal.get("ready_for_manual_review"),
        "target_sha256": metadata.get("sha256"),
        "target_line_count": metadata.get("line_count"),
        "rationale": compact_text(proposal.get("rationale"), 1000),
        "edit_strategy": compact_text(proposal.get("edit_strategy"), 1000),
        "validation_commands": proposal.get("validation_commands", []),
        "stop_conditions": proposal.get("stop_conditions", []),
    }
