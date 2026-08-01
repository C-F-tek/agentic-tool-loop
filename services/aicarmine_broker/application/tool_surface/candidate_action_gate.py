"""Gate planner candidate actions byfrom services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

 proof metadata."""

from __future__ import annotations

from typing import Any

from ..shared.diagnostics import diagnostic_row, safe_text


def _proof(action: dict[str, Any]) -> dict[str, Any]:
    proof = action.get("action_proof") if isinstance(action.get("action_proof"), dict) else {}
    return proof


def _has_path_contract(action: dict[str, Any]) -> bool:
    proof = _proof(action)
    if any(proof.get(key) is not None for key in ("path_exists", "path_readable", "under_scope")):
        return True
    args = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
    tool = safe_text(action.get("tool"), limit=160).strip().replace(".", "_")
    if tool in {
        "repo_read",
        "repo_list_files",
        "repo_tree",
        "repo_search",
        "repo_write_file",
        "repo_apply_patch",
        "repo_propose_code_edit",
        "repo_validate",
    }:
        return any(key in args for key in ("path", "paths", "target", "target_file", "file_path"))
    return any(key in args for key in ("path", "paths", "file_path"))


def _requires_readable_evidence_path(action: dict[str, Any]) -> bool:
    tool = safe_text(action.get("tool"), limit=160).strip().replace(".", "_")
    return tool in {
        "repo_read",
        "repo_ast_grep_search",
        "repo_ast_grep_dry_run",
        "repo_tree_sitter_parse",
        "repo_propose_code_edit",
    }


def _allows_missing_target_path(action: dict[str, Any]) -> bool:
    tool = safe_text(action.get("tool"), limit=160).strip().replace(".", "_")
    return tool in {
        "repo_write_file",
    }


def candidate_rejection_reason(action: dict[str, Any]) -> str:
    try:
        if not isinstance(action, dict) or not action.get("tool"):
            return "invalid_candidate_action"
        proof = _proof(action)
        if not action.get("action_id") or not proof.get("source"):
            return "missing_action_proof"
        if _has_path_contract(action):
            if proof.get("path_exists") is not True and not _allows_missing_target_path(action):
                return "candidate_path_not_existing"
            if _requires_readable_evidence_path(action) and proof.get("path_readable") is not True:
                return "candidate_path_not_readable"
            if proof.get("under_scope") is False:
                return "candidate_path_out_of_scope"
        if action.get("tool") == "repo_read" and proof.get("validator_admissible") is not True:
            return "candidate_not_validator_admissible"
        return ""
    except Exception:
        return "candidate_action_evaluation_failed"


def gate_candidate_actions(actions: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> dict[str, Any]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for action in actions if isinstance(actions, (list, tuple)) else []:
        if not isinstance(action, dict):
            rejected.append({
                "tool": None,
                "arguments": {},
                "rejection_reason": "invalid_candidate_action",
                "action_rejection_diagnostics": [
                    diagnostic_row(
                        "candidate_action_not_object",
                        schema="candidate_action_rejection_diagnostic.v1",
                        received_type=type(action).__name__,
                    )
                ],
                "diagnostic_only": True,
            })
            continue
        reason = candidate_rejection_reason(action)
        if reason:
            row = dict(action)
            row["rejection_reason"] = reason
            row["action_rejection_diagnostics"] = [
                diagnostic_row(
                    reason,
                    schema="candidate_action_rejection_diagnostic.v1",
                    tool=safe_text(action.get("tool"), limit=160),
                    has_action_id=bool(action.get("action_id")),
                    has_action_proof=isinstance(action.get("action_proof"), dict),
                )
            ]
            row["diagnostic_only"] = True
            rejected.append(row)
            continue
        accepted.append(action)
    return {
        "candidate_next_actions": accepted,
        "rejected_candidate_actions": rejected,
        "diagnostic_only": True,
    }
