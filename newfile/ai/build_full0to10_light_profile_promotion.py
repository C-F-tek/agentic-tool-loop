#!/usr/bin/env python3
"""Build Full0To10 light profile promotion artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT = Path(__file__).resolve()
AI_DIR = CURRENT.parent
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from full0to10_light_profile.builder import build_light_profile_promotion  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_light_profile_promotion(Path(args.run_report), Path(args.output_dir))
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
