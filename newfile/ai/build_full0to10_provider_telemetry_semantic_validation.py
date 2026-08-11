#!/usr/bin/env python3
"""Build Full0To10 provider telemetry semantic validation artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT = Path(__file__).resolve()
AI_DIR = CURRENT.parent
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from full0to10_provider_telemetry_semantic.constants import REPORT_JSON, REPORT_MD  # noqa: E402
from full0to10_provider_telemetry_semantic.render import render_validation  # noqa: E402
from full0to10_provider_telemetry_semantic.validator import validate_light_provider_telemetry  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = validate_light_provider_telemetry(Path(args.run_root))
    json_text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    output = Path(args.output) if args.output else output_dir / REPORT_JSON
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json_text, encoding="utf-8")
    (output_dir / REPORT_MD).write_text(render_validation(report), encoding="utf-8")
    print(json_text, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
