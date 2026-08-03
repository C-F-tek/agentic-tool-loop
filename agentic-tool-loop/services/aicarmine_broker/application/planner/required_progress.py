"""Structured model for planner required-next-progress text."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RequiredNextProgress:
    kind: str
    human_text: str
    must_not: tuple[str, ...] = ()
    must_choose_one_of: tuple[str, ...] = ()
    required_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_contract(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "human_text": self.human_text,
            "must_not": list(self.must_not),
            "must_choose_one_of": list(self.must_choose_one_of),
            "required_tools": list(self.required_tools),
            "forbidden_tools": list(self.forbidden_tools),
            "metadata": dict(self.metadata),
        }


def _metadata(metadata: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    out = dict(metadata or {})
    out.update({key: value for key, value in extra.items() if value is not None})
    return out


def progress_candidate_hint(
    human_text: str,
    *,
    metadata: dict[str, Any] | None = None,
    **extra: Any,
) -> RequiredNextProgress:
    return RequiredNextProgress(
        kind="candidate_hint",
        human_text=str(human_text or "").strip(),
        metadata=_metadata(metadata, **extra),
    )


def progress_quality_gate_final_allowed(
    human_text: str,
    *,
    metadata: dict[str, Any] | None = None,
    **extra: Any,
) -> RequiredNextProgress:
    return RequiredNextProgress(
        kind="quality_gate_final_allowed",
        human_text=str(human_text or "").strip(),
        must_choose_one_of=("final", "selective_evidence_tool_with_named_gap"),
        metadata=_metadata(metadata, **extra),
    )


def progress_code_product_route_shift(
    human_text: str,
    *,
    metadata: dict[str, Any] | None = None,
    **extra: Any,
) -> RequiredNextProgress:
    return RequiredNextProgress(
        kind="code_product_route_shift",
        human_text=str(human_text or "").strip(),
        must_not=("repeat_rejected_code_product_payload",),
        must_choose_one_of=(
            "repo_propose_code_edit_complete_payload",
            "code_product_build_state_progress",
            "typed_block",
        ),
        required_tools=("repo_propose_code_edit",),
        metadata=_metadata(metadata, **extra),
    )


def progress_forbidden_repeat_repo_read(
    human_text: str,
    *,
    target: str = "",
    metadata: dict[str, Any] | None = None,
    **extra: Any,
) -> RequiredNextProgress:
    return RequiredNextProgress(
        kind="forbidden_repeat_repo_read",
        human_text=str(human_text or "").strip(),
        must_not=("repeat_repo_read_target",),
        forbidden_tools=("repo_read",),
        metadata=_metadata(metadata, target=target or None, **extra),
    )


def progress_code_product_block_required(
    human_text: str,
    *,
    metadata: dict[str, Any] | None = None,
    **extra: Any,
) -> RequiredNextProgress:
    return RequiredNextProgress(
        kind="code_product_block_required",
        human_text=str(human_text or "").strip(),
        must_choose_one_of=("block",),
        metadata=_metadata(metadata, **extra),
    )


def progress_native_tool_required(
    human_text: str,
    *,
    metadata: dict[str, Any] | None = None,
    **extra: Any,
) -> RequiredNextProgress:
    return RequiredNextProgress(
        kind="native_tool_call_required",
        human_text=str(human_text or "").strip(),
        metadata=_metadata(metadata, **extra),
    )


def progress_prompt_context_continuation(
    human_text: str,
    *,
    metadata: dict[str, Any] | None = None,
    **extra: Any,
) -> RequiredNextProgress:
    return RequiredNextProgress(
        kind="prompt_context_continuation_required",
        human_text=str(human_text or "").strip(),
        required_tools=("planner_scratchpad_read",),
        metadata=_metadata(metadata, **extra),
    )


def required_next_progress_from_text(
    human_text: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> RequiredNextProgress:
    text = str(human_text or "").strip()
    lower = text.lower()
    base = progress_candidate_hint(text, metadata=metadata)
    if "quality gate is satisfied" in lower:
        base = progress_quality_gate_final_allowed(text, metadata=metadata)
    elif "route shift required" in lower:
        base = progress_code_product_route_shift(text, metadata=metadata)
    elif "blocked_incomplete" in lower:
        base = progress_code_product_block_required(text, metadata=metadata)
    elif "prompt_context_continuation_required" in lower or "planner_prompt_context_window" in lower:
        base = progress_prompt_context_continuation(text, metadata=metadata)
    elif "native" in lower and "tool_call" in lower:
        base = progress_native_tool_required(text, metadata=metadata)
    elif "do not final with prose-only" in lower or "requires repo_propose_code_edit" in lower:
        base = progress_code_product_route_shift(text, metadata=metadata)

    must_not: list[str] = list(base.must_not)
    must_choose_one_of: list[str] = list(base.must_choose_one_of)
    required_tools: list[str] = list(base.required_tools)
    forbidden_tools: list[str] = list(base.forbidden_tools)

    if "do not repeat repo_read" in lower or "do not call repo_read" in lower:
        forbidden_tools.append("repo_read")
        must_not.append("repeat_repo_read")
    if "do not repeat the rejected incomplete repo_propose_code_edit" in lower:
        must_not.append("repeat_rejected_incomplete_repo_propose_code_edit")
    if "empty collecting_source writes are rejected" in lower:
        must_not.append("empty_code_product_build_state_write")
    if "do not final with prose-only" in lower:
        must_not.append("prose_only_final")
    if "complete unified_diff" in lower or "complete structured_operations" in lower:
        must_choose_one_of.extend(["complete_unified_diff", "complete_structured_operations"])

    # Preserve deterministic order without duplicates.
    def unique(values: list[str]) -> tuple[str, ...]:
        out: list[str] = []
        for value in values:
            if value and value not in out:
                out.append(value)
        return tuple(out)

    return RequiredNextProgress(
        kind=base.kind,
        human_text=text,
        must_not=unique(must_not),
        must_choose_one_of=unique(must_choose_one_of),
        required_tools=unique(required_tools),
        forbidden_tools=unique(forbidden_tools),
        metadata=base.metadata,
    )
