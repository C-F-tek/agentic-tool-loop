from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path


logger = logging.getLogger(__name__)


def _preview(value: object, *, limit: int = 300) -> str:
    try:
        return str(value)[:limit]
    except Exception as exc:
        return f"<unstringifiable:{type(exc).__name__}>"


class ExecutableResolver:
    """Resolve deterministic CLI tools without hard-coding a global PATH.

    Provides methods for resolving executable paths from the active Python
    virtual environment's script directory, with fallback to PATH lookup.
    """

    def __init__(self, active_python: Path | None = None) -> None:
        try:
            self._active_python = Path(active_python or sys.executable).resolve(strict=False)
        except TypeError as exc:
            raise TypeError(f"active_python must be path-like; received={_preview(active_python)}") from exc
        except ValueError as exc:
            raise ValueError(f"active_python is invalid; received={_preview(active_python)}") from exc
        except PermissionError as exc:
            raise PermissionError(f"permission denied resolving active_python={_preview(active_python)}: {exc}") from exc
        except OSError as exc:
            raise OSError(f"OS error resolving active_python={_preview(active_python)}: {exc}") from exc

    def active_venv_script(self, name: str) -> Path:
        try:
            normalized = str(name or "").strip()
        except Exception as exc:
            raise ValueError(f"executable name must be stringifiable; error_type={type(exc).__name__}") from exc
        suffix = ".exe" if os.name == "nt" and not normalized.lower().endswith(".exe") else ""
        return self._active_python.parent / f"{normalized}{suffix}"

    def resolve(self, name: str, extra_candidates: tuple[Path, ...] = ()) -> str | None:
        try:
            normalized = str(name or "").strip()
        except Exception as exc:
            logger.debug("Invalid executable name. error_type=%s value=%s", type(exc).__name__, _preview(name))
            return None
        if not normalized:
            return None
        try:
            candidates = (self.active_venv_script(normalized), *extra_candidates)
        except ValueError as exc:
            logger.debug("Invalid executable candidate. name=%s error=%s", _preview(normalized), _preview(exc))
            return None
        for candidate in candidates:
            try:
                candidate_path = Path(candidate)
                if candidate_path.exists():
                    return str(candidate_path.resolve(strict=False))
            except PermissionError:
                logger.warning(
                    "Permission denied resolving executable candidate. name=%s candidate=%s",
                    _preview(normalized),
                    _preview(candidate),
                )
                return None
            except OSError as exc:
                logger.debug(
                    "OS error resolving executable candidate. name=%s candidate=%s error_type=%s",
                    _preview(normalized),
                    _preview(candidate),
                    type(exc).__name__,
                )
                return None
        try:
            found = shutil.which(normalized)
        except PermissionError:
            logger.warning("Permission denied during PATH executable lookup. name=%s", _preview(normalized))
            return None
        except OSError as exc:
            logger.debug(
                "OS error during PATH executable lookup. name=%s error_type=%s",
                _preview(normalized),
                type(exc).__name__,
            )
            return None
        return found or None
