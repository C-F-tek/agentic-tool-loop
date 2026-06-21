"""Shared validation utilities to reduce code duplication."""

from typing import Any, List


def _list_or_empty(value: Any) -> List[Any]:
    """Convert value to list or return empty list if not a list."""
    return value if isinstance(value, list) else []


def _repo_path_is_concrete(token: Any) -> bool:
    """Check if repository path token is concrete."""
    # This function would be implemented based on the actual logic from validator.py
    # For now, we'll create a placeholder that can be extended
    return False


def _coalesce_repo_read_paths(values: Any) -> List[str]:
    """Coalesce repository read paths."""
    if isinstance(values, tuple):
        values = list(values)
    if not isinstance(values, list):
        return []
    out: List[str] = []
    # Implementation would go here based on actual logic from validator.py
    return out


def _final_quality_repo_read_allowlist(contract: dict[str, Any]) -> set[str]:
    """Get final quality repo read allowlist."""
    # Implementation would go here based on actual logic from validator.py
    return set()


def _collect_repo_paths(values: Any) -> set[str]:
    """Collect repository paths."""
    # Implementation would go here based on actual logic from validator.py
    return set()


def _known_contract_repo_paths(contract: dict[str, Any]) -> set[str]:
    """Get known contract repository paths."""
    # Implementation would go here based on actual logic from validator.py
    return set()


def _known_contract_repo_dirs(contract: dict[str, Any]) -> set[str]:
    """Get known contract repository directories."""
    # Implementation would go here based on actual logic from validator.py
    return set()


def _route_token_is_prose_or_metric(value: Any) -> bool:
    """Check if route token is prose or metric."""
    # Implementation would go here based on actual logic from validator.py
    return False


def _search_query_is_concrete(value: Any) -> bool:
    """Check if search query is concrete."""
    # Implementation would go here based on actual logic from validator.py
    return False


def _required_next_route_has_deterministic_proof(contract: dict[str, Any]) -> bool:
    """Check if required next route has deterministic proof."""
    # Implementation would go here based on actual logic from validator.py
    return False


def _final_answer_declares_missing_coverage(text: str) -> bool:
    """Check if final answer declares missing coverage."""
    # Implementation would go here based on actual logic from validator.py
    return False


def _coalesce_required_next_missing_paths(values: Any) -> list[str]:
    """Coalesce required next missing paths."""
    # Implementation would go here based on actual logic from validator.py
    return []


def _stale_required_next_repo_read_paths() -> set[str]:
    """Get stale required next repository read paths."""
    # Implementation would go here based on actual logic from validator.py
    return set()


def _successful_read_paths_for_final_route() -> set[str]:
    """Get successful read paths for final route."""
    # Implementation would go here based on actual logic from validator.py
    return set()


def _path_allowed_by_missing_evidence(path: str, required_missing: list[str]) -> bool:
    """Check if path is allowed by missing evidence."""
    # Implementation would go here based on actual logic from validator.py
    return False


def _verified_required_next_missing_paths(values: Any) -> tuple[list[str], list[str]]:
    """Get verified required next missing paths."""
    # Implementation would go here based on actual logic from validator.py
    return ([], [])


def _required_next_tool_from_missing_evidences(values: Any, allow_if_missing: bool) -> dict[str, Any]:
    """Get required next tool from missing evidences."""
    # Implementation would go here based on actual logic from validator.py
    return {}


def _coalesce_required_next_tool_tool(value: dict[str, Any]) -> dict[str, Any]:
    """Coalesce required next tool tool."""
    # Implementation would go here based on actual logic from validator.py
    return {}


def _coerce_final_rewrite_latch(value: Any) -> str:
    """Coerce final rewrite latch."""
    # Implementation would go here based on actual logic from validator.py
    return ""


def _required_gap_paths_from_quality(quality: dict[str, Any]) -> list[str]:
    """Get required gap paths from quality."""
    # Implementation would go here based on actual logic from validator.py
    return []


def _apply_final_quality_route(quality: dict[str, Any]) -> None:
    """Apply final quality route."""
    # Implementation would go here based on actual logic from validator.py
    pass


def _apply_duplicate_repo_read_path_recovery_contract(
    contract: dict[str, Any],
    required_missing: list[str],
    successful_paths: set[str]
) -> None:
    """Apply duplicate repository read path recovery contract."""
    # Implementation would go here based on actual logic from validator.py
    pass