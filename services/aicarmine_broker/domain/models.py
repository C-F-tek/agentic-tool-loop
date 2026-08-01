"""Consolidated domain models for thfrom services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

e 3572 agentic loop.

This module centralizes all frozen dataclass types used across the planner,
controller, validator, and job orchestration layers. Each individual submodule
(./config.py, ./decisions.py, etc.) remains as a backward-compatible shim so
that existing imports like `from aicarmine_broker.domain.config import PlannerRuntimeConfig`
continue to work without changes.

All consumers should migrate toward the single-package import:
    from aicarmine_broker.domain.models import (ToolDecision, ToolResult, ...)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# From config.py (1 dataclass)
# ---------------------------------------------------------------------------
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


def _missing_text(value: Any) -> bool:
    try:
        return not str(value or "").strip()
    except Exception:
        return True


def _diagnostic_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def mapping_field_diagnostics(field_name: str, value: Any) -> tuple[str, ...]:
    """Return bounded diagnostics for optional mapping-like model fields."""
    if isinstance(value, MappingABC):
        return ()
    if value is None:
        return (f"{field_name}:missing_mapping",)
    return (f"{field_name}:invalid_mapping_type:{type(value).__name__}",)


@dataclass(frozen=True)
class PlannerRuntimeConfig:
    """Measured planner runtime settings for one process/turn."""

    planner_url: str
    planner_model: str
    task_url: str
    task_model: str
    num_ctx_requested: int
    num_ctx_cap: int
    num_ctx_effective: int
    prompt_char_budget: int
    prompt_compact_threshold_chars: int
    generation_headroom_reserve_chars: int

    def validation_diagnostics(self) -> tuple[str, ...]:
        """Return opt-in diagnostics without enforcing constructor validation."""
        diagnostics: list[str] = []
        for field_name in ("planner_url", "planner_model", "task_url", "task_model"):
            if _missing_text(getattr(self, field_name)):
                diagnostics.append(f"{field_name}:missing")
        positive_fields = (
            "num_ctx_requested",
            "num_ctx_cap",
            "num_ctx_effective",
            "prompt_char_budget",
            "prompt_compact_threshold_chars",
            "generation_headroom_reserve_chars",
        )
        numeric_values: dict[str, int] = {}
        for field_name in positive_fields:
            value = _diagnostic_int(getattr(self, field_name))
            if value is None:
                diagnostics.append(f"{field_name}:invalid_integer")
                continue
            numeric_values[field_name] = value
            if value <= 0:
                diagnostics.append(f"{field_name}:not_positive")
        effective = numeric_values.get("num_ctx_effective")
        cap = numeric_values.get("num_ctx_cap")
        if effective is not None and cap is not None and effective > cap:
            diagnostics.append("num_ctx_effective:exceeds_num_ctx_cap")
        return tuple(diagnostics)


# ---------------------------------------------------------------------------
# From decisions.py (3 dataclasses)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolDecision:
    """A planner request to execute an internal 3572 tool."""

    tool: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    reason: str = ""
    native_tool_call: bool = False


@dataclass(frozen=True)
class FinalDecision:
    """A planner final answer candidate before validator acceptance."""

    final_answer: str
    source: str = "final_answer"


@dataclass(frozen=True)
class PlannerDecision:
    """Normalized planner decision independent from Ollama transport shape."""

    action: str
    raw: Mapping[str, Any] = field(default_factory=dict)
    tool_call: ToolDecision | None = None
    final: FinalDecision | None = None
    violations: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# From evidence.py (3 dataclasses)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# From job.py (1 dataclass)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentJobSnapshot:
    """Immutable view of a 3572 job state used by orchestration ports."""

    job_id: str
    status: str
    goal: str
    workspace: Path
    history: tuple[Mapping[str, Any], ...] = ()
    state: Mapping[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# From results.py (2 dataclasses)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolResult:
    """Result returned by a dispatched internal 3572 tool."""

    tool: str
    ok: bool
    artifact: Mapping[str, Any] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationResult:
    """Validator outcome for a normalized planner decision."""

    ok: bool
    violations: tuple[str, ...] = ()
    blocker: str | None = None
    evidence_updates: Mapping[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# From tool.py (1 dataclass)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolSpec:
    """Planner-visible schema summary for one internal tool."""

    name: str
    description: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    write_guarded: bool = False
    public_3571_visible: bool = False


__all__: list[str] = [
    "mapping_field_diagnostics",
    # config
    "PlannerRuntimeConfig",
    # decisions
    "ToolDecision",
    "FinalDecision",
    "PlannerDecision",
    # evidence
    "EvidenceWindow",
    "ToolEvidence",
    "EvidenceContract",
    # job
    "AgentJobSnapshot",
    # results
    "ToolResult",
    "ValidationResult",
    # tool
    "ToolSpec",
]
