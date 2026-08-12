#!/usr/bin/env python3
"""Build Full0To10 provider tool feedback loop artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT = Path(__file__).resolve()
AI_DIR = CURRENT.parent
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from full0to10_provider_feedback_loop.builder import (  # noqa: E402
    build_provider_tool_feedback_loop,
    write_json,
)
from full0to10_provider_feedback_loop.constants import (  # noqa: E402
    FEEDBACK_PACKET_JSON,
    REPORT_JSON,
    REPORT_MD,
    TOOL_OUTPUT_MANIFEST_JSON,
)
from full0to10_provider_feedback_loop.render import render_provider_feedback  # noqa: E402


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
    report = build_provider_tool_feedback_loop(Path(args.run_root))
    json_path = Path(args.output) if args.output else output_dir / REPORT_JSON
    write_json(json_path, report)
    write_json(output_dir / TOOL_OUTPUT_MANIFEST_JSON, report["tool_output_manifest"])
    write_json(output_dir / FEEDBACK_PACKET_JSON, report["provider_feedback_packet"])
    md_path = output_dir / REPORT_MD
    md_path.write_text(render_provider_feedback(report), encoding="utf-8")
    report["outputs"] = {
        "json": str(json_path),
        "markdown": str(md_path),
        "tool_output_manifest": str(output_dir / TOOL_OUTPUT_MANIFEST_JSON),
        "provider_feedback_packet": str(output_dir / FEEDBACK_PACKET_JSON),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
