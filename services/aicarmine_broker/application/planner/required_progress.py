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


def required_next_progress_from_text(
    human_text: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> RequiredNextProgress:
    text = str(human_text or "").strip()
    lower = text.lower()
    kind = "candidate_hint"
    must_not: list[str] = []
    must_choose_one_of: list[str] = []
    required_tools: list[str] = []
    forbidden_tools: list[str] = []

    if "quality gate is satisfied" in lower:
        kind = "quality_gate_final_allowed"
        must_choose_one_of.append("final")
    elif "route shift required" in lower:
        kind = "code_product_route_shift"
        required_tools.append("repo_propose_code_edit")
    elif "blocked_incomplete" in lower:
        kind = "code_product_block_required"
        must_choose_one_of.append("block")
    elif "prompt_context_continuation_required" in lower or "planner_prompt_context_window" in lower:
        kind = "prompt_context_continuation_required"
        required_tools.append("planner_scratchpad_read")
    elif "native" in lower and "tool_call" in lower:
        kind = "native_tool_call_required"
    elif "do not final with prose-only" in lower or "requires repo_propose_code_edit" in lower:
        kind = "code_product_route_shift"
        required_tools.append("repo_propose_code_edit")

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
        kind=kind,
        human_text=text,
        must_not=unique(must_not),
        must_choose_one_of=unique(must_choose_one_of),
        required_tools=unique(required_tools),
        forbidden_tools=unique(forbidden_tools),
        metadata=metadata or {},
    )
