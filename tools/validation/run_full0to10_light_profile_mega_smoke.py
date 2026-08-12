#!/usr/bin/env python3
"""Static smoke test for Full0To10 unified light profile mega-loop."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.repo_root).resolve()
    files = {
        "builder": root / "Tools/ai/build_full0to10_light_profile_promotion.py",
        "profile": root / "Tools/workflow/run_unified_light_full0to10_profile.ps1",
        "gate": root / "Tools/workflow/run_full0to10_light_profile_gate.ps1",
        "constants": root / "Tools/ai/full0to10_light_profile/constants.py",
    }
    texts = {name: read(path) if path.exists() else "" for name, path in files.items()}
    checks = {
        "all_files_exist": all(path.exists() for path in files.values()),
        "profile_calls_light_run": "run_full0to10_light_evidence_only.ps1" in texts["profile"],
        "profile_calls_builder": "build_full0to10_light_profile_promotion.py" in texts["profile"],
        "gate_calls_builder": "build_full0to10_light_profile_promotion.py" in texts["gate"],
        "requires_provider_false": "provider_execution_performed" in texts["constants"],
        "requires_patch_false": "patch_application_performed" in texts["constants"],
        "recommends_launcher_flag": "-LightFull0To10" in texts["constants"],
        "no_git_restore_docs": "git restore docs" not in "\n".join(texts.values()),
    }
    report = {"passed": all(checks.values()), "checks": checks}
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
