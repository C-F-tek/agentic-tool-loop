#!/usr/bin/env python3
"""Static smoke for Full0To10 final product quality package."""
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
        "cli": root / "Tools/ai/build_full0to10_final_product_quality_package.py",
        "builder": root / "Tools/ai/full0to10_final_product_quality/builder.py",
        "constants": root / "Tools/ai/full0to10_final_product_quality/constants.py",
        "render": root / "Tools/ai/full0to10_final_product_quality/render.py",
        "wrapper": root / "Tools/workflow/run_full0to10_light_evidence_only.ps1",
        "profile_constants": root / "Tools/ai/full0to10_light_profile/constants.py",
    }
    texts = {name: read(path) for name, path in files.items()}
    joined = "\n".join(texts.values())
    checks = {
        "required_files_exist": all(path.exists() for path in files.values()),
        "wrapper_has_step": "final_product_quality_package" in texts["wrapper"],
        "promotion_requires_step": "final_product_quality_package" in texts["profile_constants"],
        "checks_final_product": "final_product.from_cli.json" in texts["constants"],
        "checks_provider_feedback": "provider_tool_feedback_loop" in texts["constants"],
        "checks_memory_visibility": "memory_visibility_assertion" in texts["constants"],
        "has_visibility_summary": "full0to10_final_product_quality_summary" in texts["builder"],
        "provider_execution_false": '"provider_execution_performed": False' in texts["builder"],
        "patch_application_false": '"patch_application_performed": False' in texts["builder"],
        "no_git_restore_docs": "git restore docs" not in joined.lower(),
    }
    report = {"passed": all(checks.values()), "checks": checks}
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
