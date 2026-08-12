#!/usr/bin/env python3
"""Inspect Blender package folders under Scripting/."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from Tools.validation.report_utils import count_file_lines
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.validation.report_utils import count_file_lines


SKIP_DIRS = {"shared", "__pycache__"}
SKIP_NAME_PARTS = ("_backup", "_backgood", "_bak")


def inspect_package(path: Path, scripting_root: Path) -> dict[str, Any]:
    python_files = sorted(path.glob("*.py"))
    readme = path / "README.md"
    config = path / "config.py"
    main_candidates = [item for item in python_files if item.name == "main.py" or item.name.startswith("main_")]
    encode_candidates = [item for item in python_files if "encode" in item.name.lower() or "ffmpeg" in item.name.lower()]

    warnings: list[str] = []
    if not readme.exists():
        warnings.append("missing README.md")
    if not main_candidates:
        warnings.append("missing obvious main entry point")
    if not config.exists() and path.name not in {"v61b"}:
        warnings.append("missing config.py or documented equivalent")
    if not encode_candidates:
        warnings.append("no local encode helper detected")

    return {
        "package": path.relative_to(scripting_root).as_posix(),
        "path": path.as_posix(),
        "readme": readme.exists(),
        "config": config.exists(),
        "python_file_count": len(python_files),
        "main_candidates": [item.name for item in main_candidates],
        "encode_candidates": [item.name for item in encode_candidates],
        "line_counts": {item.name: count_file_lines(item, encoding="utf-8")[0] for item in python_files},
        "warnings": warnings,
        "status": "ok" if not warnings else "review",
    }


def should_skip_package_dir(path: Path) -> bool:
    name = path.name.lower()
    if path.name in SKIP_DIRS or path.name.startswith("."):
        return True
    return any(marker in name for marker in SKIP_NAME_PARTS)


def iter_packages(scripting_root: Path) -> list[Path]:
    packages: list[Path] = []
    for item in sorted(scripting_root.iterdir()):
        if not item.is_dir() or should_skip_package_dir(item):
            continue
        if any(item.glob("*.py")) or (item / "README.md").exists():
            packages.append(item)
    return packages


def flatten_warnings(packages: list[dict[str, Any]]) -> list[str]:
    items: list[str] = []
    for package in packages:
        for warning in package.get("warnings", []):
            items.append(f"{package['package']}: {warning}")
    return items


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", help="Optional JSON report path.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when warnings are found.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    scripting_root = repo_root / "Scripting"
    if not scripting_root.is_dir():
        raise SystemExit(f"Scripting directory not found: {scripting_root}")

    packages = [inspect_package(path, scripting_root) for path in iter_packages(scripting_root)]
    warnings = flatten_warnings(packages)
    errors = warnings if args.strict else []
    report = {
        "schema_version": 1,
        "kind": "package_structure",
        "repo_root": repo_root.as_posix(),
        "scripting_root": scripting_root.as_posix(),
        "package_count": len(packages),
        "warning_count": len(warnings),
        "passed": not errors,
        "strict": args.strict,
        "errors": errors,
        "warnings": warnings,
        "packages": packages,
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
