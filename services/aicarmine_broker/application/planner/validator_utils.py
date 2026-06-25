"""Validator utility functions and helper methods."""

from __future__ import annotations

import json
from typing import Any, Mapping

from aicarmine_broker.application.evidence.audit_guidance import *
from aicarmine_broker.application.evidence.goal_classifier import *
from aicarmine_broker.application.tool_surface.required_tool_call import *
from aicarmine_broker.application.shared.path_tokens import *

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
# The functions below are imported at module level (lines 17-28) and used throughout this file.
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
