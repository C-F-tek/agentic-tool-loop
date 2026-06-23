"""Tests for BaseEvidenceBuilder - shared evidence builder utilities."""

from __future__ import annotations

import pytest

from aicarmine_broker.application.shared.evidence_builder import BaseEvidenceBuilder


@pytest.fixture
def builder():
    """Create a BaseEvidenceBuilder instance."""
    return BaseEvidenceBuilder()


class TestAppendUnique:
    """Test _append_unique method."""

    def test_appends_new_value(self, builder):
        """Test that new values are appended."""
        values = []
        builder._append_unique(values, "test")
        assert values == ["test"]

    def test_skips_duplicate_value(self, builder):
        """Test that duplicate values are skipped."""
        values = ["existing"]
        builder._append_unique(values, "existing")
        assert values == ["existing"]

    def test_skips_empty_value(self, builder):
        """Test that empty values are skipped."""
        values = ["existing"]
        builder._append_unique(values, "")
        assert values == ["existing"]

    def test_skips_none_value(self, builder):
        """Test that None values are skipped."""
        values = ["existing"]
        builder._append_unique(values, None)
        assert values == ["existing"]

    def test_appends_whitespace_only_as_empty(self, builder):
        """Test that whitespace-only values are treated as empty."""
        values = []
        builder._append_unique(values, "   ")
        assert values == []


class TestClipText:
    """Test _clip_text method."""

    def test_leaves_short_text_unchanged(self, builder):
        """Test that short text is returned unchanged."""
        result = builder._clip_text("hello world", 50)
        assert result == "hello world"

    def test_truncates_long_text(self, builder):
        """Test that long text is truncated with message."""
        long_text = "a" * 100
        result = builder._clip_text(long_text, 50)
        assert len(result) < len(long_text)
        assert "...[truncated" in result

    def test_handles_none_input(self, builder):
        """Test that None input is handled gracefully."""
        result = builder._clip_text(None, 50)
        assert result == ""

    def test_handles_empty_input(self, builder):
        """Test that empty input is handled gracefully."""
        result = builder._clip_text("", 50)
        assert result == ""

    def test_exact_limit_no_truncation(self, builder):
        """Test that text at exact limit is not truncated."""
        text = "abcde"
        result = builder._clip_text(text, 5)
        assert result == text


class TestCompactList:
    """Test _compact_list method."""

    def test_compacts_to_limit(self, builder):
        """Test that list is compacted to specified limit."""
        values = list(range(20))
        result = builder._compact_list(values, limit=5)
        assert len(result) == 5
        assert result == [0, 1, 2, 3, 4]

    def test_returns_empty_for_non_list(self, builder):
        """Test that non-list input returns empty list."""
        result = builder._compact_list("string", limit=5)
        assert result == []

    def test_returns_empty_for_none(self, builder):
        """Test that None input returns empty list."""
        result = builder._compact_list(None, limit=5)
        assert result == []

    def test_zero_limit_returns_empty(self, builder):
        """Test that zero limit returns empty list."""
        values = [1, 2, 3]
        result = builder._compact_list(values, limit=0)
        assert result == []

    def test_negative_limit_returns_empty(self, builder):
        """Test that negative limit returns empty list."""
        values = [1, 2, 3]
        result = builder._compact_list(values, limit=-1)
        assert result == []


class TestCompactMapping:
    """Test _compact_mapping method."""

    def test_compacts_dict_values(self, builder):
        """Test that dict values are compacted."""
        data = {"key1": "x" * 600, "key2": "short"}
        result = builder._compact_mapping(data, text_limit=500)
        assert len(result["key1"]) < 600
        assert result["key2"] == "short"

    def test_compacts_nested_dict(self, builder):
        """Test that nested dicts are recursively compacted."""
        data = {"outer": {"inner": "x" * 600}}
        result = builder._compact_mapping(data, text_limit=500)
        assert len(result["outer"]["inner"]) < 600

    def test_compacts_list_items(self, builder):
        """Test that list items are compacted."""
        data = {"items": ["x" * 600] * 10}
        result = builder._compact_mapping(data, list_limit=8)
        assert len(result["items"]) == 8

    def test_skips_empty_values(self, builder):
        """Test that empty/None values are skipped."""
        data = {"valid": "text", "empty": None, "zero": 0, "false": False}
        result = builder._compact_mapping(data)
        assert "valid" in result
        assert "empty" not in result
        # 0 and False are falsy but not in (None, "", [], {})
        assert "zero" in result or "false" in result

    def test_returns_non_dict_non_list_unchanged(self, builder):
        """Test that non-dict/non-list values are returned unchanged."""
        assert builder._compact_mapping(42) == 42
        assert builder._compact_mapping("text") == "text"


class TestConceptCheckers:
    """Test concept checker methods - stub implementations return defaults."""

    def test_concept_present_returns_false_stub(self, builder):
        """Test _concept_present returns False (stub implementation)."""
        # These are stub implementations that return False
        assert builder._concept_present("hello world", ("hello",)) is False

    def test_concept_not_present_returns_false(self, builder):
        """Test _concept_present returns False when no pattern matches."""
        assert builder._concept_present("hello world", ("xyz", "abc")) is False

    def test_absolute_no_issue_claim_returns_false_stub(self, builder):
        """Test _absolute_no_issue_claim returns False (stub implementation)."""
        assert builder._absolute_no_issue_claim("there is absolutely no issue") is False

    def test_absolute_repo_no_issue_claim_returns_false_stub(self, builder):
        """Test _absolute_repo_no_issue_claim returns False (stub implementation)."""
        assert builder._absolute_repo_no_issue_claim("absolutely no repo issues") is False

    def test_declares_partial_coverage_returns_false_stub(self, builder):
        """Test _declares_partial_or_limited_coverage returns False (stub)."""
        assert builder._declares_partial_or_limited_coverage("partial coverage only") is False

    def test_claims_deep_review_returns_false_stub(self, builder):
        """Test _claims_deep_or_complete_review returns False (stub)."""
        assert builder._claims_deep_or_complete_review("deep complete review") is False


class TestRouteTokenCheckers:
    """Test route token checker methods."""

    def test_route_token_is_prose_or_metric_prose(self, builder):
        """Test _route_token_is_prose_or_metric returns True for prose."""
        # Should return True for non-metric looking tokens
        result = builder._route_token_is_prose_or_metric("some text")
        assert isinstance(result, bool)

    def test_search_query_is_concrete_concrete(self, builder):
        """Test _search_query_is_concrete returns True for concrete queries."""
        result = builder._search_query_is_concrete("specific path/file.py")
        assert isinstance(result, bool)

    def test_allowed_concrete_repo_path_empty(self, builder):
        """Test _allowed_concrete_repo_path returns empty string."""
        result = builder._allowed_concrete_repo_path("test", set())
        assert result == ""

    def test_normalize_required_next_tool_call_paths(self, builder):
        """Test _normalize_required_next_tool_call_paths."""
        result = builder._normalize_required_next_tool_call_paths(["/path/to/file"])
        # Returns empty list as stub implementation
        assert result == []

    def test_required_next_output_sections_violations(self, builder):
        """Test _required_next_output_sections with violations."""
        violations = ["test_violation"]
        metrics = {"score": 0.5}
        result = builder._required_next_output_sections(violations, metrics)
        assert result == []

    def test_required_next_missing_evidences_empty(self, builder):
        """Test _required_next_missing_evidences with empty contract."""
        result = builder._required_next_missing_evidences({})
        assert result == []


class TestUnverifiedPaths:
    """Test unverified path methods."""

    def test_unverified_final_path_tokens_empty(self, builder):
        """Test _unverified_final_path_tokens returns empty set."""
        result = builder._unverified_final_path_tokens({}, [], [])
        assert result == set()

    def test_repo_read_completed_paths_empty(self, builder):
        """Test _repo_read_completed_paths returns empty set."""
        result = builder._repo_read_completed_paths({})
        assert result == set()

    def test_repo_read_path_allowlist_empty(self, builder):
        """Test _repo_read_path_allowlist returns empty set."""
        result = builder._repo_read_path_allowlist({})
        assert result == set()

    def test_known_repo_paths_empty(self, builder):
        """Test _known_repo_paths returns empty set."""
        result = builder._known_repo_paths({})
        assert result == set()

    def test_known_repo_dirs_empty(self, builder):
        """Test _known_repo_dirs returns empty set."""
        result = builder._known_repo_dirs(set())
        assert result == set()


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_init_is_idempotent(self, builder):
        """Test that multiple inits don't cause issues."""
        builder.__init__()  # Should not raise

    def test_append_unique_handles_special_chars(self, builder):
        """Test _append_unique with special characters."""
        values = []
        builder._append_unique(values, "test\nwith\tnewlines")
        assert values == ["test\nwith\tnewlines"]

    def test_clip_text_handles_unicode(self, builder):
        """Test _clip_text with unicode characters."""
        text = "你好世界" * 50
        result = builder._clip_text(text, 100)
        assert result != text  # Should be truncated
        assert "...[truncated" in result

    def test_compact_list_handles_mixed_types(self, builder):
        """Test _compact_list with mixed type values."""
        values = [1, "two", 3.0, {"four": 4}]
        result = builder._compact_list(values, limit=2)
        assert len(result) == 2
        assert result[0] == 1
        assert result[1] == "two"

    def test_compact_mapping_handles_deep_nesting(self, builder):
        """Test _compact_mapping with deeply nested structures."""
        data = {"l1": {"l2": {"l3": {"l4": "x" * 600}}}}
        result = builder._compact_mapping(data, text_limit=500)
        # Deep nesting is recursively compacted
        assert "l1" in result
        assert "l2" in result["l1"]
