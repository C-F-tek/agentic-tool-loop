"""Archive helpers for semantic evidence chunks."""

from __future__ import annotations

import zipfile
from pathlib import Path

from .common import repo_rel

def write_zip(zip_output: Path, repo_root: Path, paths: list[Path]) -> str:
    zip_output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            if path.exists() and path.is_file():
                zf.write(path, repo_rel(repo_root, path))
    return repo_rel(repo_root, zip_output)
