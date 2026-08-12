#!/usr/bin/env python3
"""Smoke test for final product import graph."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    ai_dir = repo_root / "Tools" / "ai"
    if str(ai_dir) not in sys.path:
        sys.path.insert(0, str(ai_dir))

    imported = {}
    modules = [
        "full0to10_provider_invocation_plan.builder",
        "full0to10_provider_execution_bridge.builder",
        "full0to10_final_product.builder",
    ]
    for name in modules:
        __import__(name)
        imported[name] = True

    print(json.dumps({"passed": True, "imported": imported}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
