"""Agent memory record and microtask models."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

from .common import (
    DEFAULT_MAX_RECORD_CHARS,
    clamp_confidence,
    compact_text,
    sha256_text,
    stable_tag_tuple,
    utc_now_iso,
)

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
