"""Planner validation helpers extracted from planner.py.

This module owns:
- _apply_duplicate_window_replan_contract
- _apply_unverified_old_text_replan_contract
- code_product_build_state_duplicate_write
- code_product_build_state_has_collecting_progress
- code_product_build_state_parse
- code_product_build_state_ready_payload
- code_product_payload_violations
- invalid_code_product_decision_signature_count
- invalid_decision_signature_key
- successful_code_edit_proposals
"""
from __future__ import annotations

import json
import re
from typing import Any


def _apply_duplicate_window_replan_contract(state: dict[str, Any], decision: dict[str, Any]) -> bool:
    """Check if duplicate write window replan contract applies."""
    if not isinstance(state, dict) or not isinstance(decision, dict):
        return False
    build_state = state.get("build_state") if isinstance(state.get("build_state"), dict) else {}
    if not build_state:
        return False
    duplicate_count = build_state.get("duplicate_write_count", 0)
    if duplicate_count >= 2:
        return True
    return False


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


def code_product_build_state_duplicate_write(state: dict[str, Any]) -> int:
    """Count duplicate write attempts in build state."""
    if not isinstance(state, dict):
        return 0
    build_state = state.get("build_state") if isinstance(state.get("build_state"), dict) else {}
    if not build_state:
        return 0
    return int(build_state.get("duplicate_write_count", 0))


def code_product_build_state_has_collecting_progress(state: dict[str, Any]) -> bool:
    """Check if build state has collecting progress."""
    if not isinstance(state, dict):
        return False
    build_state = state.get("build_state") if isinstance(state.get("build_state"), dict) else {}
    if not build_state:
        return False
    return bool(build_state.get("collecting_progress", False))


def code_product_build_state_parse(raw_text: str) -> dict[str, Any]:
    """Parse code product build state from raw text."""
    if not isinstance(raw_text, str):
        return {"parseable": False}
    try:
        decoded = json.loads(raw_text)
        if isinstance(decoded, dict):
            return {"parseable": True, "state": decoded}
    except (json.JSONDecodeError, ValueError):
        pass
    return {"parseable": False}


def code_product_build_state_ready_payload(state: dict[str, Any]) -> dict[str, Any]:
    """Build ready payload from parsed build state."""
    if not isinstance(state, dict):
        return {}
    return {
        "ready": bool(state.get("ready", False)),
        "answer": state.get("answer") or "",
        "clean_text": state.get("clean_text") or "",
        "violations": state.get("violations") or [],
    }


def code_product_payload_violations(payload: dict[str, Any]) -> list[str]:
    """Extract violations from code product payload."""
    if not isinstance(payload, dict):
        return []
    violations = payload.get("violations")
    if isinstance(violations, list):
        return [str(v) for v in violations if v]
    return []


def invalid_code_product_decision_signature_count(decisions: list[dict[str, Any]]) -> int:
    """Count invalid code product decision signatures."""
    if not isinstance(decisions, list):
        return 0
    count = 0
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        edit_kind = str(decision.get("edit_kind") or "")
        if edit_kind in ("unified_diff", "structured_edit"):
            old_text = decision.get("old_text") or decision.get("anchor")
            if not old_text or not str(old_text).strip():
                count += 1
    return count


def invalid_decision_signature_key(decision: dict[str, Any]) -> str:
    """Extract invalid decision signature key."""
    if not isinstance(decision, dict):
        return ""
    edit_kind = str(decision.get("edit_kind") or decision.get("operation") or "")
    tool_name = str(decision.get("tool") or decision.get("action") or "")
    return f"{edit_kind}:{tool_name}"


def successful_code_edit_proposals(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract successful code edit proposals from history."""
    if not isinstance(history, list):
        return []
    proposals: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        if result.get("ok") is True and result.get("edit_kind") in ("unified_diff", "structured_edit"):
            proposals.append(dict(result))
    return proposals