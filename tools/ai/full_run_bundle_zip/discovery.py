from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from Tools.ai.full_run_bundle_zip.paths import repo_relative, resolve_repo_path
from Tools.ai.full_run_bundle_zip.policy import TEXT_SUFFIX_ALLOWLIST, forbidden_reason


@dataclass(frozen=True)
class Candidate:
    """One candidate artifact for inclusion."""

    path: Path
    source: str
    required: bool = False
    recursive_root: str | None = None


def discover_stamp_files(evidence_dir: Path, stamp: str, basename: str) -> list[Candidate]:
    """Discover stamped compact evidence files directly under evidence_dir."""
    if not evidence_dir.exists() or not evidence_dir.is_dir():
        return []
    candidates: list[Candidate] = []
    for path in sorted(evidence_dir.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or stamp not in path.name:
            continue
        if path.name.startswith(basename) and path.suffix.lower() == ".zip":
            continue
        if path.suffix.lower() not in TEXT_SUFFIX_ALLOWLIST:
            continue
        candidates.append(Candidate(path=path.resolve(), source="stamp_discovery"))
    return candidates


def discover_recursive_dir_files(
    root: Path,
    repo_root: Path,
    *,
    allow_output: bool,
) -> tuple[list[Path], list[dict[str, Any]]]:
    """Return safe file members below a recursive root and skipped entries."""
    files: list[Path] = []
    skipped: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: repo_relative(item, repo_root).lower()):
        if not path.is_file():
            continue
        rel = repo_relative(path, repo_root)
        if path.suffix.lower() not in TEXT_SUFFIX_ALLOWLIST:
            skipped.append({"path": rel, "reason": "suffix not allowlisted"})
            continue
        reason = forbidden_reason(rel, allow_output=allow_output)
        if reason:
            skipped.append({"path": rel, "reason": reason})
            continue
        files.append(path)
    return files, skipped


def dedupe_candidates(candidates: list[Candidate]) -> list[Candidate]:
    """Deduplicate candidates by resolved path while preserving first source."""
    out: list[Candidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.path.resolve().as_posix()
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def collect_candidates(
    repo_root: Path,
    evidence_dir: Path,
    stamp: str,
    basename: str,
    artifacts: list[str],
    artifact_roots: list[str],
    required_artifacts: list[str],
    required_roots: list[str],
    include_default_stamp_files: bool,
) -> list[Candidate]:
    """Collect explicit, required and discovered bundle candidates."""
    candidates: list[Candidate] = []
    if include_default_stamp_files:
        candidates.extend(discover_stamp_files(evidence_dir, stamp, basename))
    for raw in artifacts:
        candidates.append(Candidate(resolve_repo_path(repo_root, raw), source="explicit_artifact"))
    for raw in artifact_roots:
        root = resolve_repo_path(repo_root, raw)
        candidates.append(Candidate(root, source="explicit_recursive_root", recursive_root=repo_relative(root, repo_root)))
    for raw in required_artifacts:
        candidates.append(Candidate(resolve_repo_path(repo_root, raw), source="required_artifact", required=True))
    for raw in required_roots:
        root = resolve_repo_path(repo_root, raw)
        candidates.append(
            Candidate(
                root,
                source="required_recursive_root",
                required=True,
                recursive_root=repo_relative(root, repo_root),
            )
        )
    return dedupe_candidates(candidates)


def candidate_entry(candidate: Candidate, repo_root: Path, *, allow_output: bool) -> dict[str, Any]:
    """Build a manifest entry for a candidate path."""
    rel = repo_relative(candidate.path, repo_root)
    entry: dict[str, Any] = {
        "path": rel,
        "source": candidate.source,
        "required": candidate.required,
        "recursive_root": candidate.recursive_root,
        "exists": candidate.path.exists(),
        "is_file": candidate.path.is_file(),
        "is_dir": candidate.path.is_dir(),
        "included_in_zip": False,
        "zip_member_count": 0,
        "errors": [],
        "warnings": [],
    }
    reason = forbidden_reason(rel, allow_output=allow_output)
    if reason:
        entry["errors"].append(reason)
    if candidate.required and not candidate.path.exists():
        entry["errors"].append("required artifact missing")
    return entry
