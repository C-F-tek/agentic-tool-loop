#!/usr/bin/env python3
"""Static smoke for Full0To10 light profile promotion."""
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
    root = Path(args.repo_root).resolve()
    wrapper = root / "Tools/workflow/run_unified_light_full0to10_profile.ps1"
    summary = root / "Tools/ai/summarize_full0to10_light_evidence.py"
    wrapper_text = wrapper.read_text(encoding="utf-8", errors="replace")
    summary_text = summary.read_text(encoding="utf-8", errors="replace")
    checks = {
        "wrapper_exists": wrapper.exists(),
        "summary_exists": summary.exists(),
        "calls_light_evidence_run": "run_full0to10_light_evidence_only.ps1" in wrapper_text,
        "calls_summary": "summarize_full0to10_light_evidence.py" in wrapper_text,
        "has_no_external_probes": "NoExternalProbes" in wrapper_text,
        "promotion_report_name": "full0to10_light_evidence_promotion.json" in wrapper_text,
        "summary_checks_provider_false": "provider_execution_performed" in summary_text,
        "summary_checks_patch_false": "patch_application_performed" in summary_text,
        "recommends_light_flag": "-LightFull0To10" in summary_text,
    }
    report = {"passed": all(checks.values()), "checks": checks}
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
