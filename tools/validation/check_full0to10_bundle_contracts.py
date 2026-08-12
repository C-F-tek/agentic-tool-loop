#!/usr/bin/env python3
"""CLI wrapper for Full0To10 bundle contract validation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT = Path(__file__).resolve()
VALIDATION_DIR = CURRENT.parent
if str(VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(VALIDATION_DIR))

from full0to10_contracts.render import render_markdown  # noqa: E402
from full0to10_contracts.validator import build_report  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--bundle", help="Compact Full0To10/shared toolbox bundle JSON")
    parser.add_argument("--evidence-dir", default="docs/LOCAL_VALIDATION_EVIDENCE")
    parser.add_argument("--output", required=True, help="JSON report output path")
    parser.add_argument("--markdown-output", help="Optional Markdown report output path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    bundle_path = Path(args.bundle).resolve() if args.bundle else None
    evidence_dir = Path(args.evidence_dir)
    report = build_report(repo_root, bundle_path, evidence_dir)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.markdown_output:
        markdown = Path(args.markdown_output)
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(render_markdown(report), encoding="utf-8")

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
