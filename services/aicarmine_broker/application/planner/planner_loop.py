"""Planner agentic loop and code product builders extracted from planner.py.

This module owns:
- run_agentic_planner_job (stub - full implementation remains in planner.py)
- _agentic_v2_alias_repo_path
- _agentic_v2_goal_scope
- _agentic_v2_decision_paths
- _agentic_v2_read_has_window
- _agentic_v2_repo_list_rows → delegates to .agentic_v2
- _agentic_v2_successful_read_paths → delegates to .agentic_v2
- _agentic_v2_enrich_evidence_contract → delegates to .agentic_v2
- _code_product_build_state_* → delegates to .code_product_state
"""
from __future__ import annotations

import json
import re
from typing import Any


# ---------------------------------------------------------------------------
# Agentic v2 helpers
# ---------------------------------------------------------------------------

def _agentic_v2_alias_repo_path(path: Any) -> str:
    """Normalize repo path aliases for agentic loop."""
    if path is None:
        return ""
    raw = str(path).strip()
    if not raw:
        return ""
    # Normalize common alias patterns
    normalized = raw.replace("\\", "/")
    return normalized.strip("/")


def _agentic_v2_goal_scope(goal: str, contract: dict[str, Any] | None = None) -> str:
    """Extract goal scope from task description."""
    if not isinstance(goal, str):
        return ""
    low = goal.lower().strip()
    # Classify by intent keywords
    intents = {
        "code_product": ("implement", "create", "build", "add", "modify", "refactor"),
        "analysis": ("analyze", "review", "audit", "inspect", "diagnose"),
        "search": ("find", "search", "locate", "discover"),
        "validation": ("validate", "verify", "test", "check"),
    }
    for category, keywords in intents.items():
        if any(kw in low for kw in keywords):
            return category
    return "unknown"


def _agentic_v2_decision_paths(tool: str, args: dict[str, Any]) -> list[str]:
    """Determine decision paths based on tool and arguments."""
    paths: list[str] = []
    # Map tool to expected path types
    tool_paths = {
        "repo_read": ["read_file", "read_directory"],
        "repo_search": ["search_pattern", "search_symbol"],
        "repo_tree": ["list_files", "list_directories"],
        "repo_list_files": ["list_files"],
        "repo_patch": ["apply_patch", "validate_patch"],
        "terminal_run_command_wait": ["execute_command"],
    }
    expected = tool_paths.get(tool, [])
    if expected:
        paths.extend(expected)
    # Check args for additional paths
    if args.get("path") or args.get("paths"):
        paths.append("path_based")
    if args.get("query") or args.get("pattern"):
        paths.append("query_based")
    return list(dict.fromkeys(paths))


def _agentic_v2_read_has_window(args: dict[str, Any]) -> bool:
    """Check if read operation has window metadata."""
    if not isinstance(args, dict):
        return False
    meta = args.get("meta") if isinstance(args.get("meta"), dict) else {}
    if not meta:
        return False
    return bool(meta.get("window_start") is not None and meta.get("window_end") is not None)


def _agentic_v2_repo_list_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Delegate to canonical implementation in agentic_v2 module."""
    from . import agentic_v2
    return agentic_v2._agentic_v2_repo_list_rows(history)


def _agentic_v2_successful_read_paths(history: list[dict[str, Any]]) -> list[str]:
    """Delegate to canonical implementation in agentic_v2 module."""
    from . import agentic_v2
    return agentic_v2._agentic_v2_successful_read_paths(history)


def _agentic_v2_enrich_evidence_contract(
    contract: dict[str, Any],
    goal: str,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Delegate to canonical implementation in agentic_v2 module."""
    from . import agentic_v2
    return agentic_v2._agentic_v2_enrich_evidence_contract(contract, goal, history)


# ---------------------------------------------------------------------------
# Code product builders
# ---------------------------------------------------------------------------

from . import code_product_state as _cps


def _code_product_build_state_duplicate_write(
    history: list[dict[str, Any]],
    *,
    target_file: str,
    text: str,
) -> bool:
    """Delegate to canonical implementation in code_product_state module."""
    return _cps._code_product_build_state_duplicate_write(history, target_file=target_file, text=text)


def _code_product_build_state_read_action(state: dict[str, Any], target_file: str) -> dict[str, Any]:
    """Delegate to canonical implementation in code_product_state module."""
    return _cps._code_product_build_state_read_action(state, target_file)


def _code_product_build_state_write_action(
    target_file: str,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Delegate to canonical implementation in code_product_state module."""
    return _cps._code_product_build_state_write_action(target_file, history)


def _code_product_build_state_propose_action(
    state: dict[str, Any],
    latest_violations: list[str],
) -> dict[str, Any]:
    """Delegate to canonical implementation in code_product_state module."""
    return _cps._code_product_build_state_propose_action(state, latest_violations)


def _code_product_candidate_action(
    *,
    target_file: str,
    latest_violations: list[str],
    goal: str = "",
) -> dict[str, Any]:
    """Delegate to canonical implementation in code_product_state module."""
    return _cps._code_product_candidate_action(target_file=target_file, latest_violations=latest_violations, goal=goal)


def _code_product_payload_rejection_count(
    validation_rejections: list[dict[str, Any]],
    target_file: str = "",
) -> int:
    """Delegate to canonical implementation in code_product_state module."""
    return _cps._code_product_payload_rejection_count(validation_rejections, target_file)


def _code_product_source_window_candidate(
    target_file: str,
    *,
    line_count: int = 0,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Delegate to canonical implementation in code_product_state module."""
    return _cps._code_product_source_window_candidate(target_file, line_count=line_count, history=history)


def _code_product_low_signal_target(path: str, contract: dict[str, Any]) -> bool:
    """Delegate to canonical implementation in code_product_state module."""
    return _cps._code_product_low_signal_target(path, contract)


# ---------------------------------------------------------------------------
# Main agentic loop entry point (stub - full implementation remains in planner.py)
# ---------------------------------------------------------------------------

def run_agentic_planner_job(job_id: str) -> dict[str, Any]:
    """Run the agentic planner job.
    
    Full implementation remains in planner.py to avoid breaking circular imports.
    This stub preserves the function signature for consumers.
    """
    # TODO: Full agentic loop implementation
    return {
        "ok": False,
        "error": "implementation_moved_to_planner.py",
        "job_id": job_id,
    }