"""Code product state management extracted from planner.py.

These functions handle code product build state tracking, read/write/propose
actions, window signature detection, and payload rejection counting.
"""
from __future__ import annotations

import json
from typing import Any


# ---------------------------------------------------------------------------
# Code product build state helpers
# ---------------------------------------------------------------------------

def _code_product_build_state_duplicate_write(
    history: list[dict[str, Any]],
    *,
    target_file: str,
    text: str,
) -> bool:
    """Return True if writing this text to target_file would be a duplicate."""
    from .agentic_v2 import code_product_build_state_duplicate_write as _inner
    return _inner(history, target_file=target_file, text=text)


def code_product_build_state_from_result(result: dict[str, Any]) -> dict[str, Any]:
    """Extract the code product build state from a planner result."""
    from .agentic_v2 import code_product_build_state_from_result as _inner
    return _inner(result)


def _code_product_build_state_read_action(state: dict[str, Any], target_file: str) -> dict[str, Any]:
    """Generate a read action for the code product build state."""
    from .agentic_v2 import code_product_build_state_read_action as _inner
    return _inner(state, target_file)


def code_product_source_windows_from_reads(
    history: list[dict[str, Any]],
    target_file: str,
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Extract source windows from successful repo_read history items."""
    from .agentic_v2 import code_product_source_windows_from_reads as _inner
    return _inner(history, target_file, same_tool_artifact_payload=_same_tool_artifact_payload,
                  repo_read_item_full_content=_repo_read_item_full_content, limit=limit)


def _code_product_build_state_write_action(
    target_file: str,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate a write action for the code product build state."""
    from .agentic_v2 import code_product_build_state_write_action as _inner
    return _inner(target_file, history, same_tool_artifact_payload=_same_tool_artifact_payload,
                  repo_read_item_full_content=_repo_read_item_full_content)


def _code_product_build_state_propose_action(
    state: dict[str, Any],
    latest_violations: list[str],
) -> dict[str, Any]:
    """Generate a propose action based on current state and violations."""
    from .agentic_v2 import code_product_build_state_propose_action as _inner
    return _inner(state, latest_violations)


def _code_product_candidate_action(
    *,
    target_file: str,
    latest_violations: list[str],
    goal: str = "",
) -> dict[str, Any]:
    """Generate a candidate action for the code product."""
    from .agentic_v2 import code_product_candidate_action as _inner
    return _inner(target_file=target_file, latest_violations=latest_violations, goal=goal)


# ---------------------------------------------------------------------------
# Window signature helpers
# ---------------------------------------------------------------------------

def _successful_window_signatures(history: list[dict[str, Any]], tool: str) -> set[str]:
    """Extract unique window signatures for successful tool calls."""
    from .agentic_v2 import successful_window_signatures as _inner
    return _inner(history, tool)


def _successful_repo_read_window_ranges(history: list[dict[str, Any]], target_file: str) -> list[tuple[int, int]]:
    """Extract window ranges for successful repo_read calls on target_file."""
    from .agentic_v2 import successful_repo_read_window_ranges as _inner
    return _inner(history, target_file)


# ---------------------------------------------------------------------------
# Payload rejection counting
# ---------------------------------------------------------------------------

def _code_product_payload_rejection_count(
    validation_rejections: list[dict[str, Any]],
    target_file: str = "",
) -> int:
    """Count validation rejections matching the target file."""
    from .agentic_v2 import code_product_payload_rejection_count as _inner
    return _inner(validation_rejections, target_file)


def _code_product_source_window_candidate(
    target_file: str,
    *,
    line_count: int = 0,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate a source window candidate for the target file."""
    from .agentic_v2 import code_product_source_window_candidate as _inner
    return _inner(target_file, line_count=line_count, history=history,
                  single_file_prompt_read_chars=_single_file_prompt_read_chars())


# ---------------------------------------------------------------------------
# Duplicate window stripping
# ---------------------------------------------------------------------------

def strip_duplicate_window_candidate(
    actions: list[dict[str, Any]],
    *,
    tool: str,
    signature: str,
) -> list[dict[str, Any]]:
    """Remove duplicate window candidates from action list."""
    from .agentic_v2 import strip_duplicate_window_candidate as _inner
    return _inner(actions, tool=tool, signature=signature)


def _apply_duplicate_window_replan_contract(
    contract: dict[str, Any],
    *,
    violation: str,
    tool: str,
    args: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply the duplicate window replan contract to fix candidate actions."""
    from .agentic_v2 import apply_duplicate_window_replan_contract as _inner
    return _inner(contract, violation=violation, tool=tool, args=args, history=history,
                  planner_scratchpad_next_window_action_from_history=_planner_scratchpad_next_window_action_from_history,
                  same_tool_artifact_payload=_same_tool_artifact_payload,
                  repo_read_item_full_content=_repo_read_item_full_content,
                  single_file_prompt_read_chars=_single_file_prompt_read_chars())


# ---------------------------------------------------------------------------
# Low signal target detection
# ---------------------------------------------------------------------------

def _code_product_low_signal_target(path: str, contract: dict[str, Any]) -> bool:
    """Return True if the path has low signal for code product work."""
    from .agentic_v2 import code_product_low_signal_target as _inner
    return _inner(path, contract)


# ---------------------------------------------------------------------------
# Decision signature helpers
# ---------------------------------------------------------------------------

def _canonical_invalid_code_product_decision_signature(
    decision: dict[str, Any],
    violations: list[Any] | tuple[Any, ...] | None = None,
) -> dict[str, Any]:
    """Generate a canonical signature for an invalid code product decision."""
    from .agentic_v2 import canonical_invalid_code_product_decision_signature as _inner
    return _inner(decision, violations)


def _invalid_decision_signature_key(signature: dict[str, Any]) -> str:
    """Extract the key used to identify duplicate invalid signatures."""
    from .agentic_v2 import invalid_decision_signature_key as _inner
    return _inner(signature)


def invalid_code_product_decision_signature_from_history_item(item: dict[str, Any]) -> dict[str, Any]:
    """Extract invalid decision signature from a history item."""
    from .agentic_v2 import invalid_code_product_decision_signature_from_history_item as _inner
    return _inner(item)


def _invalid_code_product_decision_signature_count(
    history: list[dict[str, Any]],
    signature: dict[str, Any],
) -> int:
    """Count how many times this invalid signature has appeared."""
    from .agentic_v2 import invalid_code_product_decision_signature_count as _inner
    return _inner(history, signature)


def _disallowed_invalid_code_product_signatures(
    validation_rejections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract disallowed invalid code product signatures from rejections."""
    from .agentic_v2 import disallowed_invalid_code_product_signatures as _inner
    return _inner(validation_rejections)


def _compact_validation_rejections_tail(
    validation_rejections: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Get the tail of validation rejections, compacted."""
    from .agentic_v2 import compact_validation_rejections_tail as _inner
    return _inner(validation_rejections, limit=limit)


# ---------------------------------------------------------------------------
# Local helper imports used by code product functions
# ---------------------------------------------------------------------------

def _same_tool_artifact_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Extract the artifact payload from a tool result."""
    from .agentic_v2 import same_tool_artifact_payload as _inner
    return _inner(result)


def _repo_read_item_full_content(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Extract full content from a repo_read history item."""
    from .prompt_budget import _repo_read_item_full_content as _inner
    return _inner(item)


def _planner_scratchpad_next_window_action_from_history(
    args: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Get the next window action from history for scratchpad reads."""
    from .agentic_v2 import planner_scratchpad_next_window_action_from_history as _inner
    return _inner(args, history, history_tool_result=_history_tool_result,
                  code_product_build_state_kind="code_product_build_state")


def _single_file_prompt_read_chars() -> int:
    """Calculate optimal single-file read size based on prompt budget."""
    try:
        from aicarmine_broker.config import AGENTIC_PLANNER_PROMPT_CHAR_BUDGET
        budget = int(AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or 24000)
    except Exception:
        budget = 24000
    return max(2000, min(120000, budget // 4))


def _history_tool_result(item: dict[str, Any]) -> dict[str, Any]:
    """Extract the tool result from a history item."""
    from .agentic_v2 import history_tool_result as _inner
    return _inner(item)


# ---------------------------------------------------------------------------
# Local aliases for backward compatibility with planner.py imports
# ---------------------------------------------------------------------------
_code_product_build_state_duplicate_write = _code_product_build_state_duplicate_write
code_product_build_state_from_result = code_product_build_state_from_result
_code_product_build_state_read_action = _code_product_build_state_read_action
code_product_source_windows_from_reads = code_product_source_windows_from_reads
_code_product_build_state_write_action = _code_product_build_state_write_action
_code_product_build_state_propose_action = _code_product_build_state_propose_action
_code_product_candidate_action = _code_product_candidate_action
_successful_window_signatures = _successful_window_signatures
_successful_repo_read_window_ranges = _successful_repo_read_window_ranges
_code_product_payload_rejection_count = _code_product_payload_rejection_count
_code_product_source_window_candidate = _code_product_source_window_candidate
strip_duplicate_window_candidate = strip_duplicate_window_candidate
_apply_duplicate_window_replan_contract = _apply_duplicate_window_replan_contract
_code_product_low_signal_target = _code_product_low_signal_target
_canonical_invalid_code_product_decision_signature = _canonical_invalid_code_product_decision_signature
_invalid_decision_signature_key = _invalid_decision_signature_key
invalid_code_product_decision_signature_from_history_item = invalid_code_product_decision_signature_from_history_item
_invalid_code_product_decision_signature_count = _invalid_code_product_decision_signature_count
_disallowed_invalid_code_product_signatures = _disallowed_invalid_code_product_signatures
_compact_validation_rejections_tail = _compact_validation_rejections_tail

__all__ = [
    "_code_product_build_state_duplicate_write",
    "code_product_build_state_from_result",
    "_code_product_build_state_read_action",
    "code_product_source_windows_from_reads",
    "_code_product_build_state_write_action",
    "_code_product_build_state_propose_action",
    "_code_product_candidate_action",
    "_successful_window_signatures",
    "_successful_repo_read_window_ranges",
    "_code_product_payload_rejection_count",
    "_code_product_source_window_candidate",
    "strip_duplicate_window_candidate",
    "_apply_duplicate_window_replan_contract",
    "_code_product_low_signal_target",
    "_canonical_invalid_code_product_decision_signature",
    "_invalid_decision_signature_key",
    "invalid_code_product_decision_signature_from_history_item",
    "_invalid_code_product_decision_signature_count",
    "_disallowed_invalid_code_product_signatures",
    "_compact_validation_rejections_tail",
]