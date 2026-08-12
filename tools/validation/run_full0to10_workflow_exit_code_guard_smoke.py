#!/usr/bin/env python3
"""Static smoke test for workflow wrapper exit-code guards."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


TARGETS = (
    "Tools/workflow/run_full0to10_auto_refactor_apply.ps1",
    "Tools/workflow/run_full0to10_markdown_split_shadow.ps1",
    "Tools/workflow/run_full0to10_startup_check_guard.ps1",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    return parser.parse_args()


def check(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "path": path.as_posix(),
        "exists": path.exists(),
        "checks_last_exitcode": "$LASTEXITCODE" in text,
        "throws_on_failure": "throw " in text,
        "prints_ok": 'Write-Host "[OK]' in text,
        "passed": path.exists() and "$LASTEXITCODE" in text and "throw " in text,
    }


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    results = [check(repo_root / target) for target in TARGETS]
    report = {"passed": all(item["passed"] for item in results), "results": results}
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
