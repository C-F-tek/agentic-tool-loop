#!/usr/bin/env python3
"""Apply allowlisted Full0To10 auto-refactor patch specs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT = Path(__file__).resolve()
AI_DIR = CURRENT.parent
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from full0to10_auto_refactor_apply.applier import apply_patch_specs  # noqa: E402
from full0to10_auto_refactor_apply.render import render_markdown  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--patch-specs", required=True)
    parser.add_argument("--max-specs", type=int, default=200)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = apply_patch_specs(
        Path(args.repo_root),
        Path(args.patch_specs),
        apply=bool(args.apply),
        max_specs=args.max_specs,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.markdown_output:
        md = Path(args.markdown_output)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(render_markdown(report), encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
