from __future__ import annotations

import argparse
import json
from pathlib import Path

from Tools.ai.runtime_hardware_capability.manifest import build_manifest
from Tools.ai.runtime_hardware_capability.markdown import render_markdown


def resolve_output(repo_root: Path, raw: str | None) -> Path | None:
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/validation/runtime_hardware_capability_manifest.json")
    parser.add_argument("--markdown-output", default="output/validation/runtime_hardware_capability_manifest.md")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    report = build_manifest(repo_root)
    output = resolve_output(repo_root, args.output)
    markdown_output = resolve_output(repo_root, args.markdown_output)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if markdown_output:
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2
