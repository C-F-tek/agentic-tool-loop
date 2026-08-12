from __future__ import annotations

import argparse
import json
from pathlib import Path

from Tools.ai.full_run_bundle_zip.builder import build_full_run_bundle
from Tools.ai.full_run_bundle_zip.paths import resolve_repo_path, split_values
from Tools.ai.full_run_bundle_zip.policy import DEFAULT_EVIDENCE_DIR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--stamp", required=True)
    parser.add_argument("--basename", default=None)
    parser.add_argument("--output-dir", default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--artifact-root", action="append", default=[])
    parser.add_argument("--required-artifact", action="append", default=[])
    parser.add_argument("--required-recursive-root", action="append", default=[])
    parser.add_argument("--no-default-recursive-roots", action="store_true")
    parser.add_argument("--no-default-stamp-files", action="store_true")
    parser.add_argument("--no-git-status", action="store_true")
    parser.add_argument("--allow-output-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    output_dir = resolve_repo_path(repo_root, args.output_dir)
    basename = args.basename or f"full_run_evidence_bundle_{args.stamp}"
    report = build_full_run_bundle(
        repo_root=repo_root,
        stamp=args.stamp,
        basename=basename,
        evidence_dir=output_dir,
        artifacts=split_values(args.artifact),
        artifact_roots=split_values(args.artifact_root),
        required_artifacts=split_values(args.required_artifact),
        required_roots=split_values(args.required_recursive_root),
        include_default_recursive_roots=not args.no_default_recursive_roots,
        include_default_stamp_files=not args.no_default_stamp_files,
        include_git_status=not args.no_git_status,
        allow_output=bool(args.allow_output_artifacts),
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2
