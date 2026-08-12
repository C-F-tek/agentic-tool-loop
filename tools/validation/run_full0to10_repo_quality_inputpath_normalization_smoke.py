#!/usr/bin/env python3
"""Static smoke test for repo quality InputPath normalization."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    wrapper = repo_root / "Tools/workflow/run_full0to10_repo_quality_packet.ps1"
    text = wrapper.read_text(encoding="utf-8", errors="replace")
    checks = {
        "wrapper_exists": wrapper.exists(),
        "has_normalize_function": "function Normalize-InputPaths" in text,
        "splits_comma": "-split \"[,;`r`n]+\"" in text,
        "uses_normalized_count": "Normalized input count" in text,
        "passes_normalized_inputs": "$NormalizedInputPath" in text,
    }
    report = {"passed": all(checks.values()), "checks": checks}
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
