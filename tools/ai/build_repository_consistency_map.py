#!/usr/bin/env python3
"""Build a deterministic repository consistency map before provider review.

The CLI entrypoint stays stable while the path scanner, Markdown scanner,
Python inventory, finding builder and renderer live in
Tools.ai.repository_consistency_map.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from Tools.validation.report_utils import write_json_report, write_text_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.validation.report_utils import write_json_report, write_text_report  # type: ignore

from Tools.ai.repository_consistency_map.builder import build_report  # noqa: E402
from Tools.ai.repository_consistency_map.constants import (  # noqa: E402
    DEFAULT_MARKDOWN,
    DEFAULT_MAX_SNIPPET_CHARS,
    DEFAULT_OUTPUT,
)
from Tools.ai.repository_consistency_map.paths import resolve_path  # noqa: E402
from Tools.ai.repository_consistency_map.render import render_markdown  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    parser.add_argument("--max-detail-items", type=int, default=2000)
    parser.add_argument("--max-snippet-chars", type=int, default=DEFAULT_MAX_SNIPPET_CHARS)
    parser.add_argument("--workers", type=int, default=8, help="Bounded worker count for Markdown/Python repository scans.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    output = resolve_path(repo_root, args.output)
    markdown_output = resolve_path(repo_root, args.markdown_output)
    report = build_report(
        repo_root=repo_root,
        max_detail_items=args.max_detail_items,
        max_snippet_chars=args.max_snippet_chars,
        workers=args.workers,
    )
    write_json_report(report, output)
    write_text_report(render_markdown(report), markdown_output)
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown_output),
                "finding_count": report["finding_count"],
                "severity_counts": report["severity_counts"],
                "markdown_reference_count": report["scope"]["markdown_reference_count"],
                "markdown_python_command_count": report["scope"]["markdown_python_command_count"],
                "provider_execution_performed": report["provider_execution_performed"],
                "patch_application_performed": report["patch_application_performed"],
                "sqlite_write_performed": report["sqlite_write_performed"],
                "workers_requested": report.get("performance", {}).get("workers_requested"),
                "performance": report.get("performance", {}),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
