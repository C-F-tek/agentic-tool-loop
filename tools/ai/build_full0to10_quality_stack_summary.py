#!/usr/bin/env python3
"""Build Full0To10 quality stack preflight summary."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT = Path(__file__).resolve()
AI_DIR = CURRENT.parent
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from full0to10_quality_stack.builder import build_quality_stack_summary  # noqa: E402
from full0to10_quality_stack.render import render_markdown  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--search-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = build_quality_stack_summary(Path(args.repo_root), Path(args.search_root))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.markdown_output:
        md = Path(args.markdown_output)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(render_markdown(summary), encoding="utf-8")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
