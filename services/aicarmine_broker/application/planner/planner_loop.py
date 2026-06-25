"""Planner agentic loop and code product builders extracted from planner.py.

This module owns:
- run_agentic_planner_job (stub - full implementation remains in planner.py)
- _agentic_v2_alias_repo_path
- _agentic_v2_goal_scope
- _agentic_v2_decision_paths
- _agentic_v2_read_has_window
- _agentic_v2_repo_list_rows
- _agentic_v2_successful_read_paths
- _agentic_v2_enrich_evidence_contract
- _code_product_build_state_duplicate_write
- _code_product_build_state_read_action
- _code_product_build_state_write_action
- _code_product_build_state_propose_action
- _code_product_candidate_action
- _code_product_payload_rejection_count
- _code_product_source_window_candidate
- _code_product_low_signal_target
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
    """Extract repo list rows from history."""
    rows: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        tool_result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        tool = tool_result.get("tool") if isinstance(tool_result, dict) else ""
        if tool in ("repo_list_files", "terminal_list_files"):
            rows.append(dict(tool_result))
    return rows


def _agentic_v2_successful_read_paths(history: list[dict[str, Any]]) -> list[str]:
    """Extract successful read paths from history."""
    paths: list[str] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        tool_result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        if tool_result.get("ok") is True:
            tool = tool_result.get("tool")
            artifact = tool_result.get("artifact")
            if tool in ("repo_read", "terminal_list_files") and artifact:
                path = str(artifact).strip()
                if path not in paths:
                    paths.append(path)
    return paths


def _agentic_v2_enrich_evidence_contract(
    contract: dict[str, Any],
    goal: str,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Enrich evidence contract with goal and history context."""
    if not isinstance(contract, dict):
        contract = {}
    if goal:
        contract["goal"] = goal[:500]
    if history:
        contract["history_tail_count"] = len(history)
        contract["last_tool"] = history[-1].get("tool") if history else ""
    return contract


# ---------------------------------------------------------------------------
# Code product builders
# ---------------------------------------------------------------------------

def _code_product_build_state_duplicate_write(
    state: dict[str, Any],
    *,
    max_duplicates: int = 2,
) -> bool:
    """Check if duplicate write limit exceeded."""
    if not isinstance(state, dict):
        return False
    build_state = state.get("build_state") if isinstance(state.get("build_state"), dict) else {}
    if not build_state:
        return False
    count = int(build_state.get("duplicate_write_count", 0))
    return count >= max_duplicates


def _code_product_build_state_read_action(
    state: dict[str, Any],
    target_file: str,
) -> dict[str, Any]:
    """Build read action from build state."""
    return {
        "action": "read",
        "target_file": target_file,
        "state": state.get("build_state"),
    }


def _code_product_build_state_write_action(
    state: dict[str, Any],
    target_file: str,
    content: str,
) -> dict[str, Any]:
    """Build write action from build state."""
    return {
        "action": "write",
        "target_file": target_file,
        "content_preview": content[:200] if content else "",
        "content_length": len(content) if content else 0,
    }


def _code_product_build_state_propose_action(
    state: dict[str, Any],
    edit_kind: str,
    old_text: str,
    new_text: str,
) -> dict[str, Any]:
    """Build propose action from build state."""
    return {
        "action": "propose_edit",
        "edit_kind": edit_kind,
        "old_text_preview": old_text[:200] if old_text else "",
        "new_text_preview": new_text[:200] if new_text else "",
    }


def _code_product_candidate_action(
    decision: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build candidate action from decision and history."""
    tool = str(decision.get("tool") or decision.get("action") or "")
    arguments = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
    return {
        "tool": tool,
        "arguments": dict(arguments),
        "history_tail_count": len(history),
        "decision_confidence": decision.get("confidence", 0.5),
    }


def _code_product_payload_rejection_count(
    decisions: list[dict[str, Any]],
) -> int:
    """Count rejected code product payloads."""
    count = 0
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        result = decision.get("result") if isinstance(decision.get("result"), dict) else {}
        if not result.get("ok") is True:
            count += 1
    return count


def _code_product_source_window_candidate(
    history: list[dict[str, Any]],
    target_path: str,
) -> dict[str, Any]:
    """Find source window candidate from history for target path."""
    candidates: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        tool_result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        artifact = tool_result.get("artifact") if isinstance(tool_result, dict) else ""
        if artifact and target_path in str(artifact):
            candidates.append(dict(tool_result))
    return {
        "target_path": target_path,
        "candidates": candidates[:5],
        "candidate_count": len(candidates),
    }


def _code_product_low_signal_target(path: str, contract: dict[str, Any]) -> bool:
    """Check if target has low signal for code product."""
    if not path or not contract:
        return True
    # Low signal indicators
    low_signal_patterns = (
        "__pycache__", ".pyc", ".egg-info", ".git",
        "node_modules", "vendor", "test_", "_test.py",
    )
    low = path.lower()
    return any(pattern in low for pattern in low_signal_patterns)


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