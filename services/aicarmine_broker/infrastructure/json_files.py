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


def same_tool_artifact_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Load the full JSON only for the same successful tool result."""
    if not isinstance(result, dict) or not result.get("ok"):
        return result if isinstance(result, dict) else {}
    artifact = str(result.get("artifact") or "")
    if not artifact:
        return result
    try:
        artifact_path = Path(artifact)
        if not artifact_path.exists() or not artifact_path.is_file():
            return result
        loaded = json.loads(artifact_path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return result
    if not isinstance(loaded, dict):
        return result
    expected_tool = str(result.get("tool") or "")
    loaded_tool = str(loaded.get("tool") or "")
    if expected_tool and loaded_tool and expected_tool != loaded_tool:
        return result
    return loaded
