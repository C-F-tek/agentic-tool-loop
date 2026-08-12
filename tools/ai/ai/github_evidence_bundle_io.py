#!/usr/bin/env python3
"""Shared IO, path and policy helpers for GitHub evidence bundles."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from Tools.validation.report_utils import physical_line_count
except ImportError:  # pragma: no cover - fallback for direct package-local execution.
    def physical_line_count(text: str) -> int:
        if not text:
            return 0
        return text.count("\n") + (0 if text.endswith("\n") else 1)

DEFAULT_REPORTS = (
    "output/validation/ai_workload_report_quality.json",
    "output/validation/ai_workload_quality_lane_routing.json",
    "output/validation/npu_decode_quality_remediation.json",
    "output/validation/npu_decode_smoke_diagnostic.json",
    "output/validation/local_provider_probe.json",
    "output/validation/npu_runtime_output_manifest.json",
    "output/validation/provider_result_report.json",
)

DEFAULT_SELECTED_CHUNKS_EVIDENCE = (
    "docs/LOCAL_VALIDATION_EVIDENCE/full_context_golden_selected_chunks_evidence.json",
)

MAX_ARTIFACT_PREVIEW_CHARS = 1500
MAX_PATCH_PLAN_TEXT_CHARS = 1200
DEFAULT_INCLUDED_ARTIFACT_CHARS = 6000
DEFAULT_MAX_INCLUDED_ARTIFACTS = 40
CONTENT_EXTENSION_ALLOWLIST = {".json", ".md", ".txt", ".csv", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".py", ".ps1"}

RAW_ARTIFACT_DENY_PREFIXES = (
    "output/ai_context_packs/",
    "output/ai_pipeline/gpu_deep_planning_parallel_checkpoints/",
    "output/ai_pipeline/gpu_planner_nonempty_diagnostics_checkpoints",
    "output/ai_pipeline/gpu_planner_fallback_verify_checkpoints",
    "output/ai_pipeline/gpu_planner_full_after_fallback_fix_checkpoints",
    "indexAI/code_chunks/",
    "indexAI/project_code_chunks/",
    "renders/",
)

RAW_ARTIFACT_DENY_FRAGMENTS = (
    "full_analysis",
    "analysis_full",
    ".sqlite",
    ".db",
    "_npu_async_audit_context",
    "_npu_async_audit_npu",
    "_npu_async_audit_npu_notes",
)


def split_path_values(items: list[str]) -> list[str]:
    """Expand repeatable/comma-separated path CLI values."""
    out: list[str] = []
    for item in items:
        for part in str(item).split(","):
            normalized = part.strip().strip("'\"")
            if normalized:
                out.append(normalized)
    return out


def read_json(path: Path) -> dict[str, Any] | None:
    """Read a JSON object, returning None for missing/malformed/non-object input."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def read_text(path: Path) -> tuple[str, str | None]:
    """Read text defensively using UTF-8 replacement semantics."""
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace"), None
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}"


def sha256_file(path: Path) -> str | None:
    """Return SHA-256 for an existing file."""
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def line_count(text: str) -> int:
    """Return physical line count for text."""
    return physical_line_count(text)


def compact_value(value: Any, *, max_string: int = 500) -> Any:
    """Bound nested values for compact evidence summaries."""
    if isinstance(value, str):
        return value if len(value) <= max_string else value[:max_string] + "...[truncated]"
    if isinstance(value, list):
        return [compact_value(item, max_string=max_string) for item in value[:20]]
    if isinstance(value, dict):
        return {str(key): compact_value(item, max_string=max_string) for key, item in value.items()}
    return value


def as_list(value: Any) -> list[Any]:
    """Normalize a scalar/list/None into a list."""
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def list_contains(value: Any, expected: str) -> bool:
    """Case-insensitive containment check over list-normalized values."""
    return any(str(item).lower() == expected.lower() for item in as_list(value))


def resolve_repo_path(repo_root: Path, raw: str) -> Path:
    """Resolve a raw path relative to the repository root."""
    path = Path(raw)
    return path if path.is_absolute() else repo_root / path


def repo_relative(path: Path, repo_root: Path) -> str:
    """Return a repository-relative path when possible."""
    if path.is_absolute() and path.is_relative_to(repo_root):
        return path.relative_to(repo_root).as_posix()
    return str(path).replace("\\", "/")


def normalize_manifest_path(path: Path, repo_root: Path) -> str:
    """Return a normalized path for manifest/report output."""
    return repo_relative(path, repo_root).replace("\\", "/")


def raw_artifact_content_allowed(rel_path: str) -> bool:
    """Return whether bounded raw artifact content may be embedded."""
    lower = rel_path.lower().replace("\\", "/")
    if any(lower.startswith(prefix.lower()) for prefix in RAW_ARTIFACT_DENY_PREFIXES):
        return False
    if any(fragment.lower() in lower for fragment in RAW_ARTIFACT_DENY_FRAGMENTS):
        return False
    return True
