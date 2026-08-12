#!/usr/bin/env python3
"""Smoke test for controlled Full0To10 refactor applier."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], repo_root: Path) -> dict[str, object]:
    proc = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, check=False)
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
    output_flag = cmd.index("--output") + 1
    return json.loads(Path(cmd[output_flag]).read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--work-dir", default="output/validation/full0to10_controlled_refactor_applier_smoke")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    work_dir = repo_root / args.work_dir
    sample_root = work_dir / "repo"
    sample_root.mkdir(parents=True, exist_ok=True)
    sample = sample_root / "sample.py"
    sample.write_text("x = 1   \nprint(x)", encoding="utf-8")
    specs = work_dir / "patch_specs.json"
    specs.write_text(json.dumps([
        {"candidate_kind": "safe_cleanup_trailing_whitespace", "target_path": "sample.py"},
        {"candidate_kind": "safe_cleanup_final_newline", "target_path": "sample.py"},
        {"candidate_kind": "code_split_candidate", "target_path": "sample.py"},
    ], indent=2), encoding="utf-8")

    cli = repo_root / "Tools/ai/apply_full0to10_auto_refactor_patch_specs.py"
    dry = run([
        sys.executable, str(cli), "--repo-root", str(sample_root), "--patch-specs", str(specs),
        "--output", str(work_dir / "dry.json"), "--markdown-output", str(work_dir / "dry.md"),
    ], repo_root)
    applied = run([
        sys.executable, str(cli), "--repo-root", str(sample_root), "--patch-specs", str(specs), "--apply",
        "--output", str(work_dir / "apply.json"), "--markdown-output", str(work_dir / "apply.md"),
    ], repo_root)

    text = sample.read_text(encoding="utf-8")
    summary = {
        "passed": dry["changed_count"] >= 1 and applied["applied_count"] >= 1 and text.endswith("\n"),
        "dry_changed": dry["changed_count"],
        "applied": applied["applied_count"],
        "rejected": applied["rejected_count"],
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
