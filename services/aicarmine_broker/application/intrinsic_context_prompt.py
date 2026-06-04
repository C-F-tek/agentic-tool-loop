"""Prompt compaction helpers for intrinsic planner context."""
from __future__ import annotations

from typing import Any

from .prompt_values import prompt_clip_value


def compact_intrinsic_context_for_prompt(
    context: dict[str, Any],
    *,
    prompt_preview_chars: int,
) -> dict[str, Any]:
    if not isinstance(context, dict):
        return {}
    out = dict(context)
    rag = out.get("retrieved_rag_chunks") if isinstance(out.get("retrieved_rag_chunks"), dict) else {}
    if rag:
        rag = dict(rag)
        rag["items"] = prompt_clip_value(rag.get("items") or [], text_limit=360, list_limit=3)
        rag["count"] = len(rag.get("items") or [])
        out["retrieved_rag_chunks"] = rag
    mem = out.get("retrieved_memory") if isinstance(out.get("retrieved_memory"), dict) else {}
    if mem:
        mem = dict(mem)
        mem["items"] = prompt_clip_value(mem.get("items") or [], text_limit=360, list_limit=4)
        mem["count"] = len(mem.get("items") or [])
        out["retrieved_memory"] = mem
    return prompt_clip_value(out, text_limit=prompt_preview_chars, list_limit=8)
