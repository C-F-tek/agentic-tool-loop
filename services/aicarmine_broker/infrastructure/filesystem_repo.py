from __future__ import annotations

from pathlib import Path


def safe_rel_path(value: str) -> str:
    raw = str(value or "").strip().strip("\"'").replace("\\", "/")
    if not raw:
        raise ValueError("empty path")
    if raw.startswith("/") or raw.startswith("../") or "/../" in raw or ":" in raw:
        raise ValueError(f"path must be repo-relative: {raw}")
    return raw


def repo_rel(path: Path, root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(root.resolve(strict=False)).as_posix()
    except Exception:
        return str(path)


class FilesystemRepo:
    """Repo-bounded filesystem adapter."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root).resolve(strict=False)

    @property
    def root(self) -> Path:
        return self._root

    def resolve(self, repo_path: str) -> Path:
        safe = safe_rel_path(repo_path)
        resolved = (self._root / safe).resolve(strict=False)
        try:
            resolved.relative_to(self._root)
        except ValueError as exc:
            raise ValueError(f"path escapes repository root: {repo_path}") from exc
        return resolved

    def exists(self, repo_path: str) -> bool:
        return self.resolve(repo_path).exists()

    def read_text(self, repo_path: str, *, encoding: str = "utf-8") -> str:
        return self.resolve(repo_path).read_text(encoding=encoding)

    def list_files(self, repo_path: str = ".") -> tuple[str, ...]:
        root = self.resolve(repo_path)
        if root.is_file():
            return (repo_rel(root, self._root),)
        return tuple(
            sorted(
                repo_rel(path, self._root)
                for path in root.rglob("*")
                if path.is_file()
            )
        )
