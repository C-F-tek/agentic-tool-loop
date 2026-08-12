#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def repo_root_from(start: Path) -> Path:
    cur = start.resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / ".git").exists():
            return candidate
    raise SystemExit(f"[FAIL] Repository root not found from {start}")


def load_or_build_report(repo: Path, report_arg: str, max_lines: int) -> dict[str, Any]:
    report_path = repo / report_arg
    if not report_path.exists():
        builder = repo / "Tools" / "docs" / "build_code_aware_md_coherence.py"
        if not builder.exists():
            raise SystemExit(f"[FAIL] Missing report and builder: {report_path}")
        subprocess.run([
            sys.executable,
            str(builder),
            "--repo-root",
            str(repo),
            "--max-lines",
            str(max_lines),
            "--output",
            report_arg,
            "--markdown-output",
            "output/validation/md_code_coherence_report.md",
        ], cwd=repo, check=True)
    return json.loads(report_path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate code-aware Markdown coherence report thresholds.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--report", default="output/validation/md_code_coherence_report.json")
    parser.add_argument("--max-lines", type=int, default=400)
    parser.add_argument("--max-high", type=int, default=0)
    parser.add_argument("--max-medium", type=int, default=999999)
    parser.add_argument("--output", default="output/validation/md_code_coherence_check.json")
    args = parser.parse_args()

    repo = repo_root_from(Path(args.repo_root))
    report = load_or_build_report(repo, args.report, args.max_lines)
    summary = report.get("summary", {})
    by_severity = summary.get("by_severity", {})
    high = int(by_severity.get("high", 0))
    medium = int(by_severity.get("medium", 0))
    passed = high <= args.max_high and medium <= args.max_medium
    result = {
        "kind": "md_code_coherence_check",
        "passed": passed,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "thresholds": {"max_high": args.max_high, "max_medium": args.max_medium},
        "observed": {"high": high, "medium": medium},
        "errors": [] if passed else [f"threshold exceeded: high={high}/{args.max_high}, medium={medium}/{args.max_medium}"],
        "warnings": [],
    }
    out = repo / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
