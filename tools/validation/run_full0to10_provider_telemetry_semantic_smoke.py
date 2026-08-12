#!/usr/bin/env python3
"""Static smoke test for Full0To10 provider telemetry semantic validation."""
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
    args = parse_args()
    root = Path(args.repo_root).resolve()
    files = {
        "cli": root / "Tools/ai/build_full0to10_provider_telemetry_semantic_validation.py",
        "constants": root / "Tools/ai/full0to10_provider_telemetry_semantic/constants.py",
        "validator": root / "Tools/ai/full0to10_provider_telemetry_semantic/validator.py",
        "render": root / "Tools/ai/full0to10_provider_telemetry_semantic/render.py",
        "light_wrapper": root / "Tools/workflow/run_full0to10_light_evidence_only.ps1",
        "profile_constants": root / "Tools/ai/full0to10_light_profile/constants.py",
    }
    texts = {name: read(path) for name, path in files.items()}
    joined = "\n".join(texts.values())
    checks = {
        "required_files_exist": all(path.exists() for path in files.values()),
        "light_wrapper_calls_validator": (
            "build_full0to10_provider_telemetry_semantic_validation.py" in texts["light_wrapper"]
        ),
        "light_wrapper_has_step": "provider_telemetry_semantic" in texts["light_wrapper"],
        "promotion_requires_step": "provider_telemetry_semantic" in texts["profile_constants"],
        "semantic_flags_declared": (
            "REQUIRED_SEMANTIC_FLAGS" in texts["constants"]
            and "gpu0_policy_visible" in texts["constants"]
            and "npu_policy_visible" in texts["constants"]
        ),
        "cli_imports_validator": "validate_light_provider_telemetry" in texts["cli"],
        "cli_writes_markdown": "render_validation" in texts["cli"],
        "validator_checks_no_external_probes": "accelerator_external_probes_disabled" in texts["validator"],
        "no_git_restore_docs": "git restore docs" not in joined.lower(),
    }
    report = {"passed": all(checks.values()), "checks": checks}
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
