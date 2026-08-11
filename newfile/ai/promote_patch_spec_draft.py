#!/usr/bin/env python3
"""Promote a draft patch spec into a reviewed dry-run-passing spec.

This tool is intentionally non-mutating. It combines a proposal-derived draft
spec with an explicit replacement plan, dry-runs the resulting patch spec, and
writes the reviewed spec under output/ by default.
"""
from __future__ import annotations

import argparse
import copy
import importlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT_DIR = "output/patch_specs"
DEFAULT_BASENAME = "reviewed_patch_spec"
EXPECTED_DRAFT_KIND = "proposal_patch_spec_draft"
EXPECTED_PLAN_KIND = "patch_spec_replacement_plan"
REVIEWED_SPEC_KIND = "reviewed_patch_spec"
REVIEWED_MANIFEST_KIND = "reviewed_patch_spec_manifest"
EXPECTED_APPLY_MODE = "manual_review_only"
EXPECTED_REVIEW_STATUS = "dry_run_passed"

SUPPORTED_REPLACEMENT_TYPES = {
    "exact",
    "regex",
    "insert_after",
    "insert_before",
}

FORBIDDEN_TARGET_PREFIXES = (
    "indexAI/",
    "Scripting/ready_to_jazz_wow_youtube_profiles_audio_sync/",
    "patch_specs/inbox/",
)

FORBIDDEN_TARGET_EXACT = {
    "Scripting/shared/blender_compat.py",
}

FORBIDDEN_TARGET_FRAGMENTS = (
    "full_analysis",
    "analysis_full",
)

FORBIDDEN_COMMAND_FRAGMENTS = (
    "git reset --hard",
    "git clean",
    "Remove-Item -Recurse",
    "Remove-Item -Force -Recurse",
    "patch_specs/inbox/",
)

DEFAULT_GUARDRAILS = [
    "Reviewed specs are still manual-review-only.",
    "This tool only dry-runs; it never writes source targets.",
    "Do not copy reviewed specs into patch_specs/inbox/ without explicit approval.",
    "Keep provider execution explicit and report-bound.",
]


def resolve_repo_path(repo_root: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def normalize_repo_path(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/")


def sanitize_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    sanitized = sanitized.strip("._-")
    return sanitized or "reviewed_patch_spec"


def read_json_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def load_patch_runner(repo_root: Path) -> tuple[Any, Any]:
    sys.path.insert(0, str(repo_root))
    module = importlib.import_module("Tools.repo_patch_runner.apply_repo_mods")
    return module.apply_spec, module.PatchError


def target_path_error(path: str, repo_root: Path) -> str | None:
    normalized = normalize_repo_path(path)
    if not normalized:
        return "empty target path"
    if Path(normalized).is_absolute():
        return "absolute target paths are not allowed"
    full = (repo_root / normalized).resolve()
    try:
        full.relative_to(repo_root)
    except ValueError:
        return "target path escapes repository root"
    if normalized in FORBIDDEN_TARGET_EXACT:
        return f"forbidden target path: {normalized}"
    if any(normalized.startswith(prefix) for prefix in FORBIDDEN_TARGET_PREFIXES):
        return f"forbidden target prefix: {normalized}"
    lower = normalized.lower()
    if any(fragment in lower for fragment in FORBIDDEN_TARGET_FRAGMENTS) and lower.endswith(".json"):
        return f"forbidden full-analysis JSON target: {normalized}"
    if "*" in normalized or normalized.endswith("/"):
        return "target is a path group, glob or directory"
    if not full.exists():
        return "target file does not exist"
    if not full.is_file():
        return "target is not a file"
    return None


def validation_command_error(command: Any) -> str | None:
    lower = str(command).lower()
    for fragment in FORBIDDEN_COMMAND_FRAGMENTS:
        if fragment.lower() in lower:
            return f"forbidden command fragment: {fragment}"
    return None


def validate_replacement(item: Any) -> str | None:
    if not isinstance(item, dict):
        return "replacement item must be an object"
    kind = item.get("type", "exact")
    if kind not in SUPPORTED_REPLACEMENT_TYPES:
        return f"unsupported replacement type: {kind}"
    count = item.get("count", 1)
    try:
        if int(count) < 1:
            return "replacement count must be >= 1"
    except (TypeError, ValueError):
        return "replacement count must be an integer"
    if kind in {"exact", "regex"} and not isinstance(item.get("new"), str):
        return f"{kind} replacement requires new string"
    if kind == "exact" and not isinstance(item.get("old"), str):
        return "exact replacement requires old string"
    if kind == "regex" and not isinstance(item.get("pattern"), str):
        return "regex replacement requires pattern string"
    if kind in {"insert_after", "insert_before"}:
        if not isinstance(item.get("anchor"), str) or not isinstance(item.get("insert"), str):
            return f"{kind} replacement requires anchor and insert strings"
    return None


def validate_inputs(draft: dict[str, Any], plan: dict[str, Any], repo_root: Path) -> list[str]:
    errors: list[str] = []
    if draft.get("kind") != EXPECTED_DRAFT_KIND:
        errors.append(f"draft kind must be {EXPECTED_DRAFT_KIND}")
    if draft.get("apply_mode") != EXPECTED_APPLY_MODE:
        errors.append("draft apply_mode must be manual_review_only")
    if draft.get("provider_execution_performed") is not False:
        errors.append("draft provider_execution_performed must be false")
    if plan.get("kind") != EXPECTED_PLAN_KIND:
        errors.append(f"replacement plan kind must be {EXPECTED_PLAN_KIND}")
    if plan.get("apply_mode") != EXPECTED_APPLY_MODE:
        errors.append("replacement plan apply_mode must be manual_review_only")
    if plan.get("provider_execution_performed") is not False:
        errors.append("replacement plan provider_execution_performed must be false")

    draft_operations = draft.get("operations")
    if not isinstance(draft_operations, list) or not draft_operations:
        errors.append("draft operations must be a non-empty list")

    plan_operations = plan.get("operations")
    if not isinstance(plan_operations, list) or not plan_operations:
        errors.append("replacement plan operations must be a non-empty list")

    if isinstance(draft_operations, list) and isinstance(plan_operations, list):
        draft_paths = {normalize_repo_path(op.get("path")) for op in draft_operations if isinstance(op, dict)}
        for index, operation in enumerate(plan_operations):
            if not isinstance(operation, dict):
                errors.append(f"plan operations[{index}] must be an object")
                continue
            path = normalize_repo_path(operation.get("path"))
            if path not in draft_paths:
                errors.append(f"plan operations[{index}] path is not present in draft: {path}")
            path_error = target_path_error(path, repo_root)
            if path_error:
                errors.append(f"plan operations[{index}] {path}: {path_error}")
            replacements = operation.get("replacements")
            if not isinstance(replacements, list) or not replacements:
                errors.append(f"plan operations[{index}] replacements must be a non-empty list")
            elif len(replacements) > 12:
                errors.append(f"plan operations[{index}] has too many replacements; keep reviewed patches small")
            else:
                for repl_index, replacement in enumerate(replacements):
                    repl_error = validate_replacement(replacement)
                    if repl_error:
                        errors.append(f"plan operations[{index}].replacements[{repl_index}]: {repl_error}")

    for command in plan.get("validation_commands") or []:
        command_error = validation_command_error(command)
        if command_error:
            errors.append(command_error)

    return errors


def draft_operations_by_path(draft: dict[str, Any]) -> dict[str, dict[str, Any]]:
    operations = draft.get("operations") or []
    return {
        normalize_repo_path(op.get("path")): op
        for op in operations
        if isinstance(op, dict) and normalize_repo_path(op.get("path"))
    }


def build_reviewed_operation(plan_operation: dict[str, Any], draft_operation: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {
        "path": normalize_repo_path(plan_operation.get("path")),
        "replacements": copy.deepcopy(plan_operation.get("replacements") or []),
        "proposal_id": draft_operation.get("proposal_id"),
        "artifact_kind": draft_operation.get("artifact_kind"),
        "operation": draft_operation.get("operation") or "manual_patch_suggestion",
        "content_status": "reviewed_patch_spec",
        "review_status": EXPECTED_REVIEW_STATUS,
        "require_contains_before": plan_operation.get("require_contains_before") or [],
        "forbid_contains_before": plan_operation.get("forbid_contains_before") or [],
        "require_contains_after": plan_operation.get("require_contains_after") or [],
        "forbid_contains_after": plan_operation.get("forbid_contains_after") or [],
    }
    for optional_key in ("expected_line_delta", "normalize_replacement_newlines"):
        if optional_key in plan_operation:
            output[optional_key] = plan_operation[optional_key]
    if plan_operation.get("review_notes"):
        output["review_notes"] = plan_operation["review_notes"]
    return output


def dry_run_spec(repo_root: Path, spec: dict[str, Any]) -> tuple[bool, list[dict[str, Any]], str]:
    apply_spec, patch_error = load_patch_runner(repo_root)
    try:
        reports = apply_spec(repo_root, copy.deepcopy(spec), write=False, no_backup=True)
    except patch_error as exc:
        return False, [], str(exc)
    return True, [
        {
            "path": repo_relative(report.path, repo_root),
            "changed": report.changed,
            "before_lines": report.before_lines,
            "after_lines": report.after_lines,
            "replacements_applied": report.replacements_applied,
            "bom_removed": report.bom_removed,
        }
        for report in reports
    ], ""


def build_reviewed_spec(
    *,
    repo_root: Path,
    draft_path: Path,
    plan_path: Path,
    output_dir: Path,
    basename: str,
) -> dict[str, Any]:
    draft = read_json_object(draft_path)
    plan = read_json_object(plan_path)
    errors = validate_inputs(draft, plan, repo_root)
    warnings: list[str] = []

    draft_by_path = draft_operations_by_path(draft)
    reviewed_operations: list[dict[str, Any]] = []
    for plan_operation in plan.get("operations") or []:
        if not isinstance(plan_operation, dict):
            continue
        path = normalize_repo_path(plan_operation.get("path"))
        draft_operation = draft_by_path.get(path)
        if draft_operation is None:
            continue
        reviewed_operations.append(build_reviewed_operation(plan_operation, draft_operation))

    reviewed_spec = {
        "version": 1,
        "schema_version": 1,
        "kind": REVIEWED_SPEC_KIND,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": str(repo_root),
        "source_draft_spec": repo_relative(draft_path, repo_root),
        "source_replacement_plan": repo_relative(plan_path, repo_root),
        "source_proposal_report": draft.get("source_proposal_report") or "",
        "proposal_id": draft.get("proposal_id") or "",
        "proposal_title": draft.get("proposal_title") or "",
        "apply_mode": EXPECTED_APPLY_MODE,
        "review_status": EXPECTED_REVIEW_STATUS,
        "provider_execution_performed": False,
        "description": plan.get("description") or draft.get("description") or "Reviewed patch spec",
        "operations": reviewed_operations,
        "validation_commands": plan.get("validation_commands") or draft.get("validation_commands") or [],
        "stop_conditions": plan.get("stop_conditions") or draft.get("stop_conditions") or [],
        "do_not_touch": draft.get("do_not_touch") or [],
        "guardrails": DEFAULT_GUARDRAILS,
    }

    if not reviewed_operations and not errors:
        errors.append("no reviewed operations were produced")

    dry_run_passed = False
    dry_run_reports: list[dict[str, Any]] = []
    dry_run_error = ""
    if not errors:
        dry_run_passed, dry_run_reports, dry_run_error = dry_run_spec(repo_root, reviewed_spec)
        if not dry_run_passed:
            errors.append(f"dry-run failed: {dry_run_error}")
        elif not any(item.get("changed") for item in dry_run_reports):
            errors.append("dry-run passed but no target would change")

    reviewed_spec["dry_run"] = {
        "passed": dry_run_passed and not errors,
        "error": dry_run_error,
        "reports": dry_run_reports,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    spec_path = output_dir / f"{basename}.json"
    manifest_path = output_dir / f"{basename}_manifest.json"
    markdown_path = output_dir / f"{basename}_manifest.md"
    spec_path.write_text(json.dumps(reviewed_spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "kind": REVIEWED_MANIFEST_KIND,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "apply_mode": EXPECTED_APPLY_MODE,
        "review_status": EXPECTED_REVIEW_STATUS,
        "source_draft_spec": repo_relative(draft_path, repo_root),
        "source_replacement_plan": repo_relative(plan_path, repo_root),
        "reviewed_spec_count": 1,
        "specs": [
            {
                "path": repo_relative(spec_path, repo_root),
                "kind": REVIEWED_SPEC_KIND,
                "operation_count": len(reviewed_operations),
                "dry_run_passed": reviewed_spec["dry_run"]["passed"],
                "operations": [
                    {
                        "path": operation.get("path"),
                        "artifact_kind": operation.get("artifact_kind"),
                        "replacement_count": len(operation.get("replacements") or []),
                    }
                    for operation in reviewed_operations
                ],
            }
        ],
        "guardrails": DEFAULT_GUARDRAILS,
    }
    manifest["manifest_json"] = repo_relative(manifest_path, repo_root)
    manifest["manifest_markdown"] = repo_relative(markdown_path, repo_root)
    manifest["reviewed_spec"] = repo_relative(spec_path, repo_root)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_manifest_markdown(manifest), encoding="utf-8")
    return manifest


def render_manifest_markdown(manifest: dict[str, Any]) -> str:
    lines = ["# Reviewed Patch Spec", ""]
    lines.append(f"- Generated at: `{manifest['generated_at']}`")
    lines.append(f"- Source draft: `{manifest['source_draft_spec']}`")
    lines.append(f"- Replacement plan: `{manifest['source_replacement_plan']}`")
    lines.append(f"- Passed: `{manifest['passed']}`")
    lines.append(f"- Provider execution performed: `{manifest['provider_execution_performed']}`")
    lines.append("")
    lines.append("## Specs")
    lines.append("")
    for item in manifest["specs"]:
        lines.append(
            f"- `{item['path']}`: dry-run `{item['dry_run_passed']}`, "
            f"{item['operation_count']} operation(s)"
        )
    lines.append("")
    if manifest["errors"]:
        lines.append("## Errors")
        lines.append("")
        for error in manifest["errors"]:
            lines.append(f"- {error}")
        lines.append("")
    lines.append("## Guardrail")
    lines.append("")
    lines.append("This reviewed spec has been dry-run only. It is not queued and was not applied.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--draft", required=True, help="Draft proposal patch spec JSON.")
    parser.add_argument("--replacement-plan", required=True, help="Explicit replacement plan JSON.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--basename", default=DEFAULT_BASENAME)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    draft_path = resolve_repo_path(repo_root, args.draft)
    plan_path = resolve_repo_path(repo_root, args.replacement_plan)
    output_dir = resolve_repo_path(repo_root, args.output_dir)
    manifest = build_reviewed_spec(
        repo_root=repo_root,
        draft_path=draft_path,
        plan_path=plan_path,
        output_dir=output_dir,
        basename=sanitize_filename(args.basename),
    )
    print(
        json.dumps(
            {
                "passed": manifest["passed"],
                "manifest_json": manifest["manifest_json"],
                "manifest_markdown": manifest["manifest_markdown"],
                "reviewed_spec": manifest["reviewed_spec"],
                "reviewed_spec_count": manifest["reviewed_spec_count"],
            },
            indent=2,
        )
    )
    return 0 if manifest["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
