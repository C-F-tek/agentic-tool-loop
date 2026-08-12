from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import zipfile

from Tools.ai.full_run_bundle_zip.discovery import (
    candidate_entry,
    collect_candidates,
    discover_recursive_dir_files,
)
from Tools.ai.full_run_bundle_zip.git_status import run_git_status
from Tools.ai.full_run_bundle_zip.paths import repo_relative
from Tools.ai.full_run_bundle_zip.policy import default_required_recursive_roots
from Tools.ai.full_run_bundle_zip.reports import render_markdown_report, write_json


def add_sidecar_paths(
    repo_root: Path,
    deduped_members: dict[str, Path],
    artifact_list_json: Path,
    artifact_list_txt: Path,
    completeness_json: Path,
    completeness_md: Path,
) -> None:
    """Add sidecar report files to the ZIP member map."""
    for path in (artifact_list_json, artifact_list_txt, completeness_json, completeness_md):
        deduped_members[repo_relative(path, repo_root)] = path


def build_full_run_bundle(
    *,
    repo_root: Path,
    stamp: str,
    basename: str,
    evidence_dir: Path,
    artifacts: list[str],
    artifact_roots: list[str],
    required_artifacts: list[str],
    required_roots: list[str],
    include_default_recursive_roots: bool,
    include_default_stamp_files: bool,
    include_git_status: bool,
    allow_output: bool,
) -> dict[str, Any]:
    """Create a complete evidence ZIP and sidecar completeness reports."""
    evidence_dir.mkdir(parents=True, exist_ok=True)

    zip_path = evidence_dir / f"{basename}.zip"
    artifact_list_json = evidence_dir / f"{basename}_artifact_list.json"
    artifact_list_txt = evidence_dir / f"{basename}_artifact_list.txt"
    git_status_path = evidence_dir / f"{basename}_git_status_after_run.txt"
    completeness_json = evidence_dir / f"{basename}_bundle_completeness_report.json"
    completeness_md = evidence_dir / f"{basename}_bundle_completeness_report.md"

    effective_required_roots = list(required_roots)
    if include_default_recursive_roots:
        effective_required_roots.extend(default_required_recursive_roots(stamp))

    candidates = collect_candidates(
        repo_root,
        evidence_dir,
        stamp,
        basename,
        artifacts,
        artifact_roots,
        required_artifacts,
        effective_required_roots,
        include_default_stamp_files,
    )

    artifacts_report: list[dict[str, Any]] = []
    member_paths: list[tuple[Path, str]] = []
    skipped_recursive: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    for candidate in candidates:
        entry = candidate_entry(candidate, repo_root, allow_output=allow_output)
        if entry["errors"]:
            errors.extend(f"{entry['path']}: {error}" for error in entry["errors"])
            artifacts_report.append(entry)
            continue

        if candidate.path.is_file():
            rel = repo_relative(candidate.path, repo_root)
            member_paths.append((candidate.path, rel))
            entry["included_in_zip"] = True
            entry["zip_member_count"] = 1
        elif candidate.path.is_dir():
            files, skipped = discover_recursive_dir_files(candidate.path, repo_root, allow_output=allow_output)
            skipped_recursive.extend(skipped)
            for file_path in files:
                member_paths.append((file_path, repo_relative(file_path, repo_root)))
            entry["included_in_zip"] = bool(files)
            entry["zip_member_count"] = len(files)
            if candidate.required and not files:
                msg = "required recursive root has no safe files"
                entry["errors"].append(msg)
                errors.append(f"{entry['path']}: {msg}")
        else:
            if candidate.required:
                errors.append(f"{entry['path']}: required artifact missing")
            else:
                warnings.append(f"{entry['path']}: artifact missing")
        artifacts_report.append(entry)

    if include_git_status:
        git_status, status_error = run_git_status(repo_root)
        if status_error:
            warnings.append(f"git status unavailable: {status_error}")
        git_status_path.write_text(git_status, encoding="utf-8")
        member_paths.append((git_status_path, repo_relative(git_status_path, repo_root)))

    deduped_members: dict[str, Path] = {}
    for path, rel in member_paths:
        if rel not in deduped_members:
            deduped_members[rel] = path

    artifact_list = sorted(deduped_members)
    write_json(artifact_list_json, artifact_list)
    artifact_list_txt.write_text("\n".join(artifact_list) + ("\n" if artifact_list else ""), encoding="utf-8")

    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "full_run_evidence_bundle_completeness",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": str(repo_root),
        "stamp": stamp,
        "basename": basename,
        "zip_path": repo_relative(zip_path, repo_root),
        "artifact_list_json": repo_relative(artifact_list_json, repo_root),
        "artifact_list_txt": repo_relative(artifact_list_txt, repo_root),
        "git_status_after_run": repo_relative(git_status_path, repo_root) if include_git_status else None,
        "allow_output": allow_output,
        "include_default_recursive_roots": include_default_recursive_roots,
        "include_default_stamp_files": include_default_stamp_files,
        "required_recursive_roots": effective_required_roots,
        "artifacts": artifacts_report,
        "skipped_recursive": skipped_recursive[:500],
        "included_artifact_count": len(artifact_list),
        "zip_member_count": 0,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "persistent_memory_write_performed": False,
        "errors": errors,
        "warnings": warnings,
        "passed": not errors,
    }

    report["bundle_completeness_report_json"] = repo_relative(completeness_json, repo_root)
    report["bundle_completeness_report_md"] = repo_relative(completeness_md, repo_root)
    write_json(completeness_json, report)
    completeness_md.write_text(render_markdown_report(report), encoding="utf-8")

    add_sidecar_paths(repo_root, deduped_members, artifact_list_json, artifact_list_txt, completeness_json, completeness_md)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for rel, path in sorted(deduped_members.items()):
            archive.write(path, rel)

    report["zip_member_count"] = len(deduped_members)
    write_json(completeness_json, report)
    completeness_md.write_text(render_markdown_report(report), encoding="utf-8")
    return report
