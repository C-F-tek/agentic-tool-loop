"""Route validation and tool call processing."""

from __future__ import annotations

from typing import Any, Mapping

from aicarmine_broker.application.evidence.audit_guidance import goal_requests_semantic_audit
from aicarmine_broker.application.evidence.goal_classifier import effective_repo_analysis_goal
from aicarmine_broker.application.tool_surface.required_tool_call import (
    append_stale_required_call_marker,
    required_next_tool_call_satisfaction,
)
from aicarmine_broker.application.shared.path_tokens import repo_path_token as _repo_path_token, repo_rel_token

# Import validation utilities from shared module
from aicarmine_broker.application.shared.validation_utils import (
    _list_or_empty,
    _repo_path_is_concrete,
    _coalesce_repo_read_paths,
    _final_quality_repo_read_allowlist,
    _collect_repo_paths,
    _known_contract_repo_paths,
    _known_contract_repo_dirs,
    _route_token_is_prose_or_metric,
    _search_query_is_concrete,
    _required_next_route_has_deterministic_proof,
)


def _normalize_terminal_planner_decision(
    decision: dict[str, Any]
) -> dict[str, Any]:
    """Normalize terminal planner decision."""
    # Note: dispatch_tool, normalize_tool_name, sanitize_tool_args were imported via _resolve_lazy
    # but are no longer used after removing duplicate local definitions.
    return decision


# Re-exported from validation_utils to avoid F811 redefined-while-unused:
# The functions below are imported at module level (lines 16-27) and used throughout this file.
# Local redefinitions have been removed; use the imported versions directly.
_list_or_empty = _list_or_empty
_repo_path_is_concrete = _repo_path_is_concrete
_coalesce_repo_read_paths = _coalesce_repo_read_paths
_final_quality_repo_read_allowlist = _final_quality_repo_read_allowlist
_collect_repo_paths = _collect_repo_paths
_known_contract_repo_paths = _known_contract_repo_paths
_known_contract_repo_dirs = _known_contract_repo_dirs
_route_token_is_prose_or_metric = _route_token_is_prose_or_metric
_search_query_is_concrete = _search_query_is_concrete
_required_next_route_has_deterministic_proof = _required_next_route_has_deterministic_proof


def _coalesce_required_next_missing_paths(values: Any) -> list[str]:
    out: list[str] = []
    if not isinstance(values, (list, tuple, set)):
        return out
    for value in values:
        token = repo_rel_token(value)
        if token and token not in out:
            out.append(token)
    return out[:12]


def _stale_required_next_repo_read_paths() -> set[str]:
    paths: set[str] = set()
    # This function would need to be implemented based on the actual contract processing
    return paths


def _successful_read_paths_for_final_route() -> set[str]:
    # This function would need to be implemented based on the actual contract processing
    return set()


def _path_allowed_by_missing_evidence(path: str, required_missing: list[str]) -> bool:
    # This function would need to be implemented based on the actual contract processing
    return False


def _verified_required_next_missing_paths(values: Any) -> tuple[list[str], list[str]]:
    valid: list[str] = []
    invalid: list[str] = []
    # This function would need to be implemented based on the actual contract processing
    return valid[:12], invalid[:12]


def _required_next_tool_from_missing_evidences(values: Any, allow_if_missing: bool) -> dict[str, Any]:
    # This function would need to be implemented based on the actual contract processing
    return {}


def _coalesce_required_next_tool_tool(value: dict[str, Any]) -> dict[str, Any]:
    # This function would need to be implemented based on the actual contract processing
    return {}


def _coerce_final_rewrite_latch(value: Any) -> str:
    # This function would need to be implemented based on the actual contract processing
    return "inactive"


def _required_gap_paths_from_quality(
    quality: Mapping[str, Any],
    *,
    existing_missing: list[str],
) -> list[str]:
    # This function would need to be implemented based on the actual contract processing
    return []


def _apply_final_quality_route(quality: dict[str, Any]) -> None:
    # This function would need to be implemented based on the actual contract processing
    pass