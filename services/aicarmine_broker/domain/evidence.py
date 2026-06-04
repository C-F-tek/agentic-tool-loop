from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class EvidenceWindow:
    """Real bounded text window consumed by the planner prompt pack."""

    document_id: str
    section: str
    text: str
    window_start: int
    window_end: int
    full_chars: int
    window_chars: int
    complete: bool
    has_more_before: bool
    has_more_after: bool
    sha256: str
    window_sha256: str

    def has_tracking_metadata(self) -> bool:
        return (
            bool(self.document_id)
            and self.window_start >= 0
            and self.window_end >= self.window_start
            and self.full_chars >= self.window_end
            and self.window_chars == len(self.text)
            and bool(self.sha256)
            and bool(self.window_sha256)
        )


@dataclass(frozen=True)
class ToolEvidence:
    """Useful evidence extracted from a successful internal tool result."""

    tool: str
    ok: bool
    target: str = ""
    facts: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceContract:
    """Per-turn validator contract passed to the planner."""

    goal: str
    final_allowed: bool
    required_next_progress: str = ""
    required_next_tool_call: Mapping[str, Any] | None = None
    verified_content_read_count: int = 0
    known_paths: tuple[str, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)
