"""Controlled applier for Full0To10 auto-refactor patch specs."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import ALLOWED_APPLY_KINDS, REJECTED_KINDS, SAFETY_FLAGS
from .diffs import ensure_final_newline, remove_trailing_whitespace, unified_diff
from .io_utils import load_patch_specs, repo_relative, resolve_target


def transform_text(kind: str, text: str) -> str:
    if kind == "safe_cleanup_trailing_whitespace":
        return remove_trailing_whitespace(text)
    if kind == "safe_cleanup_final_newline":
        return ensure_final_newline(text)
    return text


def apply_one(repo_root: Path, spec: dict[str, Any], apply: bool) -> dict[str, Any]:
    kind = str(spec.get("candidate_kind") or spec.get("kind") or "")
    target_path = str(spec.get("target_path") or spec.get("path") or "")
    result: dict[str, Any] = {
        "candidate_kind": kind,
        "target_path": target_path,
        "applied": False,
        "changed": False,
        "allowed": kind in ALLOWED_APPLY_KINDS,
    }

    if kind in REJECTED_KINDS:
        result["rejected_reason"] = "candidate kind requires manual refactor"
        return result
    if kind not in ALLOWED_APPLY_KINDS:
        result["rejected_reason"] = "candidate kind is not allowlisted"
        return result
    if not target_path:
        result["rejected_reason"] = "target_path missing"
        return result

    try:
        target = resolve_target(repo_root, target_path)
    except Exception as exc:  # noqa: BLE001 - diagnostic report.
        result["rejected_reason"] = f"{type(exc).__name__}: {exc}"
        return result

    if not target.exists():
        result["rejected_reason"] = "target file does not exist"
        return result

    before = target.read_text(encoding="utf-8", errors="replace")
    after = transform_text(kind, before)
    result["changed"] = before != after
    result["diff"] = unified_diff(Path(repo_relative(target, repo_root)), before, after)

    if apply and before != after:
        target.write_text(after, encoding="utf-8")
        result["applied"] = True
    return result


def apply_patch_specs(
    repo_root: Path,
    patch_specs_path: Path,
    apply: bool,
    max_specs: int,
) -> dict[str, Any]:
    specs = load_patch_specs(patch_specs_path)
    selected = specs[:max_specs]
    results = [apply_one(repo_root, spec, apply=apply) for spec in selected]
    changed = sum(1 for item in results if item["changed"])
    applied = sum(1 for item in results if item["applied"])
    rejected = sum(1 for item in results if item.get("rejected_reason"))
    report = {
        "kind": "full0to10_controlled_refactor_apply",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": True,
        "dry_run": not apply,
        "source_writes_performed": bool(apply and applied),
        "patch_specs_path": str(patch_specs_path),
        "spec_count": len(specs),
        "processed_count": len(selected),
        "changed_count": changed,
        "applied_count": applied,
        "rejected_count": rejected,
        "results": results,
        "errors": [],
        "warnings": [],
    }
    report.update(SAFETY_FLAGS)
    report["patch_application_performed"] = bool(apply and applied)
    return report
