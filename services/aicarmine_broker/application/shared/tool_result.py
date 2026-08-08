# Result types for tool functions - replaces repetitive dict patterns
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ToolResult:
    """Structured result for tool functions.

    Accepts arbitrary extra kwargs via cls_ok_result/cls_error_result
    and stores them in context_for_30b so that tool-specific fields
    (path, mode, query, etc.) do not raise TypeError.
    """
    ok: bool = True
    tool: str = ""
    summary: str = ""
    artifact: str | None = None
    artifacts: list[str] = field(default_factory=list)
    answer_for_30b: str = ""
    context_for_30b: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    details: str = ""
    # Generic fields for tool-specific data (count, items, etc.)
    count: int = 0
    requested_count: int = 0
    max_paths: int = 0
    success_count: int = 0
    failed_count: int = 0
    all_ok: bool = False
    items: list[Any] = field(default_factory=list)
    input_keys: list[str] = field(default_factory=list)

    def __new__(cls, *args, **kwargs):
        """Prevent direct construction with unknown kwargs."""
        return super().__new__(cls)

    @classmethod
    def ok_result(cls_self, *, tool: str = "", summary: str = "", **kwargs: Any):
        ctx = dict(kwargs) if kwargs else {}
        return cls_self(ok=True, tool=tool, summary=summary, context_for_30b=ctx)

    @classmethod
    def error_result(cls_self, *, tool: str = "", error: str = "", details: str = "", **kwargs: Any):
        ctx = dict(kwargs) if kwargs else {}
        return cls_self(
            ok=False,
            tool=tool,
            summary=error,
            error=error,
            details=details,
            context_for_30b=ctx,
        )


@dataclass(slots=True)
class PromptWindow:
    """Bounded text window with offsets and hashes."""
    text: str = ""
    window_start: int = 0
    window_end: int = 0
    full_chars: int = 0
    window_chars: int = 0
    complete: bool = True
    has_more_before: bool = False
    has_more_after: bool = False
    sha256: str = ""
    window_sha256: str = ""

    @classmethod
    def from_full_text(cls_self, text: str, *, query: str = "", max_chars: int = 3000):
        """Create a PromptWindow from full text with query-based positioning."""
        import hashlib
        import re

        full = str(text or "")
        budget = max(500, int(max_chars or 3000))
        sha256 = hashlib.sha256(full.encode("utf-8", errors="replace")).hexdigest()

        if len(full) <= budget:
            return cls_self(
                text=full,
                window_start=0,
                window_end=len(full),
                full_chars=len(full),
                window_chars=len(full),
                complete=True,
                has_more_before=False,
                has_more_after=False,
                sha256=sha256,
                window_sha256=sha256,
            )

        start = 0
        tokens = re.findall(r"[A-Za-z0-9_./-]{4,}", str(query or ""))
        for token in tokens[:12]:
            idx = full.lower().find(token.lower())
            if idx >= 0:
                start = max(0, idx - budget // 3)
                break

        end = min(len(full), start + budget)
        start = max(0, end - budget)
        window = full[start:end]

        return cls_self(
            text=window,
            window_start=start,
            window_end=end,
            full_chars=len(full),
            window_chars=len(window),
            complete=False,
            has_more_before=start > 0,
            has_more_after=end < len(full),
            sha256=sha256,
            window_sha256=hashlib.sha256(window.encode("utf-8", errors="replace")).hexdigest(),
        )


@dataclass(slots=True)
class DiagnosticResult:
    """Diagnostic result for error tracking."""
    schema_version: str = "diagnostic.v1"
    diagnostic_only: bool = True
    stage: str = ""
    db_path: str = ""
    error_type: str = ""
    error_preview: str = ""

    @classmethod
    def from_exception(cls_self, exc: Exception, *, stage: str, db_path: str):
        return cls_self(
            schema_version="runtime_sqlite_memory_diagnostic.v1",
            diagnostic_only=True,
            stage=stage,
            db_path=db_path,
            error_type=type(exc).__name__,
            error_preview=str(exc)[:1000],
        )