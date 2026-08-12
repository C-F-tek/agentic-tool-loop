#!/usr/bin/env python3
"""Build Full0To10 effective use optimization artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT = Path(__file__).resolve()
AI_DIR = CURRENT.parent
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from full0to10_effective_use.builder import build_effective_use_optimization  # noqa: E402
from full0to10_effective_use.constants import DEFAULT_REQUEST  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--request", default=DEFAULT_REQUEST)
    parser.add_argument("--db")
    parser.add_argument("--no-external-probes", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=8)
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_effective_use_optimization(
        Path(args.repo_root),
        Path(args.output_dir),
        args.request,
        Path(args.db) if args.db else None,
        no_external_probes=bool(args.no_external_probes),
        timeout_seconds=args.timeout_seconds,
    )
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
