from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


class ExecutableResolver:
    """Resolve deterministic CLI tools without hard-coding a global PATH."""

    def __init__(self, active_python: Path | None = None) -> None:
        self._active_python = Path(active_python or sys.executable).resolve(strict=False)

    def active_venv_script(self, name: str) -> Path:
        normalized = str(name or "").strip()
        suffix = ".exe" if os.name == "nt" and not normalized.lower().endswith(".exe") else ""
        return self._active_python.parent / f"{normalized}{suffix}"

    def resolve(self, name: str, extra_candidates: tuple[Path, ...] = ()) -> str | None:
        normalized = str(name or "").strip()
        if not normalized:
            return None
        candidates = (self.active_venv_script(normalized), *extra_candidates)
        for candidate in candidates:
            if candidate.exists():
                return str(candidate.resolve(strict=False))
        found = shutil.which(normalized)
        return found or None
