"""Shared deterministic helpers for agent memory."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
DEFAULT_MAX_MEMORY_CHARS = 24000
DEFAULT_MAX_RECORD_CHARS = 4200
MEMORY_DB_SCHEMA_VERSION = 1
DEFAULT_OPERATIONAL_DB = "output/ai_runtime_memory/operational_context.sqlite"
DEFAULT_PERSISTENT_DB = "indexAI/agent_memory/agent_memory.sqlite"
DEFAULT_SQLITE_OUTPUT = "output/validation/agent_runtime_sqlite_memory.json"
DEFAULT_SQLITE_MARKDOWN = "output/validation/agent_runtime_sqlite_memory.md"

WORD_RE = re.compile(r"[A-Za-z0-9_]{3,}")
SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")
STOP_WORDS = {
    "and",
    "are",
    "but",
    "con",
    "del",
    "dei",
    "della",
    "delle",
    "for",
    "from",
    "gli",
    "json",
    "non",
    "not",
    "per",
    "the",
    "una",
    "uno",
    "with",
}

def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()

def sha256_text(text: str) -> str:
    """Return the SHA-256 hash for text."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()

def clamp_confidence(value: Any) -> float:
    """Return confidence bounded to the supported 0.0-1.0 interval."""
    return max(0.0, min(1.0, float(value)))

def stable_tag_tuple(tags: Iterable[Any]) -> tuple[str, ...]:
    """Return non-empty tags while preserving first-seen order."""
    return tuple(dict.fromkeys(str(tag) for tag in tags if str(tag).strip()))

def json_or_default(raw: str, default: Any) -> Any:
    """Parse a JSON field, returning the provided default for malformed payloads."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default

def compact_text(text: str, limit: int = 900) -> str:
    """Collapse whitespace and trim text to a predictable size."""
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)].rstrip() + "..."

def slugify(value: str, default: str = "agent_state") -> str:
    """Return a filesystem-friendly slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return re.sub(r"_+", "_", slug) or default

def keywords(text: str, limit: int = 32) -> tuple[str, ...]:
    """Extract simple deterministic keywords for local ranking."""
    counts: dict[str, int] = {}
    for match in WORD_RE.finditer(text.lower()):
        word = match.group(0)
        if word in STOP_WORDS or word.isdigit():
            continue
        counts[word] = counts.get(word, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return tuple(word for word, _count in ranked[:limit])

def read_text(path: Path, limit: int = 240000) -> str:
    """Read text defensively for packet construction."""
    return path.read_text(encoding="utf-8", errors="replace")[:limit]

def relative_path(path: Path, repo_root: Path) -> str:
    """Return a stable repository-relative path where possible."""
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path)

def resolve_repo_path(repo_root: Path, value: str | Path) -> Path:
    """Resolve a path against the repository root."""
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()

def is_under(path: Path, parent: Path) -> bool:
    """Return whether path resolves under parent."""
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False

def read_arg_file(repo_root: Path, value: str) -> str:
    """Read an argument file relative to repo root."""
    if not value:
        return ""
    return resolve_repo_path(repo_root, value).read_text(
        encoding="utf-8-sig",
        errors="replace",
    )

def safe_identifier(value: str, default: str) -> str:
    """Return a stable identifier for broker and memory records."""
    text = SAFE_ID_RE.sub("_", str(value or "").strip()).strip("._-")
    return text[:80] or default

def split_csv_values(values: Iterable[str]) -> list[str]:
    """Split comma-separated CLI values while preserving first-seen order."""
    output: list[str] = []
    for value in values:
        for part in str(value).split(","):
            normalized = part.strip()
            if normalized and normalized not in output:
                output.append(normalized)
    return output
