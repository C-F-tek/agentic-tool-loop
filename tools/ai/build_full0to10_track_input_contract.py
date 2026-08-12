#!/usr/bin/env python3
"""Build Full0To10 track input contract artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT = Path(__file__).resolve()
AI_DIR = CURRENT.parent
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from full0to10_track_inputs.builder import build_track_input_contract  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--track-name", default="current")
    parser.add_argument("--require-inputs", action="store_true")
    parser.add_argument("--max-candidates", type=int, default=8)
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    contract = build_track_input_contract(
        Path(args.repo_root),
        Path(args.output_dir),
        args.track_name,
        require_inputs=bool(args.require_inputs),
        max_candidates=args.max_candidates,
    )
    text = json.dumps(contract, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if contract["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
