#!/usr/bin/env python3
"""Apply Markdown split patch specs in quarantined shadow mode."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT = Path(__file__).resolve()
AI_DIR = CURRENT.parent
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from full0to10_markdown_split.applier import apply_markdown_split_specs  # noqa: E402
from full0to10_markdown_split.render import render_markdown  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--patch-specs", required=True)
    parser.add_argument("--max-specs", type=int, default=200)
    parser.add_argument("--apply-shadow", action="store_true")
    parser.add_argument("--shadow-root")
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown-output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    shadow_root = Path(args.shadow_root).resolve() if args.shadow_root else None
    report = apply_markdown_split_specs(
        repo_root,
        Path(args.patch_specs),
        apply_shadow=bool(args.apply_shadow),
        max_specs=args.max_specs,
        shadow_root=shadow_root,
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
