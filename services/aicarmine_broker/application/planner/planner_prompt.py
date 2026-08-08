"""Planner prompt and history helpers extracted from planner.py.

This module owns:
- _planner_token_generation_reserve
- _prompt_compaction_threshold
- _prompt_generation_headroom_char_budget
- _prompt_window_chars
- _prompt_budget_report
- _prompt_window_consumed_offsets
- _prompt_window_tracking_metadata_errors
- _planner_scratchpad_next_window_action_from_history
- _prompt_context_continuation_from_payload
- _planner_ollama_turn_from_decision
- _history_item_ollama_turn
- _history_tool_result
- _planner_history_summary
- _planner_history_arguments
- _planner_history_reason
- _planner_controller_guard_history_payload
- _planner_history_evidence_payload
- _planner_tool_result_message_payload
- _planner_history_item_messages
- _planner_history_messages_for_ollama
- _planner_turn_memory
- _planner_prompt_budget_value
- _planner_scratchpad_read_selector_present
- _planner_cuda_rewrite_violations
- _planner_cuda_rewrite_violation_matches
- _planner_cuda_rewrite_instruction
- _planner_system_for_current_mode
"""
from __future__ import annotations

import json
import re
from typing import Any

from ...config import (
    AGENTIC_PLANNER_HISTORY_PROMPT_TAIL,
    AGENTIC_PLANNER_NUM_CTX,
    AGENTIC_PLANNER_NUM_CTX_CAP,
    AGENTIC_PLANNER_PROMPT_CHAR_BUDGET,
    AGENTIC_PLANNER_PROMPT_COMPACT_RATIO,
    AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS,
    VALID_INTERNAL_TOOLS,
)


# ---------------------------------------------------------------------------
# Prompt budget helpers
# ---------------------------------------------------------------------------

def _planner_token_generation_reserve(num_ctx: int | None = None) -> int:
    """Reserve tokens for model generation."""
    if num_ctx is None:
        num_ctx = AGENTIC_PLANNER_NUM_CTX or 32768
    return max(1000, min(int(num_ctx * 0.15), 5000))


def _prompt_compaction_threshold() -> int:
    """Return the compaction threshold in chars."""
    return AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or 24000


def _prompt_generation_headroom_char_budget() -> int:
    """Return headroom for prompt generation."""
    budget = AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or 24000
    return max(1000, int(budget * 0.08))


def _prompt_window_chars(compact_mode: bool, attempt: int = 0) -> int:
    """Calculate prompt window size based on mode and attempt."""
    base = AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or 24000
    ratio = AGENTIC_PLANNER_PROMPT_COMPACT_RATIO or 0.6
    if compact_mode:
        base = int(base * ratio)
    headroom = attempt * _prompt_generation_headroom_char_budget()
    return max(2000, min(base - headroom, base))


def _prompt_budget_report(
    *,
    num_ctx: int,
    prompt_chars: int,
    compact_mode: bool,
    history_tail_count: int,
) -> dict[str, Any]:
    """Generate a prompt budget report."""
    reserved = _planner_token_generation_reserve(num_ctx)
    available = num_ctx - reserved
    used_pct = (prompt_chars / num_ctx * 100) if num_ctx else 0
    return {
        "num_ctx": num_ctx,
        "available_tokens": available,
        "prompt_chars": prompt_chars,
        "compact_mode": compact_mode,
        "history_tail_count": history_tail_count,
        "used_pct": round(used_pct, 2),
        "headroom_tokens": available - (prompt_chars // 4),
    }


# ---------------------------------------------------------------------------
# Prompt window tracking
# ---------------------------------------------------------------------------

def _prompt_window_consumed_offsets(history: list[dict[str, Any]]) -> dict[str, int]:
    """Track consumed offsets in prompt window."""
    if not isinstance(history, list):
        return {"before": 0, "after": 0}
    before = 0
    after = 0
    for item in history:
        if not isinstance(item, dict):
            continue
        meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
        if isinstance(meta.get("window_start"), (int, float)):
            before = max(before, int(meta["window_start"]))
        if isinstance(meta.get("window_end"), (int, float)):
            after = max(after, int(meta["window_end"]))
    return {"before": before, "after": after}


def _prompt_window_tracking_metadata_errors(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find metadata errors in prompt window tracking."""
    if not isinstance(history, list):
        return []
    errors: list[dict[str, Any]] = []
    for index, item in enumerate(history):
        if not isinstance(item, dict):
            continue
        meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
        if not meta:
            continue
        required_keys = ("window_start", "window_end", "complete")
        for key in required_keys:
            if key not in meta or meta[key] is None:
                errors.append({
                    "index": index,
                    "missing_key": key,
                    "item_type": type(item).get("tool", "unknown"),
                })
    return errors


# ---------------------------------------------------------------------------
# Scratchpad window actions
# ---------------------------------------------------------------------------

def _planner_scratchpad_next_window_action_from_history(
    history: list[dict[str, Any]],
) -> str:
    """Determine next scratchpad window action from history."""
    if not isinstance(history, list):
        return "no_action"
    for item in reversed(history):
        if not isinstance(item, dict):
            continue
        tool_result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        guard_type = tool_result.get("guard_type") if isinstance(tool_result, dict) else ""
        if guard_type == "scratchpad_window_complete":
            return "window_complete"
        if guard_type == "scratchpad_window_partial":
            return "window_partial"
    return "no_scratchpad"


# ---------------------------------------------------------------------------
# Prompt context continuation
# ---------------------------------------------------------------------------

def _prompt_context_continuation_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract prompt context continuation from payload."""
    if not isinstance(payload, dict):
        return {}
    optional = payload.get("optional_context") if isinstance(payload.get("optional_context"), dict) else {}
    evidence = payload.get("evidence_contract") if isinstance(payload.get("evidence_contract"), dict) else {}
    return {
        "intrinsic_context": optional.get("intrinsic_context"),
        "candidate_next_actions": evidence.get("candidate_next_actions"),
        "evidence_contract": evidence,
    }


# ---------------------------------------------------------------------------
# Ollama turn / history item builders
# ---------------------------------------------------------------------------

def _planner_ollama_turn_from_decision(decision: dict[str, Any]) -> dict[str, Any]:
    """Build an Ollama turn message from a decision."""
    if not isinstance(decision, dict):
        return {"role": "assistant", "content": ""}
    content = str(
        decision.get("raw_planner_text")
        or decision.get("partial_content")
        or decision.get("final_answer")
        or ""
    )
    return {
        "role": "assistant",
        "content": content.strip() if content.strip() else "",
    }


def _history_item_ollama_turn(item: dict[str, Any]) -> dict[str, Any]:
    """Extract Ollama turn from history item."""
    if not isinstance(item, dict):
        return {"role": "user", "content": ""}
    message = item.get("message") if isinstance(item.get("message"), dict) else {}
    return {
        "role": item.get("role", "user"),
        "content": str(message.get("content") or ""),
    }


def _history_tool_result(item: dict[str, Any]) -> dict[str, Any]:
    """Extract tool result from history item."""
    if not isinstance(item, dict):
        return {}
    result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
    return dict(result) if isinstance(result, dict) else {}


# ---------------------------------------------------------------------------
# History summary builders
# ---------------------------------------------------------------------------

def _planner_history_summary(value: Any) -> str:
    """Summarize a history value for display."""
    if isinstance(value, str):
        return value[:500] if len(value) > 500 else value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)[:500]
    except Exception:
        return str(value)[:500]


def _planner_history_arguments(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Extract arguments from history item and result."""
    args = result.get("arguments") if isinstance(result.get("arguments"), dict) else {}
    if not args:
        args = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
    return dict(args)


def _planner_history_reason(item: dict[str, Any], result: dict[str, Any]) -> str:
    """Extract reason from history item and result."""
    reason = result.get("reason") if isinstance(result.get("reason"), str) else ""
    if not reason:
        reason = item.get("reason") if isinstance(item.get("reason"), str) else ""
    return reason


def _planner_controller_guard_history_payload(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Build controller guard history payload."""
    return {
        "tool": result.get("tool", item.get("tool", "")),
        "ok": result.get("ok", True),
        "guard_type": result.get("guard_type", ""),
        "summary": result.get("summary", ""),
        "violations": result.get("violations", []),
    }


def _planner_history_evidence_payload(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Build evidence payload from history item."""
    return {
        "tool": result.get("tool", item.get("tool", "")),
        "evidence": result.get("evidence", {}),
        "confidence": result.get("confidence", 0.0),
    }


def _planner_tool_result_message_payload(
    tool_name: str,
    result: dict[str, Any],
    *,
    max_content_chars: int = 2000,
) -> dict[str, Any]:
    """Build a tool result message payload for Ollama."""
    content = str(result.get("summary") or result.get("content") or "")
    return {
        "role": "assistant",
        "content": f"Tool: {tool_name}\nResult: {content[:max_content_chars]}",
    }


# ---------------------------------------------------------------------------
# History messages builder
# ---------------------------------------------------------------------------

def _planner_history_item_messages(
    item: dict[str, Any],
    result: dict[str, Any],
    *,
    compact_mode: bool = False,
) -> list[dict[str, Any]]:
    """Build messages for a single history item."""
    if not isinstance(item, dict):
        return []
    role = item.get("role", "user")
    content = str(item.get("content") or "")
    if compact_mode and len(content) > 2000:
        content = content[:2000] + "... <truncated>"
    return [{"role": role, "content": content}]


def _planner_history_messages_for_ollama(
    history: list[dict[str, Any]],
    *,
    tail_count: int | None = None,
    compact_mode: bool = False,
) -> list[dict[str, Any]]:
    """Build complete messages list for Ollama from history."""
    if tail_count is not None:
        history = history[-tail_count:] if tail_count > 0 else history
    messages: list[dict[str, Any]] = []
    for item in history:
        msgs = _planner_history_item_messages(item, result={}, compact_mode=compact_mode)
        messages.extend(msgs)
    return messages


# ---------------------------------------------------------------------------
# Turn memory
# ---------------------------------------------------------------------------

def _planner_turn_memory(
    *,
    goal: str,
    step: int,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build turn memory context."""
    return {
        "goal": goal[:500] if isinstance(goal, str) else "",
        "step": step,
        "history_tail_count": len(history),
        "memory_available": bool(history),
    }


# ---------------------------------------------------------------------------
# Prompt budget value
# ---------------------------------------------------------------------------

def _planner_prompt_budget_value(default: int = 24000) -> int:
    """Get prompt budget value from config or default."""
    from ...config import AGENTIC_PLANNER_PROMPT_CHAR_BUDGET
    return AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or default


# ---------------------------------------------------------------------------
# Scratchpad read selector
# ---------------------------------------------------------------------------

def _planner_scratchpad_read_selector_present(args: dict[str, Any]) -> bool:
    """Check if scratchpad read selector is present in args."""
    tool_name = str(args.get("tool") or args.get("action") or "")
    if tool_name not in ("scratchpad_tools_public", "memory_tools_public"):
        return False
    arguments = args.get("arguments") if isinstance(args.get("arguments"), dict) else {}
    if not isinstance(arguments, dict):
        return False
    return bool(arguments.get("selector") or arguments.get("mode"))


# ---------------------------------------------------------------------------
# CUDA rewrite violations
# ---------------------------------------------------------------------------

def _planner_cuda_rewrite_violations(validation: dict[str, Any]) -> list[str]:
    """Extract CUDA rewrite violations from validation."""
    if not isinstance(validation, dict):
        return []
    violations = validation.get("violations")
    if isinstance(violations, list):
        return [str(v) for v in violations if v]
    return []


def _planner_cuda_rewrite_violation_matches(
    violation: str,
    text: str,
) -> bool:
    """Check if a CUDA rewrite violation matches text."""
    patterns = (
        "cuda", "gpu", "tensor", "kernel", "device",
        "cuda_out_memory", "torch.cuda", "cupy",
    )
    low_text = text.lower()
    return any(p in low_text for p in patterns)


def _planner_cuda_rewrite_instruction(
    goal: str,
    violations: list[str],
) -> str:
    """Build CUDA rewrite instruction from violations."""
    if not violations:
        return ""
    return (
        f"Goal: {goal}\n"
        f"CUDA/GPU violations detected: {'; '.join(violations[:5])}\n"
        "Please provide a CPU-compatible alternative implementation."
    )


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def _planner_system_for_current_mode() -> str:
    """Build system prompt for current planner mode."""
    from ...config import AICARMINE_ORIENTATION_LANE_MODE
    mode = AICARMINE_ORIENTATION_LANE_MODE or "default"
    base = (
        "You are the controlled 30B planner. "
        "Your role is to analyze tasks, make tool decisions, and produce code products."
    )
    if mode == "repair":
        base += " You are in repair mode - fix malformed outputs."
    elif mode == "validation":
        base += " You are in validation mode - verify decisions against evidence."
    return base