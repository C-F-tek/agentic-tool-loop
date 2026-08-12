#!/usr/bin/env python3
"""Validate local Markdown links in repository documentation.

The validator checks repository-local Markdown links and ignores external URLs,
anchors-only links, mailto links and images.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote


DEFAULT_EXCLUDES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".repo_patch_backups",
    "renders",
    "output",
}

LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def is_excluded(path: Path, repo_root: Path, excludes: set[str]) -> bool:
    try:
        parts = path.relative_to(repo_root).parts
    except ValueError:
        parts = path.parts
    return any(part in excludes for part in parts)


def iter_markdown_files(repo_root: Path, excludes: set[str]) -> list[Path]:
    return sorted(
        path for path in repo_root.rglob("*.md")
        if not is_excluded(path, repo_root, excludes)
    )


def is_external_link(target: str) -> bool:
    lowered = target.lower()
    return (
        lowered.startswith("http://")
        or lowered.startswith("https://")
        or lowered.startswith("mailto:")
        or lowered.startswith("tel:")
    )


def normalize_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    if " " in target:
        target = target.split(" ", 1)[0]
    if "#" in target:
        target = target.split("#", 1)[0]
    return unquote(target.strip())


def inspect_markdown(path: Path, repo_root: Path) -> dict[str, Any]:
    rel = path.relative_to(repo_root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    broken: list[dict[str, Any]] = []
    checked = 0
    skipped = 0

    for match in LINK_RE.finditer(text):
        raw = match.group(1)
        target = normalize_target(raw)
        if not target or target.startswith("#") or is_external_link(target):
            skipped += 1
            continue
        if target.startswith(".") or "/" in target or target.endswith((".md", ".py", ".json", ".ps1", ".yml", ".yaml", ".txt")):
            checked += 1
            candidate = (path.parent / target).resolve()
            try:
                candidate.relative_to(repo_root)
            except ValueError:
                broken.append({"target": raw, "reason": "outside_repo"})
                continue
            if not candidate.exists():
                broken.append({"target": raw, "reason": "missing"})
        else:
            skipped += 1

    return {
        "path": rel,
        "ok": not broken,
        "checked_links": checked,
        "skipped_links": skipped,
        "broken_links": broken,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", help="Optional JSON report path.")
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    excludes = set(DEFAULT_EXCLUDES)
    excludes.update(args.exclude)

    files = iter_markdown_files(repo_root, excludes)
    results = [inspect_markdown(path, repo_root) for path in files]
    failed = [item for item in results if not item["ok"]]
    errors = [
        f"{item['path']}: {broken['target']} ({broken['reason']})"
        for item in failed
        for broken in item["broken_links"]
    ]
    report = {
        "schema_version": 1,
        "kind": "docs_links",
        "repo_root": str(repo_root),
        "file_count": len(results),
        "failed_count": len(failed),
        "passed": not failed,
        "errors": errors,
        "warnings": [],
        "results": results,
    }
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
