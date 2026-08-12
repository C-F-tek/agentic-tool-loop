#!/usr/bin/env python3
"""Static smoke for repo quality wrapper diagnostics."""
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
        "has_diagnostics_only": "DiagnosticsOnly" in text,
        "prints_summary_path": "Repo quality packet JSON target" in text,
        "has_show_packet_summary": "function Show-PacketSummary" in text,
        "prints_passed": "passed:" in text,
        "prints_missing_inputs": "Missing explicit/scanned inputs" in text,
        "captures_python_output": "2>&1" in text,
        "throws_with_summary_path": "See: $Summary" in text,
    }
    report = {"passed": all(checks.values()), "checks": checks}
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
