"""CLI entrypoint for AI context packs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .builder import build_evidence, build_pack
from .common import resolve_repo_path, sanitize_filename
from .profiles import (
    DEFAULT_EVIDENCE_DIR,
    DEFAULT_MAX_FILE_CHARS,
    DEFAULT_MAX_TOTAL_CHARS,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PROFILE,
    PROFILES,
)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--profile", default=DEFAULT_PROFILE, choices=sorted(PROFILES))
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--basename", default="")
    parser.add_argument("--max-total-chars", type=int, default=DEFAULT_MAX_TOTAL_CHARS)
    parser.add_argument("--max-file-chars", type=int, default=DEFAULT_MAX_FILE_CHARS)
    parser.add_argument("--evidence-dir", default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--evidence-basename", default="")
    parser.add_argument("--no-evidence", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    basename = sanitize_filename(args.basename or args.profile)
    evidence_basename = sanitize_filename(
        args.evidence_basename or f"{args.profile}_context_pack_evidence"
    )
    output_dir = resolve_repo_path(repo_root, args.output_dir)
    evidence_dir = resolve_repo_path(repo_root, args.evidence_dir)
    pack = build_pack(
        repo_root=repo_root,
        profile_name=args.profile,
        output_dir=output_dir,
        basename=basename,
        max_total_chars=args.max_total_chars,
        max_file_chars=args.max_file_chars,
    )
    evidence = (
        None
        if args.no_evidence
        else build_evidence(pack, repo_root, evidence_dir, evidence_basename)
    )
    print(
        json.dumps(
            {
                "passed": pack["passed"],
                "profile": pack["profile"],
                "pack_json": pack["pack_json"],
                "pack_markdown": pack["pack_markdown"],
                "evidence_json": (None if evidence is None else evidence["evidence_json"]),
                "included_file_count": pack["included_file_count"],
                "truncated_file_count": pack["truncated_file_count"],
                "provider_execution_performed": False,
            },
            indent=2,
        )
    )
    return 0 if pack["passed"] else 2
