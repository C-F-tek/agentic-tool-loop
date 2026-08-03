from __future__ import annotations

import logging
from pathlib import Path


logger = logging.getLogger(__name__)


def _preview(value: object, *, limit: int = 300) -> str:
    try:
        return str(value)[:limit]
    except Exception as exc:
        return f"<unstringifiable:{type(exc).__name__}>"


def safe_rel_path(value: str) -> str:
    try:
        raw = str(value or "").strip().strip("\"'").replace("\\", "/")
    except Exception as exc:
        raise ValueError(f"path must be stringifiable; error_type={type(exc).__name__}") from exc
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
        try:
            self._root = Path(root).resolve(strict=False)
        except PermissionError as exc:
            raise PermissionError(f"permission denied resolving repository root {root!r}: {exc}") from exc
        except OSError as exc:
            raise OSError(f"OS error resolving repository root {root!r}: {exc}") from exc

    @property
    def root(self) -> Path:
        return self._root

    def resolve(self, repo_path: str) -> Path:
        safe = safe_rel_path(repo_path)
        try:
            resolved = (self._root / safe).resolve(strict=False)
        except PermissionError as exc:
            raise PermissionError(f"permission denied resolving repo path {safe!r}: {exc}") from exc
        except OSError as exc:
            raise OSError(f"OS error resolving repo path {safe!r}: {exc}") from exc
        try:
            resolved.relative_to(self._root)
        except ValueError as exc:
            raise ValueError(f"path escapes repository root: {repo_path}") from exc
        return resolved

    def exists(self, repo_path: str) -> bool:
        try:
            return self.resolve(repo_path).exists()
        except ValueError:
            logger.debug("Invalid repo path in exists(). repo_path=%s", _preview(repo_path))
            return False
        except PermissionError:
            logger.warning("Permission denied in exists(). repo_path=%s", _preview(repo_path))
            return False
        except OSError:
            logger.debug("OS error in exists(). repo_path=%s", _preview(repo_path))
            return False

    def read_text(self, repo_path: str, *, encoding: str = "utf-8") -> str:
        path = self.resolve(repo_path)
        if path.is_dir():
            logger.debug("Repo path is a directory, not a file. repo_path=%s resolved=%s", _preview(repo_path), path)
            raise IsADirectoryError(f"repo path is a directory: {repo_path}")
        try:
            return path.read_text(encoding=encoding)
        except FileNotFoundError:
            logger.debug("Repo file not found. repo_path=%s resolved=%s", _preview(repo_path), path)
            raise
        except IsADirectoryError:
            logger.debug("Repo path is a directory, not a file. repo_path=%s resolved=%s", _preview(repo_path), path)
            raise
        except PermissionError:
            logger.warning("Permission denied reading repo file. repo_path=%s resolved=%s", _preview(repo_path), path)
            raise
        except OSError:
            logger.debug("OS error reading repo file. repo_path=%s resolved=%s", _preview(repo_path), path)
            raise

    def list_files(self, repo_path: str = ".") -> tuple[str, ...]:
        try:
            root = self.resolve(repo_path)
            if not root.exists():
                logger.debug("Repo list root missing. repo_path=%s resolved=%s", _preview(repo_path), root)
                return ()
            if root.is_file():
                return (repo_rel(root, self._root),)
            return tuple(
                sorted(
                    repo_rel(path, self._root)
                    for path in root.rglob("*")
                    if path.is_file()
                )
            )
        except ValueError:
            logger.debug("Invalid repo path in list_files(). repo_path=%s", _preview(repo_path))
            return ()
        except PermissionError:
            logger.warning("Permission denied listing repo files. repo_path=%s", _preview(repo_path))
            return ()
        except OSError:
            logger.debug("OS error listing repo files. repo_path=%s", _preview(repo_path))
            return ()
