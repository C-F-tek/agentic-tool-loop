#!/usr/bin/env python3
"""Static smoke for LightFull0To10 launcher integration."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_TOKENS = (
    "[string]$RepoRoot",
    "[switch]$LightFull0To10",
    "$LightFull0To10OutputDir",
    "$LightFull0To10NoExternalProbes",
    "$ResolvedLightRepoRoot",
    "IA-CARMINE-LIGHTFULL0TO10-DISPATCH-BEGIN",
    "run_unified_light_full0to10_profile.ps1",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo_root).resolve()
    launcher = repo / "Tools/workflow/run_unified_local_ai_refactor.ps1"
    patcher = repo / "Tools/ai/patch_unified_launcher_light_full0to10.py"
    text = launcher.read_text(encoding="utf-8", errors="replace")
    patcher_text = patcher.read_text(encoding="utf-8", errors="replace") if patcher.exists() else ""
    checks = {
        "launcher_exists": launcher.exists(),
        "patcher_exists": patcher.exists(),
        "required_tokens_present": all(token in text for token in REQUIRED_TOKENS),
        "patcher_adds_repo_root": "add_repo_root_param" in patcher_text,
        "dispatch_uses_resolved_root": "$ResolvedLightRepoRoot" in text,
        "patcher_replaces_existing_dispatch": "replace_existing_dispatch" in patcher_text,
        "patcher_is_idempotent": "if REPOROOT_MARKER in text" in patcher_text and "if LIGHT_PARAM_MARKER in text" in patcher_text,
        "no_git_restore_docs": "git restore docs" not in text.lower() and "git restore docs" not in patcher_text.lower(),
        "calls_light_profile": "run_unified_light_full0to10_profile.ps1" in text,
        "default_no_external_probes": 'LightFull0To10NoExternalProbes") -or $LightFull0To10NoExternalProbes' in text,
    }
    report = {"passed": all(checks.values()), "checks": checks}
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
