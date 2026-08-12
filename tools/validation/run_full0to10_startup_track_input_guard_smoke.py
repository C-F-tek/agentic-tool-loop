#!/usr/bin/env python3
"""Static smoke test for startup guard track input integration."""
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
    wrapper = repo_root / "Tools/workflow/run_full0to10_startup_check_guard.ps1"
    text = wrapper.read_text(encoding="utf-8", errors="replace")
    checks = {
        "wrapper_exists": wrapper.exists(),
        "has_track_name_param": "$TrackName" in text,
        "has_require_track_inputs": "RequireTrackInputs" in text,
        "calls_track_builder": "build_full0to10_track_input_contract.py" in text,
        "checks_track_exit_code": "$TrackExitCode" in text,
    }
    report = {"passed": all(checks.values()), "checks": checks}
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
