"""Shared evidence builder base class to reduce code duplication."""

from typing import Any, Dict, List


class BaseEvidenceBuilder:
    """Base class for evidence builders to provide common functionality."""
    
    def __init__(self):
        """Initialize the evidence builder."""
        pass
    
    def _append_unique(self, values: List[str], value: Any) -> None:
        """Append unique value to list."""
        text = str(value or "").strip()
        if text and text not in values:
            values.append(text)
    
    def _clip_text(self, value: Any, limit: int) -> str:
        """Clip text to specified limit."""
        text = str(value or "")
        if len(text) <= limit:
            return text
        return text[:max(0, limit)] + f"\n...[truncated {len(text) - limit} chars]"
    
    def _compact_list(self, values: Any, *, limit: int = 12) -> List[Any]:
        """Compact list to specified limit."""
        if not isinstance(values, list):
            return []
        return values[:max(0, int(limit or 0))]
    
    def _compact_mapping(self, value: Any, *, text_limit: int = 500, list_limit: int = 8) -> Any:
        """Compact mapping to specified limits."""
        if isinstance(value, dict):
            out: Dict[str, Any] = {}
            for key, item in value.items():
                if item in (None, "", [], {}):
                    continue
                out[str(key)] = self._compact_mapping(item, text_limit=text_limit, list_limit=list_limit)
            return out
        if isinstance(value, list):
            return [self._compact_mapping(item, text_limit=text_limit, list_limit=list_limit) for item in value[:list_limit]]
        if isinstance(value, str):
            return self._clip_text(value, text_limit)
        return value
    
    def _repo_read_completed_paths(self, contract: dict[str, Any]) -> set[str]:
        """Get repository read completed paths."""
        # Implementation would go here based on actual logic from evidence/builder.py
        return set()
    
    def _repo_read_path_allowlist(self, contract: dict[str, Any]) -> set[str]:
        """Get repository read path allowlist."""
        # Implementation would go here based on actual logic from evidence/builder.py
        return set()
    
    def _known_repo_paths(self, contract: dict[str, Any]) -> set[str]:
        """Get known repository paths."""
        # Implementation would go here based on actual logic from evidence/builder.py
        return set()
    
    def _known_repo_dirs(self, paths: set[str]) -> set[str]:
        """Get known repository directories."""
        # Implementation would go here based on actual logic from evidence/builder.py
        return set()
    
    def _route_token_is_prose_or_metric(self, value: Any) -> bool:
        """Check if route token is prose or metric."""
        # Implementation would go here based on actual logic from evidence/builder.py
        return False
    
    def _search_query_is_concrete(self, value: Any) -> bool:
        """Check if search query is concrete."""
        # Implementation would go here based on actual logic from evidence/builder.py
        return False
    
    def _allowed_concrete_repo_path(self, value: Any, allowlist: set[str]) -> str:
        """Check if repository path is allowed."""
        # Implementation would go here based on actual logic from evidence/builder.py
        return ""
    
    def _normalize_required_next_tool_call_paths(self, paths: List[str]) -> List[str]:
        """Normalize required next tool call paths."""
        # Implementation would go here based on actual logic from evidence/builder.py
        return []
    
    def _required_next_output_sections(self, violations: List[str], metrics: Dict[str, Any]) -> List[str]:
        """Get required next output sections."""
        # Implementation would go here based on actual logic from evidence/builder.py
        return []
    
    def _required_next_missing_evidences(self, contract: dict[str, Any]) -> List[str]:
        """Get required next missing evidences."""
        # Implementation would go here based on actual logic from evidence/builder.py
        return []
    
    def _unverified_final_path_tokens(self, contract: dict[str, Any], paths: List[str], core_paths: List[str]) -> set[str]:
        """Get unverified final path tokens."""
        # Implementation would go here based on actual logic from evidence/builder.py
        return set()
    
    def _concept_present(self, text_low: str, patterns: tuple[str, ...]) -> bool:
        """Check if concept is present in text."""
        # Implementation would go here based on actual logic from evidence/builder.py
        return False
    
    def _absolute_no_issue_claim(self, text_low: str) -> bool:
        """Check if there's no issue claim."""
        # Implementation would go here based on actual logic from evidence/builder.py
        return False
    
    def _absolute_repo_no_issue_claim(self, text_low: str) -> bool:
        """Check if there's no repository issue claim."""
        # Implementation would go here based on actual logic from evidence/builder.py
        return False
    
    def _declares_partial_or_limited_coverage(self, text_low: str) -> bool:
        """Check if text declares partial or limited coverage."""
        # Implementation would go here based on actual logic from evidence/builder.py
        return False
    
    def _claims_deep_or_complete_review(self, text_low: str) -> bool:
        """Check if text claims deep or complete review."""
        # Implementation would go here based on actual logic from evidence/builder.py
        return False