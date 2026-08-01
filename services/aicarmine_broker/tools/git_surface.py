from __future__ import annotations

from aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

import subprocess
from pathlib import Path

from aicarmine_broker.infrastructure.filesystem_repo import repo_rel


def git_candidate_files(repo_root: Path, base: Path) -> list[Path] | None:
    """Return Git/.gitignore-visible files under base, or None outside Git."""

    repo_root = Path(repo_root).resolve(strict=False)
    base = Path(base).resolve(strict=False)
    try:
        rel = base.relative_to(repo_root)
    except ValueError:
        return None

    if base.is_file():
        pathspec = rel.as_posix()
    else:
        pathspec = "." if str(rel) == "." else rel.as_posix().rstrip("/") + "/"

    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
                pathspec,
            ],
            check=False,
            capture_output=True,
            text=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None

    paths: list[Path] = []
    seen: set[str] = set()
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        rel_text = raw.decode("utf-8", errors="surrogateescape")
        full = (repo_root / rel_text).resolve(strict=False)
        try:
            full.relative_to(repo_root)
        except ValueError:
            continue
        if not full.is_file():
            continue
        key = repo_rel(full, repo_root)
        if key in seen:
            continue
        seen.add(key)
        paths.append(full)
    return sorted(paths, key=lambda path: repo_rel(path, repo_root).lower())
