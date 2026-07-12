"""CLI for agent memory routing policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from Tools.validation._shared.report_utils import write_json_report

from .common import resolve_repo_path
from .routing_requests import DEFAULT_BROKER_REQUEST, DEFAULT_MARKDOWN, DEFAULT_OUTPUT
from .routing_report import build_policy, render_markdown


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    return resolve_repo_path(repo_root, value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--objective", required=True)
    parser.add_argument(
        "--profile", choices=("basic", "refactor", "full_refactor"), default="basic"
    )
    parser.add_argument("--persistent-query", action="append", default=[])
    parser.add_argument("--operational-query", action="append", default=[])
    parser.add_argument("--remember-note", action="append", default=[])
    parser.add_argument("--promotion-candidate", action="append", default=[])
    parser.add_argument("--memory-search-limit", type=int, default=8)
    parser.add_argument("--clear-operational", action="store_true")
    parser.add_argument("--broker-request-output", default=DEFAULT_BROKER_REQUEST)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_policy(args)
    output = resolve_path(repo_root, args.output)
    markdown = resolve_path(repo_root, args.markdown_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    write_json_report(report, output)
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown),
                "broker_request_transport": report["broker_request_transport"],
                "tool_request_count": report["memory_plan"]["tool_request_count"],
                "persistent_query_count": report["memory_plan"]["persistent_query_count"],
                "operational_query_or_write_count": report["memory_plan"][
                    "operational_query_or_write_count"
                ],
                "provider_execution_performed": report["provider_execution_performed"],
                "patch_application_performed": report["patch_application_performed"],
                "sqlite_write_performed": report["sqlite_write_performed"],
                "persistent_memory_write_performed": report["persistent_memory_write_performed"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0
