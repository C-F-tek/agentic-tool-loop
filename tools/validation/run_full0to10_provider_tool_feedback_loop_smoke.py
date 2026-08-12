#!/usr/bin/env python3
"""Static smoke for Full0To10 provider tool feedback loop."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    return parser.parse_args()


def main() -> int:
    root = Path(parse_args().repo_root).resolve()
    files = {
        "cli": root / "Tools/ai/build_full0to10_provider_tool_feedback_loop.py",
        "builder": root / "Tools/ai/full0to10_provider_feedback_loop/builder.py",
        "constants": root / "Tools/ai/full0to10_provider_feedback_loop/constants.py",
        "wrapper": root / "Tools/workflow/run_full0to10_light_evidence_only.ps1",
        "profile_constants": root / "Tools/ai/full0to10_light_profile/constants.py",
    }
    texts = {name: read(path) for name, path in files.items()}
    joined = "\n".join(texts.values())
    checks = {
        "required_files_exist": all(path.exists() for path in files.values()),
        "wrapper_has_step": "provider_tool_feedback_loop" in texts["wrapper"],
        "promotion_requires_step": "provider_tool_feedback_loop" in texts["profile_constants"],
        "uses_provider_semantic_input": "provider_telemetry_semantic" in texts["constants"],
        "writes_tool_output_manifest": "TOOL_OUTPUT_MANIFEST_JSON" in texts["cli"],
        "writes_feedback_packet": "FEEDBACK_PACKET_JSON" in texts["cli"],
        "report_only": "report_only" in texts["builder"],
        "top_level_broker_dry_run": '"broker_dry_run_performed": True' in texts["builder"],
        "top_level_broker_execution_false": '"broker_execution_performed": False' in texts["builder"],
        "top_level_request_reinjection_false": '"provider_request_reinjection_performed": False' in texts["builder"],
        "provider_execution_false": '"provider_execution_performed": False' in texts["builder"],
        "no_git_restore_docs": "git restore docs" not in joined.lower(),
    }
    report = {"passed": all(checks.values()), "checks": checks}
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
