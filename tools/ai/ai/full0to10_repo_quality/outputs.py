"""Output handling for repo quality packet."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import ensure_dir, repo_relative, resolve_path, under_output


def output_allowed(repo_root: Path, output_file: Path, allow_outside_output: bool) -> bool:
    return allow_outside_output or under_output(output_file, repo_root)


def write_user_output(
    repo_root: Path,
    output_file_raw: str,
    packet: dict[str, Any],
    markdown: str,
    write_output: bool,
    allow_outside_output: bool,
) -> dict[str, Any]:
    output_file = resolve_path(repo_root, output_file_raw)
    allowed = output_allowed(repo_root, output_file, allow_outside_output)
    manifest = {
        "path": repo_relative(output_file, repo_root),
        "requested": bool(output_file_raw),
        "written": False,
        "allowed": allowed,
        "under_output": under_output(output_file, repo_root),
        "errors": [] if allowed else ["output outside output root"],
    }
    if write_output and allowed:
        ensure_dir(output_file.parent)
        if output_file.suffix.lower() == ".json":
            output_file.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        else:
            output_file.write_text(markdown, encoding="utf-8")
        manifest["written"] = True
    return manifest
