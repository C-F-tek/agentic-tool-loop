#!/usr/bin/env python3
"""Static smoke for Full0To10 memory visibility assertion."""
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
        "cli": root / "Tools/ai/build_full0to10_memory_visibility_assertion.py",
        "validator": root / "Tools/ai/full0to10_memory_visibility/validator.py",
        "constants": root / "Tools/ai/full0to10_memory_visibility/constants.py",
        "wrapper": root / "Tools/workflow/run_full0to10_light_evidence_only.ps1",
        "profile_constants": root / "Tools/ai/full0to10_light_profile/constants.py",
    }
    texts = {name: read(path) for name, path in files.items()}
    joined = "\n".join(texts.values())
    checks = {
        "required_files_exist": all(path.exists() for path in files.values()),
        "wrapper_has_step": "memory_visibility_assertion" in texts["wrapper"],
        "promotion_requires_step": "memory_visibility_assertion" in texts["profile_constants"],
        "checks_operational_context": "operational_context.sqlite" in texts["constants"],
        "checks_agent_memory": "agent_memory.sqlite" in texts["constants"],
        "does_not_read_db_content": "content_read_performed" in texts["validator"],
        "persistent_write_false": "persistent_memory_write_performed" in texts["validator"],
        "no_git_restore_docs": "git restore docs" not in joined.lower(),
    }
    report = {"passed": all(checks.values()), "checks": checks}
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
