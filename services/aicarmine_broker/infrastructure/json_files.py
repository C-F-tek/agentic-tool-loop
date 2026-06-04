from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class JsonFileStore:
    """Small JSON file adapter with atomic replace writes."""

    def read(self, path: Path, default: Any = None) -> Any:
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return default

    def write(self, path: Path, payload: Any) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=str(target.parent),
            text=True,
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
            tmp_path.replace(target)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
        return target
