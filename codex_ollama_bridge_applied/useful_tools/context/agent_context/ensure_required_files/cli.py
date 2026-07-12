#!/usr/bin/env python3
"""Ensure required AI context files exist before heap/context reload.

This tool reads required files from ia_carmine.context.agent_context.ai_context_pack and creates
only known compact Markdown routing documents when a required path is truly
missing. Directory-form Markdown docs such as docs/PROJECT_STATUS_POINT.md/
are treated as existing when they contain README.md or part-*.md, matching
build_ai_context_pack split Markdown support.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from ia_carmine._shared.ensure_ai_context_templates import KNOWN_MARKDOWN_TEMPLATES
except ModuleNotFoundError:
    from ia_carmine._shared.ensure_ai_context_templates import KNOWN_MARKDOWN_TEMPLATES


def repo_rel(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return path.as_posix()


def split_markdown_parts(path: Path) -> list[Path]:
    if not path.is_dir() or not path.name.endswith(".md"):
        return []
    parts: list[Path] = []
    readme = path / "README.md"
    if readme.is_file():
        parts.append(readme)
    parts.extend(sorted(item for item in path.glob("part-*.md") if item.is_file()))
    return parts


def required_path_exists(path: Path) -> bool:
    if path.is_file():
        return True
    return bool(split_markdown_parts(path))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Required AI Context Files",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Profile: `{report['profile']}`",
        f"- Apply: `{report['apply']}`",
        f"- Created count: `{len(report['created_files'])}`",
        f"- Existing split-doc count: `{len(report['existing_split_docs'])}`",
        f"- Missing unhandled count: `{len(report['missing_unhandled'])}`",
        "",
        "## Required files",
        "",
    ]
    for item in report["required_files"]:
        lines.append(
            f"- `{item['path']}` exists_before=`{item['exists_before']}` "
            f"exists_after=`{item['exists_after']}` split_doc=`{item['split_doc']}` "
            f"created=`{item['created']}` allowed=`{item['initializable']}`"
        )
    if report["missing_unhandled"]:
        lines.extend(["", "## Missing unhandled", ""])
        for item in report["missing_unhandled"]:
            lines.append(f"- `{item}`")
    return "\n".join(lines) + "\n"


def load_profiles(repo_root: Path) -> dict[str, Any]:
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    module = importlib.import_module("ia_carmine.context.agent_context.ai_context_pack")
    profiles = getattr(module, "PROFILES", {})
    return profiles if isinstance(profiles, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--profile", default="project_self_improvement")
    parser.add_argument("--output", default="output/validation/required_ai_context_files.json")
    parser.add_argument(
        "--markdown-output", default="output/validation/required_ai_context_files.md"
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    profiles = load_profiles(repo_root)
    profile = profiles.get(args.profile)
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(profile, dict):
        errors.append(f"unknown context pack profile: {args.profile}")
        profile = {}

    required_items = [
        item
        for item in profile.get("required_files", [])
        if isinstance(item, dict) and str(item.get("path") or "").strip()
    ]
    required_reports: list[dict[str, Any]] = []
    created_files: list[str] = []
    existing_split_docs: list[str] = []
    missing_unhandled: list[str] = []

    for item in required_items:
        rel_path = str(item.get("path") or "").strip().replace("\\", "/")
        target = repo_root / rel_path
        exists_before = required_path_exists(target)
        split_doc = bool(split_markdown_parts(target))
        initializable = rel_path in KNOWN_MARKDOWN_TEMPLATES
        created = False

        if split_doc:
            existing_split_docs.append(rel_path)

        if not exists_before:
            if initializable and not target.exists():
                if args.apply:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(
                        KNOWN_MARKDOWN_TEMPLATES[rel_path].rstrip() + "\n",
                        encoding="utf-8",
                        newline="\n",
                    )
                    created = True
                    created_files.append(rel_path)
                else:
                    warnings.append(f"would initialize missing required context file: {rel_path}")
            elif initializable and target.exists() and target.is_dir():
                # A directory exists but is not a valid split Markdown doc. Do not overwrite it.
                missing_unhandled.append(rel_path)
            else:
                missing_unhandled.append(rel_path)

        exists_after = required_path_exists(target)
        required_reports.append(
            {
                "path": rel_path,
                "role": item.get("role", ""),
                "exists_before": exists_before,
                "exists_after": exists_after,
                "split_doc": split_doc,
                "initializable": initializable,
                "created": created,
            }
        )

    if missing_unhandled:
        errors.append(
            "missing required context files without safe initializer: "
            + ", ".join(missing_unhandled)
        )

    report = {
        "schema_version": 1,
        "kind": "required_ai_context_files",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": repo_root.as_posix(),
        "profile": args.profile,
        "apply": bool(args.apply),
        "passed": not errors,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": bool(created_files),
        "created_files": created_files,
        "existing_split_docs": existing_split_docs,
        "missing_unhandled": missing_unhandled,
        "required_files": required_reports,
        "errors": errors,
        "warnings": warnings,
    }

    output = (repo_root / args.output).resolve()
    markdown_output = (repo_root / args.markdown_output).resolve()
    write_json(output, report)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                **report,
                "output": repo_rel(repo_root, output),
                "markdown_output": repo_rel(repo_root, markdown_output),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
