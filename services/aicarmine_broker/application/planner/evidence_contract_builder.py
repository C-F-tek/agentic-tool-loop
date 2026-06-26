"""Evidence contract builder extracted from planner.py.

This module handles building the planner evidence contract from history and
intrinsic context, including operational notebook construction, candidate
action generation, and initial orientation surface extraction.
"""
from __future__ import annotations

from typing import Any


def planner_evidence_contract(
    goal: str,
    history: list[dict[str, Any]],
    intrinsic_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the complete evidence contract for planner validation.

    This is the core function that assembles all evidence about the current
    state of the agentic loop: what has been read, what tools have been used,
    what violations have occurred, and what the next recommended actions are.
    """
    from .agentic_v2 import (
        agentic_v2_decision_paths,
        agentic_v2_enrich_evidence_contract,
        agentic_v2_goal_scope,
    )
    from ..tool_surface.turn_surface_policy import apply_turn_surface_policy
    from .code_product_state import (
        _code_product_build_state_propose_action,
        _code_product_build_state_read_action,
        _code_product_build_state_write_action,
        _code_product_candidate_action,
        _code_product_payload_rejection_count,
    )
    from .code_product_state import strip_duplicate_window_candidate
    from .agentic_v2 import code_product_action_has_complete_payload
    from .agentic_v2 import code_product_payload_violations
    from .code_product_state import _code_product_source_window_candidate
    from .code_product_state import _compact_validation_rejections_tail
    from .goal_classifier import (
        _goal_target_file,
        goal_requested_repo_scope,
        goal_requires_code_security_coverage,
        goal_requests_apply,
        goal_requests_code_product,
        semantic_goal_classification,
    )
    from .agentic_v2 import (
        failed_code_edit_proposal_validation_row,
        file_memory_from_history,
        goal_exact_text_block,
        history_has_tool,
        latest_code_product_build_state,
        path_exists_repo_relative,
        paths_from_list_rows,
        paths_from_result,
        rank_core_candidates,
        repo_analysis_goal,
        repo_code_file,
        repo_doc_or_config,
        repo_list_evidence,
        repo_readable_evidence_file,
        repo_rel_token,
        repo_required_read_count,
        scope_read_candidates_from_evidence,
        successful_window_signatures,
        successful_code_edit_proposals,
        successful_repo_read_paths,
        failed_repo_read_paths,
    )
    from .agentic_v2 import planner_scratchpad_window_signature
    from .agentic_v2 import repo_read_window_signature
    from ..evidence.builder import planner_evidence_contract as _planner_evidence_contract_impl
    from ..evidence.core_discovery import core_discovery_candidates_from_intrinsic
    from .validation_rejections import disallowed_invalid_code_product_signatures
    from .goal_classifier import (
        _repo_analysis_goal,
        low_signal_top_dir,
    )
    from .code_product_state import (
        _canonical_invalid_code_product_decision_signature,
        _invalid_decision_signature_count,
    )
    from .agentic_v2 import (
        meaningful_read_candidates_from_evidence,
        scoped_required_read_count,
    )
    from .goal_classifier import (
        _user_scope_claims,
        _verified_repo_read_content_rows,
    )

    return _planner_evidence_contract_impl(
        goal,
        history,
        intrinsic_context,
        deps={
            "agentic_v2_decision_paths": agentic_v2_decision_paths,
            "agentic_v2_enrich_evidence_contract": agentic_v2_enrich_evidence_contract,
            "agentic_v2_goal_scope": agentic_v2_goal_scope,
            "apply_turn_surface_policy": apply_turn_surface_policy,
            "build_operational_notebook": _build_operational_notebook,
            "candidate_actions_from_evidence": _candidate_actions_from_evidence,
            "canonical_invalid_code_product_decision_signature": _canonical_invalid_code_product_decision_signature,
            "code_product_action_has_complete_payload": code_product_action_has_complete_payload,
            "code_product_build_state_propose_action": _code_product_build_state_propose_action,
            "code_product_build_state_read_action": _code_product_build_state_read_action,
            "code_product_build_state_write_action": _code_product_build_state_write_action,
            "code_product_candidate_action": _code_product_candidate_action,
            "code_product_payload_rejection_count": _code_product_payload_rejection_count,
            "code_product_payload_violations": code_product_payload_violations,
            "code_product_source_window_candidate": _code_product_source_window_candidate,
            "compact_validation_rejections_tail": _compact_validation_rejections_tail,
            "core_discovery_candidates_from_intrinsic": core_discovery_candidates_from_intrinsic,
            "disallowed_invalid_code_product_signatures": disallowed_invalid_code_product_signatures,
            "failed_code_edit_proposal_validation_row": failed_code_edit_proposal_validation_row,
            "file_memory_from_history": file_memory_from_history,
            "goal_exact_text_block": goal_exact_text_block,
            "goal_target_file": _goal_target_file,
            "goal_target_kind": _goal_target_kind,
            "initial_orientation_surface_from_history": initial_orientation_surface_from_history,
            "input_error_goal": input_error_goal,
            "latest_code_product_build_state": latest_code_product_build_state,
            "low_signal_top_dir": low_signal_top_dir,
            "meaningful_read_candidates_from_evidence": meaningful_read_candidates_from_evidence,
            "path_exists_repo_relative": path_exists_repo_relative,
            "path_under_scope": path_under_scope,
            "paths_from_list_rows": paths_from_list_rows,
            "paths_from_result": paths_from_result,
            "planner_scratchpad_window_signature": planner_scratchpad_window_signature,
            "rank_core_candidates": rank_core_candidates,
            "repo_analysis_goal": repo_analysis_goal,
            "repo_code_file": repo_code_file,
            "repo_doc_or_config": repo_doc_or_config,
            "repo_list_evidence": repo_list_evidence,
            "repo_read_window_signature": repo_read_window_signature,
            "repo_readable_evidence_file": repo_readable_evidence_file,
            "repo_rel_token": repo_rel_token,
            "repo_required_read_count": repo_required_read_count,
            "scope_read_candidates_from_evidence": scope_read_candidates_from_evidence,
            "scoped_required_read_count": scoped_required_read_count,
            "user_scope_claims": _user_scope_claims,
            "verified_repo_read_content_rows": _verified_repo_read_content_rows,
            "goal_requested_repo_scope": goal_requested_repo_scope,
            "goal_requires_code_security_coverage": goal_requires_code_security_coverage,
            "goal_requests_apply": goal_requests_apply,
            "goal_requests_code_product": goal_requests_code_product,
            "history_has_tool": history_has_tool,
            "latest_file_list_result": latest_file_list_result,
            "requested_file_limit_from_goal": _requested_file_limit_from_goal,
            "semantic_goal_classification": semantic_goal_classification,
            "successful_window_signatures": successful_window_signatures,
            "successful_code_edit_proposals": successful_code_edit_proposals,
            "successful_repo_read_paths": successful_repo_read_paths,
            "failed_repo_read_paths": failed_repo_read_paths,
        },
        config={
            "CODE_PRODUCT_BUILD_STATE_KIND": "code_product_build_state",
            "LAB_REPO": "C:\\Users\\carmi\\AI",  # Default - will be overridden by config import
            "REPO_CONCRETE_READ_TARGET": 20,
            "SCOPED_CONCRETE_READ_TARGET": 10,
        },
    )


# ---------------------------------------------------------------------------
# Operational notebook builder
# ---------------------------------------------------------------------------

def _build_operational_notebook(goal: str, contract: dict[str, Any]) -> dict[str, Any]:
    """Build an operational notebook from the evidence contract.

    This provides a compact summary of what has been read, what files are
    candidates, and what the next recommended actions are. Used as context
    for the planner's decision-making.
    """
    from .agentic_v2 import _list_or_empty, _dict_or_empty

    memory = _list_or_empty(contract.get("file_memory"))
    list_rows = _list_or_empty(contract.get("repo_list_files_evidence"))
    core = _list_or_empty(contract.get("ranked_core_candidate_dirs"))
    final_contract = _dict_or_empty(contract.get("finalization_contract"))
    final_allowed = bool(final_contract.get("final_allowed"))
    validation_rejections_tail = _list_or_empty(contract.get("validation_rejections_tail"))

    return {
        "schema": "agentic_loop_operational_notes.v1",
        "goal": goal,
        "final_allowed": final_allowed,
        "next_instruction": (
            "Quality gate is satisfied and final is allowed, not required. Prefer final from read_notes, "
            "mentioned_paths, core_candidates, workflow/problems evidence, and limits when no concrete "
            "evidence gap remains; otherwise name the gap and choose one selective evidence-bound tool."
            if final_allowed else
            "Continue only with one evidence-bound unread doc/code candidate. Do not repeat prior tool calls."
        ),
        "read_notes": [
            {
                "path": item.get("path"),
                "headings": (item.get("headings") or [])[:8],
                "key_lines": (item.get("key_lines") or [])[:10],
                "mentioned_paths": (item.get("mentioned_paths") or [])[:14],
                "excerpt": str(item.get("content_excerpt") or "")[:700],
            }
            for item in memory[:18]
            if isinstance(item, dict)
        ],
        "list_notes": list_rows[-8:],
        "core_candidates": core[:8],
        "candidate_next_actions": contract.get("candidate_next_actions") or [],
        "recent_rejections": validation_rejections_tail[-8:],
        "known_problem": (
            "Do not reduce this job to path counters or directory names. Use read_notes as the working scratchpad "
            "and cite concrete evidence from them."
        ),
    }


# ---------------------------------------------------------------------------
# Candidate actions from evidence
# ---------------------------------------------------------------------------

def _candidate_actions_from_evidence(
    goal: str,
    file_memory: list[dict[str, Any]],
    list_rows: list[dict[str, Any]],
    read_ok: list[str],
    final_allowed: bool,
    failed_list_paths: list[str] | None = None,
    core_discovery_candidates: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Generate candidate next actions based on all available evidence."""
    from .agentic_v2 import (
        decision_paths,
        path_under_scope,
    )
    from .goal_classifier import (
        _repo_analysis_goal,
        repo_doc_or_config,
        low_signal_top_dir,
        repo_code_file,
        repo_readable_evidence_file,
    )
    from .code_product_state import (
        _rank_core_candidates,
    )
    from ..evidence.core_discovery import core_discovery_read_paths
    from ..evidence.repo_path_policy import scope_read_candidates_from_evidence, meaningful_read_candidates_from_evidence
    from .goal_classifier import (
        SCOPED_CONCRETE_READ_TARGET,
        REPO_CONCRETE_READ_TARGET,
        _single_file_prompt_read_chars,
        _multi_file_prompt_read_chars,
    )

    return _candidate_actions_from_evidence(
        goal,
        file_memory,
        list_rows,
        read_ok,
        final_allowed,
        failed_list_paths=failed_list_paths,
        core_discovery_candidates=core_discovery_candidates,
        repo_rel_token=_repo_rel_token,
        repo_analysis_goal=_repo_analysis_goal,
        repo_doc_or_config=repo_doc_or_config,
        low_signal_top_dir=low_signal_top_dir,
        rank_core_candidates=_rank_core_candidates,
        path_exists_repo_relative=path_exists_repo_relative,
        goal_target_scope=_goal_target_scope,
        input_error_goal=input_error_goal,
        path_under_scope=path_under_scope,
        core_discovery_read_paths=core_discovery_read_paths,
        scoped_concrete_read_target=SCOPED_CONCRETE_READ_TARGET,
        repo_concrete_read_target=REPO_CONCRETE_READ_TARGET,
        scope_read_candidates_from_evidence=scope_read_candidates_from_evidence,
        multi_file_prompt_read_chars=_multi_file_prompt_read_chars,
        meaningful_read_candidates_from_evidence=meaningful_read_candidates_from_evidence,
        single_file_prompt_read_chars=_single_file_prompt_read_chars,
        repo_code_file=repo_code_file,
        repo_readable_evidence_file=repo_readable_evidence_file,
    )


# ---------------------------------------------------------------------------
# Initial orientation surface
# ---------------------------------------------------------------------------

def initial_orientation_surface_from_history(
    history: list[dict[str, Any]],
    skipped: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the initial orientation surface from read history.

    This extracts what files have been read, what directories exist,
    and provides context about the repository structure for the planner.
    """
    from .agentic_v2 import (
        repo_rel_token,
        repo_doc_or_config,
        low_signal_top_dir,
        path_under_scope,
    )
    return {
        "schema": "initial_orientation_surface.v1",
        "history_items": len(history),
        "skipped_items": len(skipped) if skipped else 0,
        "repo_files_read": [
            item.get("path")
            for item in history
            if isinstance(item, dict) and item.get("tool") == "repo_read"
        ],
        "repo_dirs_explored": [
            item.get("path")
            for item in history
            if isinstance(item, dict) and item.get("tool") in ("repo_tree", "repo_list_files")
        ],
    }


# ---------------------------------------------------------------------------
# Local helper imports used by evidence contract builder
# ---------------------------------------------------------------------------

def _goal_target_kind(goal: str) -> str:
    """Classify the goal target kind."""
    from .goal_classifier import (
        _goal_target_file,
        _goal_target_scope,
        _repo_analysis_goal,
    )
    if _goal_target_file(goal):
        return "file"
    if _goal_target_scope(goal):
        return "directory"
    if _repo_analysis_goal(goal):
        return "repository"
    return "other"


def input_error_goal(goal: str) -> bool:
    """Return True if the goal is an input-error diagnostic request."""
    from .goal_classifier import input_error_goal as _inner
    return _inner(goal)


def path_under_scope(path: str, scope: str) -> bool:
    """Check if path is under the given scope."""
    from .agentic_v2 import path_under_scope as _inner
    return _inner(path, scope)


def _repo_rel_token(path: str) -> str:
    """Normalize a repo path token."""
    from aicarmine_broker.infrastructure.repo_tools import repo_rel_token as _inner
    return _inner(path)


def path_exists_repo_relative(path: str) -> bool:
    """Check if a path exists relative to the repository root."""
    from aicarmine_broker.infrastructure.repo_tools import safe_rel_path
    from aicarmine_broker.config import LAB_REPO
    try:
        rel = safe_rel_path(path)
        full = (LAB_REPO / rel).resolve(strict=False)
        full.relative_to(LAB_REPO)
        return full.exists()
    except Exception:
        return False


def latest_file_list_result(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract the latest repo_list_files or repo_tree result from history."""
    for item in reversed(history):
        from ..shared.tool_result import history_tool_result
        result = history_tool_result(item)
        if result.get("tool") in {"repo_list_files", "repo_tree"} and result.get("ok"):
            return result
    return {}


def _goal_target_scope(goal: str) -> str:
    """Return the target scope (directory) for this goal."""
    from .goal_classifier import goal_requested_repo_scope
    from .agentic_v2 import _agentic_v2_goal_scope
    scope = _agentic_v2_goal_scope(goal, {}) or goal_requested_repo_scope(goal)
    return scope if scope else ""


def _requested_file_limit_from_goal(goal: str, default: int = 0) -> int:
    """Extract the requested file limit from the goal text."""
    from .agentic_v2 import requested_file_limit_from_goal as _inner
    return _inner(goal, default)


# ---------------------------------------------------------------------------
# Local aliases for backward compatibility with planner.py imports
# ---------------------------------------------------------------------------
_build_operational_notebook = _build_operational_notebook
_candidate_actions_from_evidence = _candidate_actions_from_evidence
initial_orientation_surface_from_history = initial_orientation_surface_from_history

__all__ = [
    "planner_evidence_contract",
    "_build_operational_notebook",
    "_candidate_actions_from_evidence",
    "initial_orientation_surface_from_history",
]
