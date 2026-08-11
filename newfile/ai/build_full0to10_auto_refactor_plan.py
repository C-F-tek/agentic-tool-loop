#!/usr/bin/env python3
"""Build Full0To10 auto-refactor and hardware optimization plan."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT = Path(__file__).resolve()
AI_DIR = CURRENT.parent
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from full0to10_auto_refactor.planner import build_auto_refactor_plan  # noqa: E402
from full0to10_auto_refactor.render import render_markdown  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--scan-root", action="append", dest="scan_roots")
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output")
    parser.add_argument("--patch-specs-output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = build_auto_refactor_plan(Path(args.repo_root), args.scan_roots)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.markdown_output:
        md = Path(args.markdown_output)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(render_markdown(plan), encoding="utf-8")

    if args.patch_specs_output:
        specs = Path(args.patch_specs_output)
        specs.parent.mkdir(parents=True, exist_ok=True)
        specs.write_text(json.dumps(plan["patch_specs"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return 0 if plan["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
