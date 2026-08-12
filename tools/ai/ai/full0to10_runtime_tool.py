#!/usr/bin/env python3
"""Invoke a Full0To10 runtime tool through a small JSON adapter."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT = Path(__file__).resolve()
AI_DIR = CURRENT.parent
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from full0to10_runtime_tools.memory_adapter import invoke_memory_tool  # noqa: E402
from full0to10_runtime_tools.registry import build_runtime_tool_registry  # noqa: E402


def load_args(raw_json: str | None, args_file: str | None) -> dict[str, object]:
    if args_file:
        return json.loads(Path(args_file).read_text(encoding="utf-8"))
    if raw_json:
        return json.loads(raw_json)
    return {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", help="Tool name or 'list'")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--args-json")
    parser.add_argument("--args-file")
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.tool == "list":
        report = build_runtime_tool_registry(Path(args.repo_root))
    else:
        tool_args = load_args(args.args_json, args.args_file)
        report = invoke_memory_tool(args.tool, tool_args)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
