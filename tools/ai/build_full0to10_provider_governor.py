#!/usr/bin/env python3
"""Build Full0To10 provider governor artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT = Path(__file__).resolve()
AI_DIR = CURRENT.parent
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from full0to10_provider_governor.builder import build_provider_governor  # noqa: E402
from full0to10_provider_governor.constants import DEFAULT_REQUEST  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--request", default=DEFAULT_REQUEST)
    parser.add_argument("--operator-intent", action="store_true")
    parser.add_argument("--allow-provider-generation", action="store_true")
    parser.add_argument("--no-external-probes", action="store_true")
    parser.add_argument("--strict-permit", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=8)
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    governor = build_provider_governor(
        Path(args.repo_root),
        Path(args.output_dir),
        args.request,
        operator_intent=bool(args.operator_intent),
        allow_provider_generation=bool(args.allow_provider_generation),
        no_external_probes=bool(args.no_external_probes),
        timeout_seconds=args.timeout_seconds,
    )
    text = json.dumps(governor, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")

    if args.strict_permit and not governor["run_permit"]["permit_allowed"]:
        return 1
    return 0 if governor["valid_result"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
