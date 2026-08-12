#!/usr/bin/env python3
"""Static smoke test for Markdown split shadow quarantine."""
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
    wrapper = repo_root / "Tools/workflow/run_full0to10_markdown_split_shadow.ps1"
    text = wrapper.read_text(encoding="utf-8", errors="replace")
    checks = {
        "wrapper_exists": wrapper.exists(),
        "passes_shadow_root": "--shadow-root" in text,
        "requires_output_validation": "output/validation" in text,
        "checks_exit_code": "$LASTEXITCODE" in text,
        "throws_on_unsafe_shadow": "Assert-ShadowRootSafe" in text,
    }
    report = {"passed": all(checks.values()), "checks": checks}
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
