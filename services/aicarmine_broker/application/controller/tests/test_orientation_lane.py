"""Tests for orientation_lane module.

Covers:
- orientation_shadow_effective_mode
- orientation_legacy_selected_candidate_ids
- orientation_shadow_selection_metrics
- _apply_runtime_metadata
- _extract_orientation_response_object
- sanitize_orientation_selection
- controller_orientation_model_select
"""

import json
import pytest
from unittest.mock import MagicMock

from services.aicarmine_broker.application.controller.orientation_lane import (
    orientation_shadow_effective_mode,
    orientation_legacy_selected_candidate_ids,
    orientation_shadow_selection_metrics,
    _apply_runtime_metadata,
    _extract_orientation_response_object,
    sanitize_orientation_selection,
    controller_orientation_model_select,
)


# =============================================================================
# orientation_shadow_effective_mode
# =============================================================================

class TestOrientationShadowEffectiveMode:
    """Tests for orientation_shadow_effective_mode."""

    def test_shadow_string_returns_shadow(self):
        """Test that 'shadow' string returns 'shadow'."""
        result = orientation_shadow_effective_mode("shadow")
        assert result == "shadow"

    def test_shadow_uppercase_returns_shadow(self):
        """Test that 'SHADOW' normalized to lowercase returns 'shadow'."""
        result = orientation_shadow_effective_mode("SHADOW")
        assert result == "shadow"

    def test_shadow_with_whitespace_returns_shadow(self):
        """Test that ' shadow ' normalized returns 'shadow'."""
        result = orientation_shadow_effective_mode(" shadow ")
        assert result == "shadow"

    def test_non_string_returns_legacy(self):
        """Test that non-string inputs return 'legacy'."""
        assert orientation_shadow_effective_mode(None) == "legacy"
        assert orientation_shadow_effective_mode(123) == "legacy"
        assert orientation_shadow_effective_mode(True) == "legacy"
        assert orientation_shadow_effective_mode({"mode": "shadow"}) == "legacy"
        assert orientation_shadow_effective_mode(["shadow"]) == "legacy"

    def test_active_returns_legacy(self):
        """Test that 'active' returns 'legacy' (fail-closed)."""
        result = orientation_shadow_effective_mode("active")
        assert result == "legacy"

    def test_empty_string_returns_legacy(self):
        """Test that empty string returns 'legacy'."""
        result = orientation_shadow_effective_mode("")
        assert result == "legacy"

    def test_unknown_returns_legacy(self):
        """Test that unknown values return 'legacy'."""
        result = orientation_shadow_effective_mode("unknown")
        assert result == "legacy"

    def test_shadowing_returns_legacy(self):
        """Test that 'shadowing' (not exact match) returns 'legacy'."""
        result = orientation_shadow_effective_mode("shadowing")
        assert result == "legacy"

    def test_active_shadow_returns_legacy(self):
        """Test that 'active-shadow' returns 'legacy'."""
        result = orientation_shadow_effective_mode("active-shadow")
        assert result == "legacy"


# =============================================================================
# orientation_legacy_selected_candidate_ids
# =============================================================================

class TestOrientationLegacySelectedCandidateIds:
    """Tests for orientation_legacy_selected_candidate_ids."""

    def _make_candidate(self, candidate_id, path, candidate_class="root_doc"):
        """Helper to create a candidate dict."""
        return {
            "candidate_id": candidate_id,
            "path": path,
            "candidate_class": candidate_class,
        }

    def test_simple_root_doc_selection(self):
        """Test basic root_doc path selection."""
        candidates = [
            self._make_candidate("id-1", "/docs/readme.md", "root_doc"),
            self._make_candidate("id-2", "/docs/api.md", "root_doc"),
        ]
        doc_plan = {
            "arguments": {
                "paths": ["/docs/readme.md", "/docs/api.md"]
            }
        }
        result = orientation_legacy_selected_candidate_ids(
            candidates=candidates,
            doc_plan=doc_plan,
            area_plans=[],
        )
        assert result == ["id-1", "id-2"]

    def test_simple_root_area_selection(self):
        """Test basic root_area path selection."""
        candidates = [
            self._make_candidate("area-1", "/src/module", "root_area"),
        ]
        area_plans = [
            {"arguments": {"path": "/src/module"}},
        ]
        result = orientation_legacy_selected_candidate_ids(
            candidates=candidates,
            doc_plan=None,
            area_plans=area_plans,
        )
        assert result == ["area-1"]

    def test_mixed_doc_and_area_selection(self):
        """Test mixed document and area selection preserves order."""
        candidates = [
            self._make_candidate("doc-1", "/docs/a.md", "root_doc"),
            self._make_candidate("area-1", "/src/b", "root_area"),
            self._make_candidate("doc-2", "/docs/c.md", "root_doc"),
        ]
        doc_plan = {"arguments": {"paths": ["/docs/a.md"]}}
        area_plans = [
            {"arguments": {"path": "/src/b"}},
            {"arguments": {"path": "/docs/c.md"}},  # wrong class but still root_area key
        ]
        result = orientation_legacy_selected_candidate_ids(
            candidates=candidates,
            doc_plan=doc_plan,
            area_plans=area_plans,
        )
        # Docs first, then areas
        assert result[0] == "doc-1"
        assert result[1] == "area-1"
        # doc-2 not selected because /docs/c.md maps to root_doc key, not root_area
        assert "doc-2" not in result

    def test_duplicate_candidate_id_preserved_first_occurrence(self):
        """Test that duplicate candidate_ids are deduplicated preserving first."""
        candidates = [
            self._make_candidate("id-1", "/docs/a.md", "root_doc"),
            self._make_candidate("id-1", "/docs/b.md", "root_doc"),  # same id, different path
        ]
        doc_plan = {"arguments": {"paths": ["/docs/a.md", "/docs/b.md"]}}
        result = orientation_legacy_selected_candidate_ids(
            candidates=candidates,
            doc_plan=doc_plan,
            area_plans=[],
        )
        assert result.count("id-1") == 1

    def test_invalid_candidate_skipped(self):
        """Test that invalid candidates are skipped."""
        candidates = [
            {"candidate_id": 123, "path": "/docs/a.md", "candidate_class": "root_doc"},  # non-str id
            {"candidate_id": "id-1", "path": "", "candidate_class": "root_doc"},  # empty path
            {"candidate_id": "id-1", "path": "/docs/a.md", "candidate_class": "invalid"},  # invalid class
            self._make_candidate("id-valid", "/docs/valid.md", "root_doc"),
        ]
        doc_plan = {"arguments": {"paths": ["/docs/valid.md"]}}
        result = orientation_legacy_selected_candidate_ids(
            candidates=candidates,
            doc_plan=doc_plan,
            area_plans=[],
        )
        assert result == ["id-valid"]

    def test_empty_candidates_returns_empty(self):
        """Test empty candidates list returns empty result."""
        result = orientation_legacy_selected_candidate_ids(
            candidates=[],
            doc_plan=None,
            area_plans=[],
        )
        assert result == []

    def test_none_candidates_treated_as_empty(self):
        """Test None candidates treated as empty."""
        result = orientation_legacy_selected_candidate_ids(
            candidates=None,
            doc_plan=None,
            area_plans=[],
        )
        assert result == []

    def test_doc_plan_invalid_structure(self):
        """Test that invalid doc_plan structure is handled gracefully."""
        candidates = [self._make_candidate("id-1", "/docs/a.md", "root_doc")]
        # Missing arguments key
        doc_plan = {}
        result = orientation_legacy_selected_candidate_ids(
            candidates=candidates,
            doc_plan=doc_plan,
            area_plans=[],
        )
        assert result == []

    def test_area_plans_non_list_ignored(self):
        """Test that non-list area_plans is ignored."""
        candidates = [self._make_candidate("area-1", "/src/a", "root_area")]
        result = orientation_legacy_selected_candidate_ids(
            candidates=candidates,
            doc_plan=None,
            area_plans="not-a-list",
        )
        assert result == []

    def test_path_strip_normalization(self):
        """Test that paths are stripped before matching."""
        candidates = [self._make_candidate("id-1", "  /docs/a.md  ", "root_doc")]
        doc_plan = {"arguments": {"paths": ["  /docs/a.md  "]}}
        result = orientation_legacy_selected_candidate_ids(
            candidates=candidates,
            doc_plan=doc_plan,
            area_plans=[],
        )
        assert result == ["id-1"]

    def test_doc_plan_paths_with_invalid_items(self):
        """Test that invalid items in paths list are skipped."""
        candidates = [self._make_candidate("id-1", "/docs/a.md", "root_doc")]
        doc_plan = {
            "arguments": {
                "paths": [
                    "/docs/a.md",
                    123,  # non-string
                    "",   # empty after strip
                    None,  # None
                ]
            }
        }
        result = orientation_legacy_selected_candidate_ids(
            candidates=candidates,
            doc_plan=doc_plan,
            area_plans=[],
        )
        assert result == ["id-1"]

    def test_candidate_id_length_limit(self):
        """Test that candidate_id > 500 chars is rejected."""
        long_id = "x" * 501
        candidates = [self._make_candidate(long_id, "/docs/a.md", "root_doc")]
        doc_plan = {"arguments": {"paths": ["/docs/a.md"]}}
        result = orientation_legacy_selected_candidate_ids(
            candidates=candidates,
            doc_plan=doc_plan,
            area_plans=[],
        )
        assert result == []

    def test_no_modification_of_inputs(self):
        """Test that input structures are not modified."""
        import copy
        candidates = [self._make_candidate("id-1", "/docs/a.md", "root_doc")]
        doc_plan = {"arguments": {"paths": ["/docs/a.md"]}}
        area_plans = [{"arguments": {"path": "/src/b"}}]
        original_candidates = copy.deepcopy(candidates)
        original_doc_plan = copy.deepcopy(doc_plan)
        original_area_plans = copy.deepcopy(area_plans)

        orientation_legacy_selected_candidate_ids(
            candidates=candidates,
            doc_plan=doc_plan,
            area_plans=area_plans,
        )

        assert candidates == original_candidates
        assert doc_plan == original_doc_plan
        assert area_plans == original_area_plans


# =============================================================================
# orientation_shadow_selection_metrics
# =============================================================================

class TestOrientationShadowSelectionMetrics:
    """Tests for orientation_shadow_selection_metrics."""

    def test_basic_metrics(self):
        """Test basic metrics calculation."""
        result = orientation_shadow_selection_metrics(
            legacy_selected_candidate_ids=["id-1", "id-2", "id-3"],
            model_selected_candidate_ids=["id-1", "id-4"],
        )
        assert result["legacy_count"] == 3
        assert result["model_count"] == 2
        assert result["selection_overlap"] == ["id-1"]
        assert result["selection_overlap_count"] == 1
        assert result["top1_match"] is True
        assert result["exact_match"] is False
        assert result["would_change_selection"] is True

    def test_no_overlap(self):
        """Test when there is no overlap between legacy and model."""
        result = orientation_shadow_selection_metrics(
            legacy_selected_candidate_ids=["id-1", "id-2"],
            model_selected_candidate_ids=["id-3", "id-4"],
        )
        assert result["selection_overlap"] == []
        assert result["selection_overlap_count"] == 0
        assert result["top1_match"] is False

    def test_exact_match(self):
        """Test exact match scenario."""
        result = orientation_shadow_selection_metrics(
            legacy_selected_candidate_ids=["id-1", "id-2"],
            model_selected_candidate_ids=["id-1", "id-2"],
        )
        assert result["exact_match"] is True
        assert result["would_change_selection"] is False

    def test_top1_no_match(self):
        """Test top1 mismatch."""
        result = orientation_shadow_selection_metrics(
            legacy_selected_candidate_ids=["id-1"],
            model_selected_candidate_ids=["id-2"],
        )
        assert result["top1_match"] is False

    def test_empty_lists(self):
        """Test empty lists."""
        result = orientation_shadow_selection_metrics(
            legacy_selected_candidate_ids=[],
            model_selected_candidate_ids=[],
        )
        assert result["legacy_count"] == 0
        assert result["model_count"] == 0
        assert result["top1_match"] is False
        assert result["exact_match"] is True  # both empty = equal
        assert result["would_change_selection"] is False

    def test_sanitization_non_string_items(self):
        """Test that non-string items are filtered out."""
        result = orientation_shadow_selection_metrics(
            legacy_selected_candidate_ids=["id-1", 123, None, "id-2"],
            model_selected_candidate_ids=["id-1"],
        )
        assert result["legacy_count"] == 2
        assert result["selection_overlap"] == ["id-1"]

    def test_sanitization_empty_strings(self):
        """Test that empty strings after strip are filtered."""
        result = orientation_shadow_selection_metrics(
            legacy_selected_candidate_ids=["id-1", "   ", ""],
            model_selected_candidate_ids=["id-1"],
        )
        assert result["legacy_count"] == 1

    def test_sanitization_long_ids(self):
        """Test that IDs > 500 chars are filtered."""
        long_id = "x" * 501
        result = orientation_shadow_selection_metrics(
            legacy_selected_candidate_ids=[long_id, "id-1"],
            model_selected_candidate_ids=["id-1"],
        )
        assert result["legacy_count"] == 1

    def test_bounded_to_13(self):
        """Test that lists are bounded to 13 valid IDs."""
        legacy = [f"id-{i}" for i in range(20)]
        model = [f"id-{i}" for i in range(20)]
        result = orientation_shadow_selection_metrics(
            legacy_selected_candidate_ids=legacy,
            model_selected_candidate_ids=model,
        )
        assert result["legacy_count"] == 13
        assert result["model_count"] == 13

    def test_deduplication(self):
        """Test deduplication preserves first occurrence."""
        result = orientation_shadow_selection_metrics(
            legacy_selected_candidate_ids=["id-1", "id-1", "id-2"],
            model_selected_candidate_ids=["id-1"],
        )
        assert result["legacy_count"] == 2
        assert result["selection_overlap"] == ["id-1"]

    def test_input_not_modified(self):
        """Test that input lists are not modified."""
        import copy
        legacy = ["id-1", "id-2"]
        model = ["id-1"]
        original_legacy = copy.deepcopy(legacy)
        original_model = copy.deepcopy(model)

        orientation_shadow_selection_metrics(
            legacy_selected_candidate_ids=legacy,
            model_selected_candidate_ids=model,
        )

        assert legacy == original_legacy
        assert model == original_model

    def test_non_list_inputs(self):
        """Test that non-list inputs are treated as empty."""
        result = orientation_shadow_selection_metrics(
            legacy_selected_candidate_ids="not-a-list",
            model_selected_candidate_ids=None,
        )
        assert result["legacy_count"] == 0
        assert result["model_count"] == 0

    def test_output_schema_completeness(self):
        """Test that output contains all required keys."""
        result = orientation_shadow_selection_metrics(
            legacy_selected_candidate_ids=["id-1"],
            model_selected_candidate_ids=["id-1"],
        )
        assert "legacy_count" in result
        assert "model_count" in result
        assert "selection_overlap" in result
        assert "selection_overlap_count" in result
        assert "top1_match" in result
        assert "exact_match" in result
        assert "would_change_selection" in result


# =============================================================================
# _apply_runtime_metadata
# =============================================================================

class TestApplyRuntimeMetadata:
    """Tests for _apply_runtime_metadata."""

    def test_applies_all_metadata(self):
        """Test that all metadata fields are applied."""
        result = {"ok": True}
        metadata = _apply_runtime_metadata(
            result,
            planner_model="qwen3",
            planner_url="http://localhost:3572",
            timeout_seconds=30,
            keep_alive="5m",
        )
        assert metadata["planner_model"] == "qwen3"
        assert metadata["planner_url"] == "http://localhost:3572"
        assert metadata["timeout_seconds"] == 30
        assert metadata["keep_alive"] == "5m"

    def test_does_not_modify_input(self):
        """Test that input dict is not modified."""
        import copy
        original = {"ok": True}
        original_copy = copy.deepcopy(original)
        _apply_runtime_metadata(
            original,
            planner_model="qwen3",
            planner_url="http://localhost:3572",
            timeout_seconds=30,
            keep_alive="5m",
        )
        assert original == original_copy

    def test_deep_copy_behavior(self):
        """Test that nested structures are deep copied."""
        original = {"nested": {"key": "value"}}
        metadata = _apply_runtime_metadata(
            original,
            planner_model="qwen3",
            planner_url="http://localhost:3572",
            timeout_seconds=30,
            keep_alive="5m",
        )
        metadata["nested"]["new_key"] = "new_value"
        assert original["nested"] == {"key": "value"}


# =============================================================================
# _extract_orientation_response_object
# =============================================================================

class TestExtractOrientationResponseObject:
    """Tests for _extract_orientation_response_object."""

    def test_non_dict_returns_none(self):
        """Test that non-dict responses return (None, 'response_not_dict')."""
        extracted, reason = _extract_orientation_response_object("not-a-dict")
        assert extracted is None
        assert reason == "response_not_dict"

        extracted, reason = _extract_orientation_response_object(123)
        assert extracted is None
        assert reason == "response_not_dict"

        extracted, reason = _extract_orientation_response_object(None)
        assert extracted is None
        assert reason == "response_not_dict"

    def test_direct_decision_select(self):
        """Test direct decision select returns copied dict."""
        response = {"decision": "select", "selected_candidate_ids": ["id-1"]}
        extracted, reason = _extract_orientation_response_object(response)
        assert reason == "direct_decision"
        assert extracted["decision"] == "select"
        assert extracted is not response  # is a copy

    def test_response_field_extraction(self):
        """Test response['response'] field extraction."""
        response = {"response": '{"decision": "select"}'}
        extracted, reason = _extract_orientation_response_object(response)
        assert reason == "parsed_json_object"
        assert extracted["decision"] == "select"

    def test_message_content_extraction(self):
        """Test response['message']['content'] extraction."""
        response = {
            "message": {
                "content": '{"decision": "select"}'
            }
        }
        extracted, reason = _extract_orientation_response_object(response)
        assert reason == "parsed_json_object"
        assert extracted["decision"] == "select"

    def test_partial_content_extraction(self):
        """Test response['partial_content'] extraction."""
        response = {"partial_content": '{"decision": "select"}'}
        extracted, reason = _extract_orientation_response_object(response)
        assert reason == "parsed_json_object"
        assert extracted["decision"] == "select"

    def test_extraction_priority_order(self):
        """Test that response field takes priority over message.content."""
        response = {
            "response": '{"decision": "select"}',
            "message": {"content": '{"decision": "deselect"}'},
        }
        extracted, reason = _extract_orientation_response_object(response)
        assert extracted["decision"] == "select"

    def test_empty_content_returns_none(self):
        """Test that empty content returns (None, 'empty_model_content')."""
        response = {"response": ""}
        extracted, reason = _extract_orientation_response_object(response)
        assert extracted is None
        assert reason == "empty_model_content"

    def test_invalid_json_returns_none(self):
        """Test that invalid JSON returns (None, 'invalid_json_response')."""
        response = {"response": "not-valid-json"}
        extracted, reason = _extract_orientation_response_object(response)
        assert extracted is None
        assert reason == "invalid_json_response"

    def test_json_not_object_returns_none(self):
        """Test that JSON array returns (None, 'json_response_not_object')."""
        response = {"response": "[1, 2, 3]"}
        extracted, reason = _extract_orientation_response_object(response)
        assert extracted is None
        assert reason == "json_response_not_object"

    def test_message_non_dict_content_ignored(self):
        """Test that message.content only accepts strings."""
        response = {"message": {"content": 123}}
        extracted, reason = _extract_orientation_response_object(response)
        assert extracted is None
        assert reason == "empty_model_content"


# =============================================================================
# sanitize_orientation_selection
# =============================================================================

class TestSanitizeOrientationSelection:
    """Tests for sanitize_orientation_selection."""

    def test_non_dict_input(self):
        """Test that non-dict input returns invalid."""
        result = sanitize_orientation_selection(
            value="not-a-dict",
            valid_candidate_ids={"id-1"},
            max_selected=5,
        )
        assert result["ok"] is False
        assert result["status"] == "invalid"
        assert result["rationale"] == "non_dict_input"

    def test_decision_not_select(self):
        """Test that decision != 'select' returns invalid."""
        result = sanitize_orientation_selection(
            value={"decision": "deselect"},
            valid_candidate_ids={"id-1"},
            max_selected=5,
        )
        assert result["ok"] is False
        assert result["rationale"] == "decision_not_select"

    def test_selected_not_list(self):
        """Test that selected_candidate_ids not list returns invalid."""
        result = sanitize_orientation_selection(
            value={"decision": "select", "selected_candidate_ids": "not-a-list"},
            valid_candidate_ids={"id-1"},
            max_selected=5,
        )
        assert result["ok"] is False
        assert result["rationale"] == "selected_candidate_ids_not_list"

    def test_valid_selection(self):
        """Test valid selection with correct candidate IDs."""
        result = sanitize_orientation_selection(
            value={
                "decision": "select",
                "selected_candidate_ids": ["id-1", "id-2"],
                "rationale": "good choice",
                "confidence": 0.9,
            },
            valid_candidate_ids={"id-1", "id-2"},
            max_selected=5,
        )
        assert result["ok"] is True
        assert result["status"] == "ready"
        assert result["selected_candidate_ids"] == ["id-1", "id-2"]
        assert result["rationale"] == "good choice"
        assert result["confidence"] == 0.9

    def test_unknown_candidate_ids(self):
        """Test that unknown IDs are separated."""
        result = sanitize_orientation_selection(
            value={
                "decision": "select",
                "selected_candidate_ids": ["id-1", "unknown-id"],
            },
            valid_candidate_ids={"id-1"},
            max_selected=5,
        )
        assert result["ok"] is True
        assert result["selected_candidate_ids"] == ["id-1"]
        assert result["unknown_candidate_ids"] == ["unknown-id"]

    def test_duplicate_removal(self):
        """Test that duplicates are tracked."""
        result = sanitize_orientation_selection(
            value={
                "decision": "select",
                "selected_candidate_ids": ["id-1", "id-1", "id-2"],
            },
            valid_candidate_ids={"id-1", "id-2"},
            max_selected=5,
        )
        assert result["ok"] is True
        assert result["selected_candidate_ids"] == ["id-1", "id-2"]
        assert result["duplicate_candidate_ids"] == ["id-1"]

    def test_max_selected_applied(self):
        """Test that max_selected limit is applied."""
        result = sanitize_orientation_selection(
            value={
                "decision": "select",
                "selected_candidate_ids": ["id-1", "id-2", "id-3"],
            },
            valid_candidate_ids={"id-1", "id-2", "id-3"},
            max_selected=2,
        )
        assert result["ok"] is True
        assert len(result["selected_candidate_ids"]) == 2
        assert result["selected_candidate_ids"] == ["id-1", "id-2"]

    def test_no_valid_candidates(self):
        """Test that no valid candidates returns ok=False."""
        result = sanitize_orientation_selection(
            value={
                "decision": "select",
                "selected_candidate_ids": ["unknown-1"],
            },
            valid_candidate_ids={"id-1"},
            max_selected=5,
        )
        assert result["ok"] is False
        assert result["rationale"] == "no_valid_candidates_selected"

    def test_none_items_in_list(self):
        """Test that None items in selected_candidate_ids are skipped."""
        result = sanitize_orientation_selection(
            value={
                "decision": "select",
                "selected_candidate_ids": [None, "id-1"],
            },
            valid_candidate_ids={"id-1"},
            max_selected=5,
        )
        assert result["ok"] is True
        assert result["selected_candidate_ids"] == ["id-1"]

    def test_empty_string_items_skipped(self):
        """Test that empty strings after strip are skipped."""
        result = sanitize_orientation_selection(
            value={
                "decision": "select",
                "selected_candidate_ids": ["   ", "", "id-1"],
            },
            valid_candidate_ids={"id-1"},
            max_selected=5,
        )
        assert result["ok"] is True
        assert result["selected_candidate_ids"] == ["id-1"]

    def test_confidence_validation(self):
        """Test confidence validation logic."""
        # Valid float
        result = sanitize_orientation_selection(
            value={"decision": "select", "selected_candidate_ids": ["id-1"], "confidence": 0.5},
            valid_candidate_ids={"id-1"},
            max_selected=5,
        )
        assert result["confidence"] == 0.5

        # Boolean rejected
        result = sanitize_orientation_selection(
            value={"decision": "select", "selected_candidate_ids": ["id-1"], "confidence": True},
            valid_candidate_ids={"id-1"},
            max_selected=5,
        )
        assert result["confidence"] is None

        # Out of range rejected
        result = sanitize_orientation_selection(
            value={"decision": "select", "selected_candidate_ids": ["id-1"], "confidence": 1.5},
            valid_candidate_ids={"id-1"},
            max_selected=5,
        )
        assert result["confidence"] is None

        # Negative rejected
        result = sanitize_orientation_selection(
            value={"decision": "select", "selected_candidate_ids": ["id-1"], "confidence": -0.1},
            valid_candidate_ids={"id-1"},
            max_selected=5,
        )
        assert result["confidence"] is None

    def test_schema_field(self):
        """Test that schema field is set correctly."""
        result = sanitize_orientation_selection(
            value={"decision": "select", "selected_candidate_ids": ["id-1"]},
            valid_candidate_ids={"id-1"},
            max_selected=5,
        )
        assert result["schema"] == "orientation_model_selection.v1"

    def test_no_exception_for_invalid_output(self):
        """Test that no exception is raised for invalid model output."""
        # Should not raise
        result = sanitize_orientation_selection(
            value="invalid",
            valid_candidate_ids={"id-1"},
            max_selected=5,
        )
        assert result["ok"] is False


# =============================================================================
# controller_orientation_model_select
# =============================================================================

class TestControllerOrientationModelSelect:
    """Tests for controller_orientation_model_select."""

    def _make_candidate(self, candidate_id, path="/docs/a.md", candidate_class="root_doc"):
        """Helper to create a candidate dict."""
        return {
            "candidate_id": candidate_id,
            "path": path,
            "candidate_class": candidate_class,
        }

    def _mock_post_json(self, url, body, timeout):
        """Mock post_json that returns a valid response."""
        return {
            "response": '{"decision": "select", "selected_candidate_ids": ["id-1"]}',
        }

    def _mock_post_json_backend_error(self, url, body, timeout):
        """Mock post_json that simulates backend error."""
        raise ConnectionError("Connection refused")

    def _mock_post_json_response_not_dict(self, url, body, timeout):
        """Mock post_json that returns non-dict."""
        return "not-a-dict"

    def _mock_post_json_backend_timeout(self, url, body, timeout):
        """Mock post_json that returns backend timeout."""
        return {"backend_timeout": True}

    def test_basic_selection(self):
        """Test basic model selection via POST."""
        candidates = [self._make_candidate("id-1")]
        result = controller_orientation_model_select(
            goal="Read the docs",
            semantic_intent={"intent": "read"},
            candidates=candidates,
            post_json=self._mock_post_json,
            planner_url="http://localhost:3572",
            planner_model="qwen3",
            keep_alive="5m",
            timeout_seconds=30,
            max_selected=5,
        )
        assert result["ok"] is True
        assert result["status"] == "ready"
        assert result["selected_candidate_ids"] == ["id-1"]
        assert result["planner_model"] == "qwen3"
        assert result["planner_url"] == "http://localhost:3572"

    def test_empty_pool_returns_unavailable(self):
        """Test that empty candidate pool returns unavailable."""
        result = controller_orientation_model_select(
            goal="Read the docs",
            semantic_intent={"intent": "read"},
            candidates=[],
            post_json=self._mock_post_json,
            planner_url="http://localhost:3572",
            planner_model="qwen3",
            keep_alive="5m",
            timeout_seconds=30,
            max_selected=5,
        )
        assert result["ok"] is False
        assert result["status"] == "unavailable"
        assert result["rationale"] == "no_valid_candidates_in_pool"

    def test_invalid_candidates_skipped(self):
        """Test that invalid candidates are skipped."""
        candidates = [
            {"candidate_id": None},  # None id
            {"candidate_id": ""},  # Empty id
            {"candidate_id": "x" * 501},  # Too long
            self._make_candidate("id-valid"),
        ]

        def mock_valid_selection(url, body, timeout):
            return {"response": '{"decision": "select", "selected_candidate_ids": ["id-valid"]}'}

        result = controller_orientation_model_select(
            goal="Read the docs",
            semantic_intent={"intent": "read"},
            candidates=candidates,
            post_json=mock_valid_selection,
            planner_url="http://localhost:3572",
            planner_model="qwen3",
            keep_alive="5m",
            timeout_seconds=30,
            max_selected=5,
        )
        assert result["ok"] is True
        assert result["selected_candidate_ids"] == ["id-valid"]

    def test_backend_exception(self):
        """Test backend exception handling."""
        candidates = [self._make_candidate("id-1")]
        result = controller_orientation_model_select(
            goal="Read the docs",
            semantic_intent={"intent": "read"},
            candidates=candidates,
            post_json=self._mock_post_json_backend_error,
            planner_url="http://localhost:3572",
            planner_model="qwen3",
            keep_alive="5m",
            timeout_seconds=30,
            max_selected=5,
        )
        assert result["ok"] is False
        assert result["rationale"] == "backend_exception"
        assert result["error_type"] == "ConnectionError"

    def test_response_not_dict(self):
        """Test non-dict response handling."""
        candidates = [self._make_candidate("id-1")]
        result = controller_orientation_model_select(
            goal="Read the docs",
            semantic_intent={"intent": "read"},
            candidates=candidates,
            post_json=self._mock_post_json_response_not_dict,
            planner_url="http://localhost:3572",
            planner_model="qwen3",
            keep_alive="5m",
            timeout_seconds=30,
            max_selected=5,
        )
        assert result["ok"] is False
        assert result["rationale"] == "response_not_dict"

    def test_backend_timeout(self):
        """Test backend timeout detection."""
        candidates = [self._make_candidate("id-1")]
        result = controller_orientation_model_select(
            goal="Read the docs",
            semantic_intent={"intent": "read"},
            candidates=candidates,
            post_json=self._mock_post_json_backend_timeout,
            planner_url="http://localhost:3572",
            planner_model="qwen3",
            keep_alive="5m",
            timeout_seconds=30,
            max_selected=5,
        )
        assert result["ok"] is False
        assert result["rationale"] == "backend_request_failed"
        assert result["status"] == "unavailable"
        assert result["backend_timeout"] is True

    def test_goal_bounded_to_4000(self):
        """Test that goal is bounded to 4000 chars."""
        long_goal = "x" * 10000
        called_body = None

        def capture_body(url, body, timeout):
            nonlocal called_body
            called_body = body
            return {"response": '{"decision": "select", "selected_candidate_ids": ["id-1"]}'}

        candidates = [self._make_candidate("id-1")]
        controller_orientation_model_select(
            goal=long_goal,
            semantic_intent={"intent": "read"},
            candidates=candidates,
            post_json=capture_body,
            planner_url="http://localhost:3572",
            planner_model="qwen3",
            keep_alive="5m",
            timeout_seconds=30,
            max_selected=5,
        )
        assert len(called_body["messages"][0]["content"]) <= 4000

    def test_duplicate_input_candidate_ids_tracked(self):
        """Test that duplicate input candidate IDs are tracked."""
        candidates = [
            self._make_candidate("id-1"),
            self._make_candidate("id-1"),  # duplicate
            self._make_candidate("id-2"),
        ]
        result = controller_orientation_model_select(
            goal="Read the docs",
            semantic_intent={"intent": "read"},
            candidates=candidates,
            post_json=self._mock_post_json,
            planner_url="http://localhost:3572",
            planner_model="qwen3",
            keep_alive="5m",
            timeout_seconds=30,
            max_selected=5,
        )
        assert "duplicate_input_candidate_ids" in result
        assert "id-1" in result["duplicate_input_candidate_ids"]

    def test_candidate_kind_normalization(self):
        """Test candidate kind normalization produces valid prompt candidates."""
        captured_request = {}

        def capture_candidates(url, body, timeout):
            captured_request["body"] = dict(body)
            return {"response": '{"decision": "select", "selected_candidate_ids": ["id-1"]}'}

        candidates = [
            {"candidate_id": "id-1", "kind": "  file  ", "candidate_class": "root_doc"},
            {"candidate_id": "id-2", "kind": None, "candidate_class": "root_area"},
        ]
        result = controller_orientation_model_select(
            goal="Read the docs",
            semantic_intent={"intent": "read"},
            candidates=candidates,
            post_json=capture_candidates,
            planner_url="http://localhost:3572",
            planner_model="qwen3",
            keep_alive="5m",
            timeout_seconds=30,
            max_selected=5,
        )
        # Verify POST was called with correct structure
        assert result["ok"] is True
        assert "body" in captured_request
        request_body = captured_request["body"]
        # Candidates are inside messages[1]["content"] as JSON
        content_str = request_body["messages"][1]["content"]
        orientation_req = json.loads(content_str)
        prompt_cands = orientation_req["candidates"]
        assert len(prompt_cands) == 2
        assert prompt_cands[0]["kind"] == "file"
        assert prompt_cands[1]["kind"] == "file"

    def test_candidate_class_normalization(self):
        """Test candidate class normalization produces valid prompt candidates."""
        captured_request = {}

        def capture_candidates(url, body, timeout):
            captured_request["body"] = dict(body)
            return {"response": '{"decision": "select", "selected_candidate_ids": ["id-1"]}'}

        candidates = [
            {"candidate_id": "id-1", "kind": "file", "candidate_class": "  root_doc  "},
            {"candidate_id": "id-2", "kind": "file", "candidate_class": None},
        ]
        result = controller_orientation_model_select(
            goal="Read the docs",
            semantic_intent={"intent": "read"},
            candidates=candidates,
            post_json=capture_candidates,
            planner_url="http://localhost:3572",
            planner_model="qwen3",
            keep_alive="5m",
            timeout_seconds=30,
            max_selected=5,
        )
        assert result["ok"] is True
        request_body = captured_request["body"]
        content_str = request_body["messages"][1]["content"]
        orientation_req = json.loads(content_str)
        prompt_cands = orientation_req["candidates"]
        assert len(prompt_cands) == 2
        assert prompt_cands[0]["candidate_class"] == "root_doc"
        assert prompt_cands[1]["candidate_class"] == "root_doc"

    def test_static_rank_normalization(self):
        """Test static_rank normalization (bool rejected, int accepted)."""
        captured_request = {}

        def capture_candidates(url, body, timeout):
            captured_request["body"] = dict(body)
            return {"response": '{"decision": "select", "selected_candidate_ids": ["id-1"]}'}

        candidates = [
            {"candidate_id": "id-1", "static_rank": 5},
            {"candidate_id": "id-2", "static_rank": True},  # bool rejected
            {"candidate_id": "id-3", "static_rank": "not-int"},  # non-int rejected
        ]
        result = controller_orientation_model_select(
            goal="Read the docs",
            semantic_intent={"intent": "read"},
            candidates=candidates,
            post_json=capture_candidates,
            planner_url="http://localhost:3572",
            planner_model="qwen3",
            keep_alive="5m",
            timeout_seconds=30,
            max_selected=5,
        )
        assert result["ok"] is True
        request_body = captured_request["body"]
        content_str = request_body["messages"][1]["content"]
        orientation_req = json.loads(content_str)
        prompt_cands = orientation_req["candidates"]
        assert len(prompt_cands) == 3
        assert prompt_cands[0]["static_rank"] == 5
        assert prompt_cands[1]["static_rank"] == 0  # bool -> 0
        assert prompt_cands[2]["static_rank"] == 0  # non-int -> 0

    def test_signals_normalization(self):
        """Test signals normalization (max 80 chars per signal, max 8 signals)."""
        captured_request = {}

        def capture_candidates(url, body, timeout):
            captured_request["body"] = dict(body)
            return {"response": '{"decision": "select", "selected_candidate_ids": ["id-1"]}'}

        long_signal = "x" * 100
        candidates = [
            {
                "candidate_id": "id-1",
                "signals": [long_signal, "short", None, "", "another"],
            }
        ]
        result = controller_orientation_model_select(
            goal="Read the docs",
            semantic_intent={"intent": "read"},
            candidates=candidates,
            post_json=capture_candidates,
            planner_url="http://localhost:3572",
            planner_model="qwen3",
            keep_alive="5m",
            timeout_seconds=30,
            max_selected=5,
        )
        assert result["ok"] is True
        request_body = captured_request["body"]
        content_str = request_body["messages"][1]["content"]
        orientation_req = json.loads(content_str)
        prompt_cands = orientation_req["candidates"]
        assert len(prompt_cands) == 1
        signals = prompt_cands[0]["signals"]
        assert len(signals) <= 8
        for s in signals:
            assert len(s) <= 80

    def test_request_structure(self):
        """Test that request structure follows contract."""
        called_body = None

        def capture_body(url, body, timeout):
            nonlocal called_body
            called_body = body
            return {"response": '{"decision": "select", "selected_candidate_ids": ["id-1"]}'}

        candidates = [self._make_candidate("id-1")]
        controller_orientation_model_select(
            goal="Read the docs",
            semantic_intent={"intent": "read"},
            candidates=candidates,
            post_json=capture_body,
            planner_url="http://localhost:3572",
            planner_model="qwen3",
            keep_alive="5m",
            timeout_seconds=30,
            max_selected=5,
        )
        # Check Ollama request structure
        assert called_body["model"] == "qwen3"
        assert called_body["format"] == "json"
        assert called_body["stream"] is False
        assert called_body["think"] is False
        assert called_body["options"]["temperature"] == 0
        assert called_body["keep_alive"] == "5m"

        # Check messages
        assert len(called_body["messages"]) == 2
        assert called_body["messages"][0]["role"] == "system"
        assert called_body["messages"][1]["role"] == "user"

    def test_runtime_metadata_applied(self):
        """Test that runtime metadata is applied to result."""
        candidates = [self._make_candidate("id-1")]
        result = controller_orientation_model_select(
            goal="Read the docs",
            semantic_intent={"intent": "read"},
            candidates=candidates,
            post_json=self._mock_post_json,
            planner_url="http://localhost:3572",
            planner_model="qwen3",
            keep_alive="5m",
            timeout_seconds=30,
            max_selected=5,
        )
        assert result["planner_model"] == "qwen3"
        assert result["planner_url"] == "http://localhost:3572"
        assert result["timeout_seconds"] == 30
        assert result["keep_alive"] == "5m"