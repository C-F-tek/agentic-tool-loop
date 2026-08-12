#!/usr/bin/env python3
"""Build Full0To10 final product quality package artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT = Path(__file__).resolve()
AI_DIR = CURRENT.parent
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from full0to10_final_product_quality.builder import (  # noqa: E402
    build_final_product_quality_package,
    write_json,
)
from full0to10_final_product_quality.constants import (  # noqa: E402
    REPORT_JSON,
    REPORT_MD,
    SUMMARY_JSON,
)
from full0to10_final_product_quality.render import render_quality_package  # noqa: E402


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
    report = build_final_product_quality_package(Path(args.run_root))
    json_path = Path(args.output) if args.output else output_dir / REPORT_JSON
    summary_path = output_dir / SUMMARY_JSON
    md_path = output_dir / REPORT_MD
    write_json(json_path, report)
    write_json(summary_path, report["summary"])
    md_path.write_text(render_quality_package(report), encoding="utf-8")
    report["outputs"] = {
        "json": str(json_path),
        "summary": str(summary_path),
        "markdown": str(md_path),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
