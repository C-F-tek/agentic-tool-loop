#!/usr/bin/env python3
"""Check that generated local artifacts are not staged for source commit."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


BLOCKED_PREFIXES = (
    "indexAI/code_chunks/",
    "indexAI/project_code_chunks/",
    "docs/LOCAL_VALIDATION_EVIDENCE/",
)

BLOCKED_SUFFIXES = (
    ".sqlite",
    ".sqlite3",
    ".db",
)


def git_status(repo_root: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "status", "--short"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or proc.stdout.strip())
    return [line for line in proc.stdout.splitlines() if line.strip()]


def parse_path(line: str) -> str:
    value = line[3:] if len(line) > 3 else line
    if " -> " in value:
        value = value.split(" -> ", 1)[1]
    return value.replace("\\", "/").strip().strip('"')


def is_blocked(path: str) -> bool:
    return path.startswith(BLOCKED_PREFIXES) or path.endswith(BLOCKED_SUFFIXES)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    status = git_status(repo_root)
    violations = [{"status": line[:2], "path": parse_path(line)} for line in status if is_blocked(parse_path(line))]
    report = {
        "kind": "full0to10_generated_artifact_quarantine",
        "passed": not violations,
        "violation_count": len(violations),
        "violations": violations,
        "blocked_prefixes": list(BLOCKED_PREFIXES),
        "blocked_suffixes": list(BLOCKED_SUFFIXES),
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
    }
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
