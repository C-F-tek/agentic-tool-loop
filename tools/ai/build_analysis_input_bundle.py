#!/usr/bin/env python3
"""Build a mixed-file analysis input bundle for agnostic review.

The bundle can include Python, Markdown, JSON, TXT and other text-like files.
It is intended to prepare bounded, hash-tracked context for later AI/code review
without committing raw `output/**` or runtime artifacts.

It does not execute providers, run Blender, apply patches or write source files.
"""
from __future__ import annotations

import argparse
import hashlib
import mimetypes
import sys
from pathlib import Path
from typing import Any

REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[2]
if str(REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORTS))

from Tools.ai.code_patch_plan_common import (  # noqa: E402
    now_iso,
    repo_rel,
    report_only_guardrails,
    write_json_and_markdown,
)

REPORT_KIND = "analysis_input_bundle"
DEFAULT_OUTPUT = "output/analysis_input/analysis_input_bundle.json"
DEFAULT_MARKDOWN = "output/analysis_input/analysis_input_bundle.md"
DEFAULT_MAX_FILE_CHARS = 16000
DEFAULT_MAX_TOTAL_CHARS = 120000
DEFAULT_INCLUDE_EXTENSIONS = {
    ".py",
    ".ps1",
    ".psm1",
    ".psd1",
    ".md",
    ".json",
    ".jsonl",
    ".txt",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".csv",
}
DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "output",
    "renders",
    "venv",
}
DEFAULT_EXCLUDED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".png", ".jpg", ".jpeg", ".mp4", ".wav", ".blend"}


def sha256_file(path: Path) -> str | None:
    """Return SHA-256 for a file, or None on read errors."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def text_line_count(text: str) -> int:
    """Return physical line count for text."""
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def split_csv_values(values: list[str]) -> set[str]:
    """Expand repeated comma-separated CLI values into a set."""
    return {item.strip() for value in values for item in value.split(",") if item.strip()}


def is_excluded(path: Path, repo_root: Path, excluded_dirs: set[str], excluded_suffixes: set[str]) -> bool:
    """Return true when a file should not be included in analysis input."""
    suffix = path.suffix.lower()
    if suffix in excluded_suffixes:
        return True
    try:
        parts = path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).parts
    except ValueError:
        parts = path.parts
    return any(part in excluded_dirs for part in parts)


def resolve_inputs(repo_root: Path, values: list[str]) -> list[Path]:
    """Resolve input files/directories from CLI values."""
    paths: list[Path] = []
    for value in values:
        candidate = Path(value)
        full = candidate.resolve() if candidate.is_absolute() else (repo_root / candidate).resolve()
        paths.append(full)
    return paths


def iter_candidate_files(repo_root: Path, roots: list[Path], include_extensions: set[str], excluded_dirs: set[str], excluded_suffixes: set[str]) -> list[Path]:
    """Return sorted candidate files from explicit files/directories."""
    candidates: list[Path] = []
    search_roots = roots or [repo_root]
    for root in search_roots:
        if root.is_file():
            candidates.append(root)
            continue
        if root.is_dir():
            candidates.extend(path for path in root.rglob("*") if path.is_file())
    filtered = [path for path in candidates if path.suffix.lower() in include_extensions and not is_excluded(path, repo_root, excluded_dirs, excluded_suffixes)]
    unique = {path.resolve(strict=False): path for path in filtered}
    return sorted(unique, key=lambda path: repo_rel(repo_root, path).lower())


def read_text_file(path: Path) -> tuple[str, str | None]:
    """Read one text file using UTF-8 replacement semantics."""
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace"), None
    except OSError as exc:
        return "", f"{type(exc).__name__}: {exc}"


def build_entry(repo_root: Path, path: Path, max_file_chars: int, remaining_chars: int) -> tuple[dict[str, Any], int, str | None]:
    """Build one bundle entry and return chars consumed plus optional error."""
    rel = repo_rel(repo_root, path)
    text, error = read_text_file(path)
    if error:
        return {"path": rel, "included": False, "error": error}, 0, error
    raw_chars = len(text)
    limit = max(0, min(max_file_chars, remaining_chars))
    included_text = text[:limit]
    truncated = raw_chars > len(included_text)
    mime, _encoding = mimetypes.guess_type(path.name)
    return (
        {
            "path": rel,
            "included": bool(limit),
            "suffix": path.suffix.lower(),
            "mime_type": mime,
            "sha256": sha256_file(path),
            "raw_chars": raw_chars,
            "included_chars": len(included_text),
            "line_count": text_line_count(text),
            "truncated": truncated,
            "content_preview": included_text,
        },
        len(included_text),
        None,
    )


def largest_files_summary(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the largest included-file summaries for the report."""
    return sorted(
        [
            {
                "path": entry.get("path"),
                "raw_chars": entry.get("raw_chars"),
                "line_count": entry.get("line_count"),
                "truncated": entry.get("truncated"),
            }
            for entry in entries
            if entry.get("included")
        ],
        key=lambda item: int(item.get("raw_chars") or 0),
        reverse=True,
    )[:20]


def build_bundle(
    repo_root: Path,
    input_paths: list[Path],
    include_extensions: set[str],
    excluded_dirs: set[str],
    excluded_suffixes: set[str],
    max_file_chars: int,
    max_total_chars: int,
) -> dict[str, Any]:
    """Build a bounded mixed-file analysis input bundle."""
    errors: list[str] = []
    warnings: list[str] = []
    entries: list[dict[str, Any]] = []
    consumed = 0
    candidates = iter_candidate_files(repo_root, input_paths, include_extensions, excluded_dirs, excluded_suffixes)
    for path in candidates:
        if consumed >= max_total_chars:
            warnings.append("max_total_chars reached; remaining candidates omitted")
            break
        entry, used_chars, error = build_entry(repo_root, path, max_file_chars, max_total_chars - consumed)
        if error:
            errors.append(f"{entry.get('path')}: {error}")
        entries.append(entry)
        consumed += used_chars

    return {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "manual_review_required": True,
        "apply_mode": "report_only_analysis_input_bundle",
        "candidate_count": len(candidates),
        "included_count": sum(1 for entry in entries if entry.get("included")),
        "included_chars": consumed,
        "max_file_chars": max_file_chars,
        "max_total_chars": max_total_chars,
        "include_extensions": sorted(include_extensions),
        "excluded_dirs": sorted(excluded_dirs),
        "excluded_suffixes": sorted(excluded_suffixes),
        "entries": entries,
        "summary": {"largest_files": largest_files_summary(entries)},
        "guardrails": report_only_guardrails(
            raw_runtime_artifacts_excluded=True,
            providers_executed=False,
            blender_runtime_executed=False,
            patches_applied=False,
            source_files_written=False,
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render a compact human-readable bundle summary."""
    lines = ["# Analysis Input Bundle", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Candidate count: `{report['candidate_count']}`")
    lines.append(f"- Included count: `{report['included_count']}`")
    lines.append(f"- Included chars: `{report['included_chars']}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append(f"- Source writes performed: `{report['source_writes_performed']}`")
    lines.append("")
    lines.append("## Largest included files")
    lines.append("")
    largest = (report.get("summary") or {}).get("largest_files", []) if isinstance(report.get("summary"), dict) else []
    if not largest:
        lines.append("- none")
    for item in largest:
        lines.append(f"- `{item.get('path')}` — chars `{item.get('raw_chars')}`, lines `{item.get('line_count')}`, truncated `{item.get('truncated')}`")
    lines.append("")
    lines.append("## Guardrail")
    lines.append("")
    lines.append("This bundle is bounded analysis input only. It should feed review/proposal tools, not mutate source files.")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--input", action="append", default=[], help="File or directory to include; may be repeated.")
    parser.add_argument("--include-extension", action="append", default=[], help="Additional extension(s), comma-separated accepted.")
    parser.add_argument("--exclude-dir", action="append", default=[], help="Additional directory names to exclude.")
    parser.add_argument("--max-file-chars", type=int, default=DEFAULT_MAX_FILE_CHARS)
    parser.add_argument("--max-total-chars", type=int, default=DEFAULT_MAX_TOTAL_CHARS)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    include_extensions = set(DEFAULT_INCLUDE_EXTENSIONS)
    include_extensions.update(ext if ext.startswith(".") else f".{ext}" for ext in split_csv_values(args.include_extension))
    excluded_dirs = set(DEFAULT_EXCLUDED_DIRS)
    excluded_dirs.update(split_csv_values(args.exclude_dir))
    report = build_bundle(
        repo_root,
        resolve_inputs(repo_root, args.input),
        include_extensions,
        excluded_dirs,
        set(DEFAULT_EXCLUDED_SUFFIXES),
        args.max_file_chars,
        args.max_total_chars,
    )
    print(write_json_and_markdown(repo_root, report, args.output, args.markdown_output, render_markdown(report)), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
