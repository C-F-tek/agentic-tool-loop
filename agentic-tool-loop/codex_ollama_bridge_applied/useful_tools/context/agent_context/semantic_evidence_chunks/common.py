"""Shared helpers for semantic evidence chunks."""

from __future__ import annotations

import hashlib
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.validation._shared.report_utils import (
        resolve_output_path,
        write_json_report,
        write_text_report,
    )
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[4]
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.validation._shared.report_utils import (  # type: ignore
        resolve_output_path,
        write_json_report,
        write_text_report,
    )

DEFAULT_OUTPUT_DIR = "docs/LOCAL_VALIDATION_EVIDENCE"
DEFAULT_CHUNK_MAX_CHARS = 12000
DEFAULT_CHUNK_OVERLAP_LINES = 12
DEFAULT_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")
DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http:/127.0.0.1:11434")

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def split_path_values(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        for item in str(value).split(","):
            item = item.strip()
            if item:
                out.append(item)
    return out

def repo_rel(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def read_text(path: Path) -> tuple[str, str | None]:
    try:
        return path.read_text(encoding="utf-8-sig"), None
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8", errors="replace"), None
        except OSError as exc:
            return "", str(exc)
    except OSError as exc:
        return "", str(exc)

def slugify(value: str, default: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    text = re.sub(r"_+", "_", text).strip("._-")
    return text[:90] or default

def compact_text(value: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    return text[:limit] + ("..." if len(text) > limit else "")

def line_count(text: str) -> int:
    return len(text.splitlines())
