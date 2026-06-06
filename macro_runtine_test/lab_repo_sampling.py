from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path


TEXT_EXTENSIONS = {
    ".bat",
    ".cfg",
    ".cmd",
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".rs",
    ".sh",
    ".toml",
    ".ts",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    "target",
    "venv",
    "venvs",
    ".venv",
}


@dataclass(frozen=True)
class SampledRepoFiles:
    seed: int
    files: tuple[str, ...]

    def first(self) -> str:
        if not self.files:
            raise RuntimeError("No sample file available from lab repo")
        return self.files[0]


def _is_candidate(path: Path, root: Path, *, max_bytes: int) -> bool:
    try:
        rel_parts = path.relative_to(root).parts
    except ValueError:
        return False
    if any(part in EXCLUDED_DIRS for part in rel_parts):
        return False
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return False
    try:
        if not path.is_file():
            return False
        if path.stat().st_size <= 0 or path.stat().st_size > max_bytes:
            return False
    except OSError:
        return False
    return True


def sample_repo_files(
    lab_repo: Path,
    *,
    seed: int,
    count: int = 6,
    max_bytes: int = 250_000,
) -> SampledRepoFiles:
    root = lab_repo.resolve()
    if not root.exists() or not root.is_dir():
        raise RuntimeError(f"LAB_REPO is not a readable directory: {root}")
    candidates = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if _is_candidate(path, root, max_bytes=max_bytes)
    ]
    candidates = sorted(set(candidates))
    if not candidates:
        raise RuntimeError(f"No readable text files found in LAB_REPO: {root}")
    rng = random.Random(seed)
    rng.shuffle(candidates)
    return SampledRepoFiles(seed=seed, files=tuple(candidates[: max(1, count)]))

