#!/usr/bin/env python3
"""Build Full0To10 repo quality packet."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT = Path(__file__).resolve()
AI_DIR = CURRENT.parent
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from full0to10_repo_quality.builder import build_repo_quality_packet  # noqa: E402
from full0to10_repo_quality.constants import MAX_DEFAULT_FILES  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--output-file", default="output/validation/full0to10_repo_quality_packet/quality.md")
    parser.add_argument("--tool", default="repo_quality_reader")
    parser.add_argument("--request", default="Read project MD/PY files and produce a repo quality packet.")
    parser.add_argument("--write-output", action="store_true")
    parser.add_argument("--allow-output-outside-output", action="store_true")
    parser.add_argument("--max-files", type=int, default=MAX_DEFAULT_FILES)
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    packet = build_repo_quality_packet(
        Path(args.repo_root),
        Path(args.output_dir),
        args.input,
        args.output_file,
        args.tool,
        args.request,
        bool(args.write_output),
        bool(args.allow_output_outside_output),
        args.max_files,
    )
    text = json.dumps(packet, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if packet["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
