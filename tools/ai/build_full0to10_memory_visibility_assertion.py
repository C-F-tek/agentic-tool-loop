#!/usr/bin/env python3
"""Build Full0To10 memory visibility assertion artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT = Path(__file__).resolve()
AI_DIR = CURRENT.parent
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from full0to10_memory_visibility.constants import REPORT_JSON, REPORT_MD  # noqa: E402
from full0to10_memory_visibility.render import render_memory_visibility  # noqa: E402
from full0to10_memory_visibility.validator import (  # noqa: E402
    build_memory_visibility_assertion,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = build_memory_visibility_assertion(Path(args.repo_root))
    json_path = Path(args.output) if args.output else output_dir / REPORT_JSON
    md_path = output_dir / REPORT_MD
    write_json(json_path, report)
    md_path.write_text(render_memory_visibility(report), encoding="utf-8")
    report["outputs"] = {"json": str(json_path), "markdown": str(md_path)}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
