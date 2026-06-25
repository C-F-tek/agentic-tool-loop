"""Planner helper functions extracted from planner.py.

This module owns standalone helpers that don't fit into decision, validation,
prompt, or loop modules:
- _successful_window_signatures
- _repo_analysis_goal
- _path_exists_repo_relative
- _argument_value_present
- _any_argument_group_present
- _native_required_tool_decision_has_transport_provenance
- _native_required_repaired_tool_decision_disallowed
- _old_text_verified_by_repo_read
- _apply_unverified_old_text_replan_contract
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Window signature tracking
# ---------------------------------------------------------------------------

def _successful_window_signatures(
    history: list[dict[str, Any]],
    tool: str,
) -> set[str]:
    """Track successful window signatures for a given tool."""
    if not isinstance(history, list):
        return set()
    if not isinstance(tool, str):
        return set()
    signatures: set[str] = set()
    for item in history:
        if not isinstance(item, dict):
            continue
        tool_result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        result_tool = tool_result.get("tool") if isinstance(tool_result, dict) else ""
        if result_tool == tool and tool_result.get("ok") is True:
            artifact = tool_result.get("artifact", "")
            if artifact:
                signatures.add(str(artifact))
    return signatures


# ---------------------------------------------------------------------------
# Goal analysis
# ---------------------------------------------------------------------------

def _repo_analysis_goal(goal: str) -> bool:
    """Check if goal requires repo analysis."""
    if not isinstance(goal, str):
        return False
    low = goal.lower()
    analysis_keywords = (
        "analyze", "audit", "review", "inspect", "diagnose",
        "understand", "explore", "map", "catalog", "inventory",
    )
    return any(kw in low for kw in analysis_keywords)


# ---------------------------------------------------------------------------
# Path existence checks
# ---------------------------------------------------------------------------

def _path_exists_repo_relative(path: str) -> bool:
    """Check if path exists relative to repo root."""
    if not isinstance(path, str):
        return False
    try:
        from ...config import LAB_REPO
        full_path = Path(LAB_REPO) / path if LAB_REPO else Path(path)
        return full_path.exists() and full_path.is_file()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------

def _argument_value_present(args: dict[str, Any], key: str) -> bool:
    """Check if an argument value is present and non-empty."""
    if not isinstance(args, dict):
        return False
    value = args.get(key)
    if value in (None, "", [], {}):
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _any_argument_group_present(
    args: dict[str, Any],
    groups: list[list[str]] | tuple[tuple[str, ...], ...],
) -> bool:
    """Check if any group of arguments has at least one present."""
    if not isinstance(args, dict):
        return False
    if not isinstance(groups, (list, tuple)):
        return False
    for group in groups:
        if isinstance(group, tuple):
            group_keys = list(group)
        else:
            group_keys = group
        for key in group_keys:
            if _argument_value_present(args, key):
                return True
    return False


# ---------------------------------------------------------------------------
# Transport provenance checks
# ---------------------------------------------------------------------------

def _native_required_tool_decision_has_transport_provenance(decision: dict[str, Any]) -> bool:
    """Check if native tool decision has transport provenance."""
    if not isinstance(decision, dict):
        return False
    # Check for transport metadata
    transport_keys = ("transport", "source", "origin", "vulkan_repair")
    return any(
        decision.get(key) is not None
        for key in transport_keys
    )


def _native_required_repaired_tool_decision_disallowed(decision: dict[str, Any]) -> bool:
    """Check if repaired tool decision should be disallowed."""
    if not isinstance(decision, dict):
        return False
    # Disallow repaired decisions that lack proper validation
    if decision.get("repaired_by_vulkan_gpu0_11435") is True:
        if not decision.get("validator_approved"):
            return True
    return False


# ---------------------------------------------------------------------------
# Old text verification
# ---------------------------------------------------------------------------

def _old_text_verified_by_repo_read(
    history: list[dict[str, Any]],
    target_file: str,
    old_text: Any,
) -> bool:
    """Verify old_text matches a previous repo_read result."""
    if not isinstance(history, list):
        return False
    if not isinstance(target_file, str):
        return False
    old_str = str(old_text).strip() if old_text else ""
    if not old_str:
        return False
    for item in reversed(history):
        if not isinstance(item, dict):
            continue
        tool_result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        tool = tool_result.get("tool") if isinstance(tool_result, dict) else ""
        artifact = tool_result.get("artifact") if isinstance(tool_result, dict) else ""
        if tool == "repo_read" and artifact == target_file:
            content = tool_result.get("content", "")
            if isinstance(content, str) and old_str in content:
                return True
    return False


# ---------------------------------------------------------------------------
# Unverified old text replan contract
# ---------------------------------------------------------------------------

def _apply_unverified_old_text_replan_contract(decision: dict[str, Any]) -> bool:
    """Check if unverified old text triggers replan."""
    if not isinstance(decision, dict):
        return False
    edit_kind = str(decision.get("edit_kind") or decision.get("operation") or "")
    if edit_kind in ("unified_diff", "structured_edit"):
        old_text = decision.get("old_text") or decision.get("anchor")
        if not old_text or not str(old_text).strip():
            return True
    return False