"""Agent memory record and microtask models with state packet generation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
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
    """Parse a JSON field, returning the fallback for malformed payloads."""
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


def slugify(value: str, fallback: str = "agent_state") -> str:
    """Return a filesystem-friendly slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return re.sub(r"_+", "_", slug) or fallback


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


def safe_identifier(value: str, fallback: str) -> str:
    """Return a stable identifier for broker and memory records."""
    text = SAFE_ID_RE.sub("_", str(value or "").strip()).strip("._-")
    return text[:80] or fallback


def split_csv_values(values: Iterable[str]) -> list[str]:
    """Split comma-separated CLI values while preserving first-seen order."""
    output: list[str] = []
    for value in values:
        for part in str(value).split(","):
            normalized = part.strip()
            if normalized and normalized not in output:
                output.append(normalized)
    return output


@dataclass
class MemoryRecord:
    """A generic memory item selected into an agent state packet."""

    record_id: str
    kind: str
    scope: str
    source: str
    summary: str
    content: str
    tags: tuple[str, ...] = ()
    confidence: float = 1.0
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str | None = None
    expires_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_text(
        cls,
        *,
        kind: str,
        scope: str,
        source: str,
        text: str,
        tags: Iterable[str] = (),
        confidence: float = 1.0,
        max_record_chars: int = DEFAULT_MAX_RECORD_CHARS,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        """Create a memory record from raw text."""
        content = text[:max_record_chars].rstrip()
        identity = f"{kind}:{scope}:{source}:{sha256_text(content)[:16]}"
        return cls(
            record_id=sha256_text(identity)[:20],
            kind=kind,
            scope=scope,
            source=source,
            summary=compact_text(content, 900),
            content=content,
            tags=stable_tag_tuple(tags),
            confidence=clamp_confidence(confidence),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_mapping(cls, payload: Any) -> MemoryRecord | None:
        """Load a memory record from a mapping, tolerating older shapes."""
        if not isinstance(payload, dict):
            return None
        content = str(payload.get("content") or payload.get("summary") or "")
        source = str(payload.get("source") or payload.get("path") or "unknown")
        kind = str(payload.get("kind") or "memory")
        scope = str(payload.get("scope") or "project")
        tags = payload.get("tags") if isinstance(payload.get("tags"), list) else []
        record_id = str(
            payload.get("record_id") or sha256_text(f"{kind}:{scope}:{source}:{content}")[:20]
        )
        return cls(
            record_id=record_id,
            kind=kind,
            scope=scope,
            source=source,
            summary=str(payload.get("summary") or compact_text(content, 900)),
            content=content,
            tags=tuple(str(tag) for tag in tags),
            confidence=clamp_confidence(payload.get("confidence", 1.0)),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=payload.get("updated_at"),
            expires_at=payload.get("expires_at"),
            metadata=dict(payload.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        data = asdict(self)
        data["tags"] = list(self.tags)
        return data


@dataclass
class AgentMicroTask:
    """A planned unit of work for an app or specialized agent lane."""

    task_id: str
    title: str
    lane: str
    purpose: str
    priority: int = 5
    blocking: bool = False
    status: str = "planned"
    inputs: tuple[str, ...] = ()
    expected_outputs: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        data = asdict(self)
        data["inputs"] = list(self.inputs)
        data["expected_outputs"] = list(self.expected_outputs)
        data["depends_on"] = list(self.depends_on)
        return data


def build_state_packet(
    records: list[MemoryRecord],
    objective: str,
    query: str = "",
    limit: int = 80,
    max_memory_chars: int = 24000,
) -> dict[str, Any]:
    """Build an agent state packet from memory records."""
    sorted_records = sorted(records, key=lambda r: r.confidence if r.confidence else 0.0, reverse=True)[:limit]
    
    packet_content_parts: list[str] = []
    total_chars = 0
    
    for record in sorted_records:
        record_text = f"record_id:{record.record_id} kind:{record.kind} scope:{record.scope} source:{record.source}\nsummary:{record.summary}\ncontent:{record.content[:500]}..."
        if total_chars + len(record_text) > max_memory_chars:
            break
        packet_content_parts.append(record_text)
        total_chars += len(record_text)
    
    return {
        "objective": objective,
        "query": query,
        "records_count": len(sorted_records),
        "packet_content": "\n\n".join(packet_content_parts),
        "max_memory_chars": max_memory_chars,
    }


__all__ = [
    # Common helpers
    "SCHEMA_VERSION",
    "DEFAULT_MAX_MEMORY_CHARS",
    "DEFAULT_MAX_RECORD_CHARS",
    "MEMORY_DB_SCHEMA_VERSION",
    "DEFAULT_OPERATIONAL_DB",
    "DEFAULT_PERSISTENT_DB",
    "DEFAULT_SQLITE_OUTPUT",
    "DEFAULT_SQLITE_MARKDOWN",
    "utc_now_iso",
    "sha256_text",
    "clamp_confidence",
    "stable_tag_tuple",
    "json_or_default",
    "compact_text",
    "slugify",
    "keywords",
    "read_text",
    "relative_path",
    "resolve_repo_path",
    "is_under",
    "read_arg_file",
    "safe_identifier",
    "split_csv_values",
    # Models
    "MemoryRecord",
    "AgentMicroTask",
    # State packet generation
    "build_state_packet",
]