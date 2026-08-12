#!/usr/bin/env python3
"""Shared helpers for report-only code patch-plan tooling.

The helpers in this module are intentionally side-effect-light. They centralize
path normalization, compact JSON loading, line-count evidence loading,
guardrail checks and Markdown writing for the code patch-plan lane.
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[2]
if str(REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORTS))

try:
    from Tools.validation.report_utils import (
        line_count_for_path as shared_line_count_for_path,
        load_line_count_csv_map,
        parse_line_count_csv_row,
        resolve_output_path,
        write_json_report,
    )
except ImportError:  # pragma: no cover - fallback for direct package-local execution.
    from report_utils import (  # type: ignore
        line_count_for_path as shared_line_count_for_path,
        load_line_count_csv_map,
        parse_line_count_csv_row,
        resolve_output_path,
        write_json_report,
    )

REPORT_ONLY_FALSE_FIELDS = (
    "provider_execution_performed",
    "patch_application_performed",
    "source_writes_performed",
)
FORBIDDEN_TARGET_PREFIXES = (
    "output/",
    "renders/",
    ".git/",
    "indexAI/code_chunks/",
    "indexAI/project_code_chunks/",
)
FORBIDDEN_TARGET_SUFFIXES = (
    ".db",
    ".sqlite",
    ".sqlite3",
)
FORBIDDEN_TARGET_FRAGMENTS = (
    "full_analysis",
    "analysis_full",
)
CODE_EXTENSIONS = {".py", ".ps1", ".psm1", ".psd1", ".yml", ".yaml"}
MAX_TEXT_CHARS = 700
MAX_ITEMS = 40


def now_iso() -> str:
    """Return an ISO-8601 local timestamp without fractional seconds."""
    return datetime.now().isoformat(timespec="seconds")


def normalize_repo_path(value: Any) -> str:
    """Normalize a repository-relative path-like value for report metadata."""
    return str(value or "").strip().replace("\\", "/").lstrip("./")


def repo_rel(repo_root: Path, path: Path) -> str:
    """Return a repository-relative path when possible."""
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return path.resolve(strict=False).as_posix()


def read_json_object(path: Path, *, missing_is_error: bool = True) -> tuple[dict[str, Any], list[str]]:
    """Read a JSON object and return `(data, errors)` without raising."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}, [f"missing file: {path}"] if missing_is_error else []
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"{type(exc).__name__}: {exc}"]
    if not isinstance(data, dict):
        return {}, ["root JSON value must be an object"]
    return data, []


def parse_line_count_row(row: dict[str, Any]) -> tuple[str, int] | None:
    """Parse one line-count CSV row into `(path, lines)` when valid."""
    return parse_line_count_csv_row(row)


def load_line_counts(repo_root: Path, csv_path: Path) -> tuple[dict[str, int], list[str]]:
    """Load optional line-count CSV evidence as a sizing hint."""
    counts, warnings = load_line_count_csv_map(csv_path)
    normalized_warnings = [
        warning.replace(str(csv_path), repo_rel(repo_root, csv_path)) for warning in warnings
    ]
    return counts, normalized_warnings


def line_count_for(path_value: str, counts: dict[str, int]) -> int | None:
    """Return a CSV line-count hint, including suffix matching for absolute CSV paths."""
    return shared_line_count_for_path(path_value, counts)


def compact_text(value: Any, limit: int = MAX_TEXT_CHARS) -> str:
    """Compact large scalar text values for evidence artifacts."""
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "...[truncated]"


def compact_list(value: Any, *, max_items: int = MAX_ITEMS, text_limit: int = MAX_TEXT_CHARS) -> list[Any]:
    """Compact lists while preserving non-string values as-is."""
    if not isinstance(value, list):
        return []
    compacted: list[Any] = []
    for item in value[:max_items]:
        compacted.append(compact_text(item, text_limit) if isinstance(item, str) else item)
    return compacted


def report_guardrail_errors(data: dict[str, Any], label: str) -> list[str]:
    """Return errors for report-only guardrail field violations."""
    errors: list[str] = []
    for field in REPORT_ONLY_FALSE_FIELDS:
        if data.get(field) is not False:
            errors.append(f"{label}: {field} must be false")
    if data.get("manual_review_required") is not True:
        errors.append(f"{label}: manual_review_required must be true")
    return errors


def report_only_guardrails(**extra: Any) -> dict[str, Any]:
    """Build a standard report-only guardrail block."""
    guardrails: dict[str, Any] = {
        "report_only": True,
        "manual_review_required": True,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "blender_runtime_execution_performed": False,
        "sqlite_write_performed": False,
    }
    guardrails.update(extra)
    return guardrails


def is_code_like_path(path_value: str) -> bool:
    """Return true when a target belongs to the code/config patch-plan lane."""
    return Path(path_value).suffix.lower() in CODE_EXTENSIONS


def forbidden_target_errors(path: str) -> list[str]:
    """Return policy errors for forbidden target prefixes, suffixes and fragments."""
    lower = path.lower()
    errors: list[str] = []
    for prefix in FORBIDDEN_TARGET_PREFIXES:
        if path.startswith(prefix):
            errors.append(f"forbidden target prefix: {prefix}")
    for suffix in FORBIDDEN_TARGET_SUFFIXES:
        if lower.endswith(suffix):
            errors.append(f"forbidden target suffix: {suffix}")
    for fragment in FORBIDDEN_TARGET_FRAGMENTS:
        if fragment in lower:
            errors.append(f"forbidden target fragment: {fragment}")
    return errors


def target_path_errors(repo_root: Path, path_value: str, *, require_existing: bool = True, require_code_like: bool = True) -> list[str]:
    """Validate a repository target path for manual-review code patch plans."""
    path = normalize_repo_path(path_value)
    errors: list[str] = []
    if not path:
        return ["empty target path"]
    if Path(path).is_absolute():
        errors.append("absolute target paths are not allowed")
    full = (repo_root / path).resolve(strict=False)
    try:
        full.relative_to(repo_root.resolve(strict=False))
    except ValueError:
        errors.append("target path escapes repository root")
    errors.extend(forbidden_target_errors(path))
    if require_code_like and not is_code_like_path(path):
        errors.append("target is not a code/config script path for the code patch-plan lane")
    if require_existing and not full.is_file():
        errors.append("target file does not exist")
    return errors


def write_json_and_markdown(repo_root: Path, report: dict[str, Any], output_value: str, markdown_value: str, markdown_text: str) -> str:
    """Write paired JSON/Markdown reports and return the JSON report string."""
    output = resolve_output_path(repo_root, output_value)
    markdown_output = resolve_output_path(repo_root, markdown_value)
    text = write_json_report(report, output)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(markdown_text, encoding="utf-8")
    return text
