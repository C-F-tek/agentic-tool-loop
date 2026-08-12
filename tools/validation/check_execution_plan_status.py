#!/usr/bin/env python3
"""Validate execution-plan folder/status consistency.

The active folder must not contain plans whose top-level status is completed or
abandoned. Completed and abandoned plans should live in their matching folders.

Folder README files are documentation, not execution plans, and are ignored.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from report_utils import resolve_output_path, write_json_report

STATUS_RE = re.compile(r"^## Status\s*\n\s*\n(?P<status>[a-zA-Z_ -]+)\s*$", re.MULTILINE)


TERMINAL_STATUSES = {"completed", "abandoned", "wont_fix", "won't_fix"}
ALLOWED_ACTIVE_STATUSES = {"active", "in_progress", "blocked", "planned"}
IGNORED_PLAN_FILENAMES = {"README.md"}


def read_top_level_status(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = STATUS_RE.search(text)
    if not match:
        return "missing"
    return match.group("status").strip().lower().replace(" ", "_")


def iter_plan_files(folder: Path) -> list[Path]:
    return [path for path in sorted(folder.glob("*.md")) if path.name not in IGNORED_PLAN_FILENAMES]


def check_execution_plan_status(repo_root: Path) -> dict[str, object]:
    plans_root = repo_root / "docs" / "EXECUTION_PLANS"
    active_root = plans_root / "active"
    completed_root = plans_root / "completed"
    abandoned_root = plans_root / "abandoned"

    results: list[dict[str, object]] = []
    errors: list[str] = []
    warnings: list[str] = []
    ignored_files: list[str] = []

    for folder_name, folder in (
        ("active", active_root),
        ("completed", completed_root),
        ("abandoned", abandoned_root),
    ):
        if not folder.exists():
            warnings.append(f"missing execution-plan folder: {folder.relative_to(repo_root)}")
            continue
        ignored_files.extend(
            path.relative_to(repo_root).as_posix()
            for path in sorted(folder.glob("*.md"))
            if path.name in IGNORED_PLAN_FILENAMES
        )
        for path in iter_plan_files(folder):
            status = read_top_level_status(path)
            rel_path = path.relative_to(repo_root).as_posix()
            ok = True
            reason = ""
            if folder_name == "active" and status in TERMINAL_STATUSES:
                ok = False
                reason = "terminal-status plan must be moved out of active/"
            elif folder_name == "completed" and status != "completed":
                ok = False
                reason = "completed/ plan must have top-level status completed"
            elif folder_name == "abandoned" and status != "abandoned":
                ok = False
                reason = "abandoned/ plan must have top-level status abandoned"
            elif folder_name == "active" and status != "missing" and status not in ALLOWED_ACTIVE_STATUSES:
                ok = False
                reason = f"active/ plan has unsupported top-level status: {status}"
            if not ok:
                errors.append(f"{rel_path}: {reason}")
            results.append(
                {
                    "path": rel_path,
                    "folder": folder_name,
                    "status": status,
                    "ok": ok,
                    "reason": reason,
                }
            )

    return {
        "schema_version": 1,
        "kind": "execution_plan_status",
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "plan_count": len(results),
            "ignored_files": ignored_files,
            "active_terminal_status_count": sum(
                1 for item in results if item["folder"] == "active" and item["status"] in TERMINAL_STATUSES
            ),
            "results": results,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = check_execution_plan_status(repo_root)
    output = resolve_output_path(repo_root, args.output) if args.output else None
    text = write_json_report(report, output)
    print(text, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
