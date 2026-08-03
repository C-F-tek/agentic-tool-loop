from __future__ import annotations

from pathlib import Path
from typing import Protocol


class RepoFilesystem(Protocol):
    """Filesystem port for repo-bounded reads and path checks."""

    @property
    def root(self) -> Path:
        """Resolved repository root."""

    def exists(self, repo_path: str) -> bool:
        """Return whether a repo-relative path exists."""

    def read_text(self, repo_path: str, *, encoding: str = "utf-8") -> str:
        """Read a repo-relative text file."""

    def list_files(self, repo_path: str = ".") -> tuple[str, ...]:
        """List repo-relative file paths under a directory."""
