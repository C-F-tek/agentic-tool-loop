"""Controlled Markdown split shadow applier."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import SAFETY_FLAGS, SUPPORTED_KIND
from .shadow import build_shadow_plan, write_shadow_plan


def load_specs(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict) and isinstance(data.get("patch_specs"), list):
        return list(data["patch_specs"])
    if isinstance(data, list):
        return list(data)
    raise ValueError("patch specs JSON must be a list or object with patch_specs")


def resolve_target(repo_root: Path, rel_path: str) -> Path:
    target = (repo_root / rel_path).resolve()
    root = repo_root.resolve()
    if root not in target.parents and target != root:
        raise ValueError(f"target escapes repository: {rel_path}")
    return target


def process_one(repo_root: Path, spec: dict[str, Any], apply_shadow: bool, shadow_root: Path | None) -> dict[str, Any]:
    kind = str(spec.get("candidate_kind") or spec.get("kind") or "")
    target_path = str(spec.get("target_path") or spec.get("path") or "")
    result = {"candidate_kind": kind, "target_path": target_path, "accepted": False, "written": 0}

    if kind != SUPPORTED_KIND:
        result["rejected_reason"] = "not a markdown_split patch spec"
        return result
    if not target_path:
        result["rejected_reason"] = "target path missing"
        return result
    try:
        target = resolve_target(repo_root, target_path)
    except Exception as exc:  # noqa: BLE001 - diagnostic report.
        result["rejected_reason"] = f"{type(exc).__name__}: {exc}"
        return result
    if target.suffix.lower() != ".md":
        result["rejected_reason"] = "target is not Markdown"
        return result
    if not target.exists():
        result["rejected_reason"] = "target file does not exist"
        return result

    plan = build_shadow_plan(target, repo_root, shadow_root)
    result.update({"accepted": True, "shadow_dir": plan["shadow_dir"], "section_count": plan["section_count"]})
    if apply_shadow:
        result["written"] = write_shadow_plan(plan)
    return result


def apply_markdown_split_specs(
    repo_root: Path,
    patch_specs: Path,
    apply_shadow: bool,
    max_specs: int,
    shadow_root: Path | None,
) -> dict[str, Any]:
    specs = load_specs(patch_specs)[:max_specs]
    results = [process_one(repo_root, spec, apply_shadow, shadow_root) for spec in specs]
    accepted = sum(1 for item in results if item["accepted"])
    written = sum(int(item["written"]) for item in results)
    rejected = sum(1 for item in results if item.get("rejected_reason"))
    report = {
        "kind": "full0to10_markdown_split_shadow_apply",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": True,
        "dry_run": not apply_shadow,
        "source_writes_performed": False,
        "shadow_root": str(shadow_root) if shadow_root else None,
        "patch_specs_path": str(patch_specs),
        "processed_count": len(specs),
        "accepted_count": accepted,
        "written_file_count": written,
        "rejected_count": rejected,
        "results": results,
        "errors": [],
        "warnings": [],
    }
    report.update(SAFETY_FLAGS)
    report["patch_application_performed"] = False
    return report
