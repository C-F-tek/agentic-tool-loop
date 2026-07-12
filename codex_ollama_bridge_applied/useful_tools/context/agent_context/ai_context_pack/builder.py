"""AI context pack and evidence builders."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .common import context_unavailable_reason, normalize_repo_path, repo_relative
from .files import build_file_entry, profile_items
from .markdown import render_evidence_markdown, render_pack_markdown
from .profiles import APPLY_MODE, EVIDENCE_KIND, PACK_KIND, PROFILE_COMMON_STOP_CONDITIONS, PROFILES

def build_pack(
    *,
    repo_root: Path,
    profile_name: str,
    output_dir: Path,
    basename: str,
    max_total_chars: int,
    max_file_chars: int,
) -> dict[str, Any]:
    if profile_name not in PROFILES:
        raise ValueError(f"unknown profile: {profile_name}")
    profile = PROFILES[profile_name]
    errors: list[str] = []
    warnings: list[str] = []
    remaining = max_total_chars
    file_entries: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for item, required in profile_items(profile):
        path = normalize_repo_path(item.get("path"))
        if path in seen_paths:
            warnings.append(f"duplicate profile path ignored after first occurrence: {path}")
            continue
        seen_paths.add(path)
        entry, remaining = build_file_entry(
            repo_root=repo_root,
            item=item,
            required=required,
            remaining_chars=remaining,
            max_file_chars=max_file_chars,
        )
        file_entries.append(entry)
        if required and (not entry["exists"] or not entry["included"] or not entry["policy_ok"]):
            errors.append(
                f"required file unavailable for context: {path} ({context_unavailable_reason(entry)})"
            )
        elif (not required) and (
            not entry["exists"] or not entry["included"] or not entry["policy_ok"]
        ):
            warnings.append(
                f"optional file unavailable for context: {path} ({context_unavailable_reason(entry)})"
            )
        if entry.get("truncated"):
            warnings.append(f"context content truncated for {path}")

    validation_commands = list(profile.get("validation_commands") or [])
    stop_conditions = [
        *PROFILE_COMMON_STOP_CONDITIONS,
        *list(profile.get("stop_conditions") or []),
    ]
    pack = {
        "schema_version": 1,
        "kind": PACK_KIND,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": str(repo_root),
        "profile": profile_name,
        "profile_description": profile.get("description") or "",
        "apply_mode": APPLY_MODE,
        "provider_execution_performed": False,
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "max_total_chars": max_total_chars,
        "max_file_chars": max_file_chars,
        "total_included_chars": sum(int(item.get("included_chars") or 0) for item in file_entries),
        "file_count": len(file_entries),
        "included_file_count": sum(1 for item in file_entries if item.get("included") is True),
        "truncated_file_count": sum(1 for item in file_entries if item.get("truncated") is True),
        "validation_commands": validation_commands,
        "stop_conditions": stop_conditions,
        "files": file_entries,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{basename}.json"
    md_path = output_dir / f"{basename}.md"
    pack["pack_json"] = repo_relative(json_path, repo_root)
    pack["pack_markdown"] = repo_relative(md_path, repo_root)
    json_path.write_text(json.dumps(pack, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_pack_markdown(pack), encoding="utf-8")
    return pack

def build_evidence(
    pack: dict[str, Any], repo_root: Path, evidence_dir: Path, evidence_basename: str
) -> dict[str, Any]:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    json_path = evidence_dir / f"{evidence_basename}.json"
    md_path = evidence_dir / f"{evidence_basename}.md"
    files = pack.get("files") if isinstance(pack.get("files"), list) else []
    evidence = {
        "schema_version": 1,
        "kind": EVIDENCE_KIND,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": pack.get("repo_root"),
        "profile": pack.get("profile"),
        "profile_description": pack.get("profile_description"),
        "source_pack": pack.get("pack_json"),
        "source_pack_markdown": pack.get("pack_markdown"),
        "passed": pack.get("passed") is True,
        "errors": pack.get("errors") or [],
        "warnings": pack.get("warnings") or [],
        "provider_execution_performed": False,
        "apply_mode": APPLY_MODE,
        "file_count": pack.get("file_count"),
        "included_file_count": pack.get("included_file_count"),
        "truncated_file_count": pack.get("truncated_file_count"),
        "total_included_chars": pack.get("total_included_chars"),
        "validation_command_count": len(pack.get("validation_commands") or []),
        "required_missing": [
            item.get("path")
            for item in files
            if item.get("required") is True
            and (item.get("exists") is not True or item.get("included") is not True)
        ],
        "forbidden_path_count": sum(1 for item in files if item.get("policy_ok") is not True),
        "blender_runtime_touched": any(
            str(item.get("path") or "").startswith("Scripting/") for item in files
        ),
        "included_paths": [
            {
                "path": item.get("path"),
                "role": item.get("role"),
                "required": item.get("required"),
                "included": item.get("included"),
                "truncated": item.get("truncated"),
                "sha256": item.get("sha256"),
                "included_chars": item.get("included_chars"),
            }
            for item in files
        ],
        "decision": {
            "context_pack_built": pack.get("passed") is True,
            "provider_execution_seen": False,
            "forbidden_paths_blocked": sum(1 for item in files if item.get("policy_ok") is not True)
            == 0,
            "source_writes_performed": False,
        },
    }
    evidence["evidence_json"] = repo_relative(json_path, repo_root)
    evidence["evidence_markdown"] = repo_relative(md_path, repo_root)
    json_path.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    md_path.write_text(render_evidence_markdown(evidence), encoding="utf-8")
    return evidence
