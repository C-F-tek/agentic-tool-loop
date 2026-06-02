"""CLI for runtime SQLite memory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import (
    DEFAULT_OPERATIONAL_DB,
    DEFAULT_PERSISTENT_DB,
    DEFAULT_SQLITE_MARKDOWN,
    DEFAULT_SQLITE_OUTPUT,
    resolve_repo_path,
)
from .sqlite_report import build_report, render_markdown

DEFAULT_MARKDOWN = DEFAULT_SQLITE_MARKDOWN
DEFAULT_OUTPUT = DEFAULT_SQLITE_OUTPUT


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    return resolve_repo_path(repo_root, value)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--action",
        choices=("status", "remember", "search", "clear_operational"),
        default="status",
    )
    parser.add_argument("--scope", choices=("operational", "persistent"), default="operational")
    parser.add_argument("--database", default=DEFAULT_OPERATIONAL_DB)
    parser.add_argument("--persistent-database", default=DEFAULT_PERSISTENT_DB)
    parser.add_argument("--request-id", default="runtime_sqlite_memory")
    parser.add_argument("--summary", default="")
    parser.add_argument("--content", default="")
    parser.add_argument(
        "--content-file",
        default="",
        help="Read remember content from file to avoid long Windows command lines.",
    )
    parser.add_argument("--role", default="doctor_tool")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--query", default="")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--confirm", default="")
    parser.add_argument("--allow-persistent-write", action="store_true")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_report(args)
    output = resolve_path(repo_root, args.output)
    markdown = resolve_path(repo_root, args.markdown_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown),
                "action": report["action"],
                "scope": report["scope"],
                "sqlite_write_performed": report["sqlite_write_performed"],
                "sqlite_search_backend": report["sqlite_search_backend"],
                "sqlite_fts5_enabled": report["sqlite_fts5_enabled"],
                "persistent_memory_write_performed": report["persistent_memory_write_performed"],
                "operational_sqlite_write_performed": report["operational_sqlite_write_performed"],
                "operational_memory_clear_performed": report["operational_memory_clear_performed"],
                "patch_application_performed": report["patch_application_performed"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 2
