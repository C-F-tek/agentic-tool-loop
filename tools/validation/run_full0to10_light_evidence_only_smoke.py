#!/usr/bin/env python3
"""Static smoke test for Full0To10 light evidence-only workflow."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


BAD_PATTERNS = (
    '"- Passed: `',
    '"- Steps: `',
    '"- Failed: `',
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    wrapper = repo_root / "Tools/workflow/run_full0to10_light_evidence_only.ps1"
    text = wrapper.read_text(encoding="utf-8", errors="replace")
    risky_colon_interpolation = bool(re.search(r'"\[[^"]*\]\s+\$[A-Za-z_][A-Za-z0-9_]*:', text))
    bad_markdown_strings = [pattern for pattern in BAD_PATTERNS if pattern in text]
    checks = {
        "wrapper_exists": wrapper.exists(),
        "has_no_external_probes": "NoExternalProbes" in text,
        "calls_repo_quality": "run_full0to10_repo_quality_packet.ps1" in text,
        "calls_track_inputs": "run_full0to10_track_input_contract.ps1" in text,
        "calls_provider_governor": "run_full0to10_provider_governor.ps1" in text,
        "calls_execution_bridge": "run_full0to10_provider_execution_bridge.ps1" in text,
        "writes_json_report": "full0to10_light_evidence_only_run.json" in text,
        "provider_false": "provider_execution_performed = $false" in text,
        "patch_false": "patch_application_performed = $false" in text,
        "uses_safe_formatting": " -f " in text,
        "no_risky_colon_interpolation": not risky_colon_interpolation,
        "no_double_quoted_markdown_backtick_formats": not bad_markdown_strings,
        "uses_markdown_list_builder": "System.Collections.Generic.List[string]" in text,
    }
    report = {"passed": all(checks.values()), "checks": checks, "bad_markdown_strings": bad_markdown_strings}
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
