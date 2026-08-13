"""Tests for services/aicarmine_broker/application/public_payload/evidence_materializer.py."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.aicarmine_broker.application.public_payload.evidence_materializer import (
    MATERIALIZATION_SCHEMA,
    PRIMARY_SCHEMA,
    PRIORITY_SCHEMA,
    INDEX_KIND,
    PublicEvidenceMaterializer,
    _as_dict,
    _as_list,
    _clean,
    _iter_location_strings,
    _item_index_from_location,
    _first_location_value,
    _append_unique,
    materialize_public_evidence,
)


class TestAsDict:
    """Tests for _as_dict helper."""

    def test_dict_returns_as_is(self):
        result = _as_dict({"key": "value"})
        assert result == {"key": "value"}

    def test_string_valid_json_returns_dict(self):
        result = _as_dict('{"key": "value"}')
        assert result == {"key": "value"}

    def test_string_invalid_json_returns_empty(self):
        result = _as_dict("not valid json")
        assert result == {}

    def test_string_json_array_returns_empty(self):
        result = _as_dict("[1, 2, 3]")
        assert result == {}

    def test_none_returns_empty(self):
        result = _as_dict(None)
        assert result == {}

    def test_list_returns_empty(self):
        result = _as_dict([1, 2, 3])
        assert result == {}


class TestAsList:
    """Tests for _as_list helper."""

    def test_list_returns_as_is(self):
        result = _as_list([1, 2, 3])
        assert result == [1, 2, 3]

    def test_non_list_returns_empty(self):
        result = _as_list("string")
        assert result == []

    def test_dict_returns_empty(self):
        result = _as_list({"key": "value"})
        assert result == []

    def test_none_returns_empty(self):
        result = _as_list(None)
        assert result == []

    def test_int_returns_empty(self):
        result = _as_list(42)
        assert result == []


class TestClean:
    """Tests for _clean helper."""

    def test_dict_removes_empty_values(self):
        result = _clean({"key": "value", "empty": "", "none": None})
        assert result == {"key": "value"}

    def test_dict_keeps_non_empty_values(self):
        result = _clean({"key": "value", "list": [], "dict": {}})
        assert result == {"key": "value"}

    def test_list_removes_empty_items(self):
        result = _clean(["item", "", None, [], {}])
        assert result == ["item"]

    def test_nested_clean(self):
        result = _clean({"outer": {"inner": "value", "empty": ""}})
        assert result == {"outer": {"inner": "value"}}

    def test_string_returns_as_is(self):
        result = _clean("string")
        assert result == "string"

    def test_int_returns_as_is(self):
        result = _clean(42)
        assert result == 42


class TestIterLocationStrings:
    """Tests for _iter_location_strings helper."""

    def test_string_returns_single_item(self):
        result = list(_iter_location_strings("location"))
        assert result == ["location"]

    def test_dict_recursive(self):
        result = list(_iter_location_strings({"a": "loc1", "b": {"c": "loc2"}}))
        assert set(result) == {"loc1", "loc2"}

    def test_nested_dict_recursive(self):
        result = list(_iter_location_strings({
            "level1": {
                "level2": {
                    "level3": "deep_location"
                }
            }
        }))
        assert result == ["deep_location"]

    def test_empty_dict_returns_empty(self):
        result = list(_iter_location_strings({}))
        assert result == []

    def test_none_returns_empty(self):
        result = list(_iter_location_strings(None))
        assert result == []

    def test_mixed_types(self):
        result = list(_iter_location_strings({
            "str": "string_loc",
            "num": 42,
            "none": None,
            "nested": {"inner": "inner_loc"}
        }))
        assert "string_loc" in result
        assert "inner_loc" in result


class TestItemIndexFromLocation:
    """Tests for _item_index_from_location helper."""

    def test_valid_index_extracted(self):
        result = _item_index_from_location("priority_evidence_for_30b.items[5]")
        assert result == 5

    def test_invalid_index_returns_none(self):
        result = _item_index_from_location("priority_evidence_for_30b.items[abc]")
        assert result is None

    def test_no_match_returns_none(self):
        result = _item_index_from_location("no_match_here")
        assert result is None

    def test_empty_string_returns_none(self):
        result = _item_index_from_location("")
        assert result is None

    def test_dict_with_index(self):
        result = _item_index_from_location({"key": "priority_evidence_for_30b.items[10]"})
        assert result == 10

    def test_dict_without_index_returns_none(self):
        result = _item_index_from_location({"key": "no_index"})
        assert result is None


class TestFirstLocationValue:
    """Tests for _first_location_value helper."""

    def test_primary_location_returned(self):
        row = {"primary_location": "loc1", "field": "loc2"}
        result = _first_location_value(row)
        assert result == "loc1"

    def test_field_returned_when_no_primary(self):
        row = {"field": "loc2", "full_context_location": "loc3"}
        result = _first_location_value(row)
        assert result == "loc2"

    def test_full_context_location_returned(self):
        row = {"full_context_location": "loc3"}
        result = _first_location_value(row)
        assert result == "loc3"

    def test_empty_fields_returns_empty(self):
        row = {"primary_location": "", "field": None}
        result = _first_location_value(row)
        assert result == ""

    def test_empty_dict_returns_empty(self):
        result = _first_location_value({})
        assert result == ""


class TestAppendUnique:
    """Tests for _append_unique helper."""

    def test_appends_new_value(self):
        values: list[str] = []
        _append_unique(values, "new")
        assert values == ["new"]

    def test_skips_duplicate(self):
        values: list[str] = ["existing"]
        _append_unique(values, "existing")
        assert values == ["existing"]

    def test_skips_none(self):
        values: list[str] = []
        _append_unique(values, None)
        assert values == []

    def test_skips_empty_string(self):
        values: list[str] = []
        _append_unique(values, "")
        assert values == []

    def test_strips_whitespace(self):
        values: list[str] = []
        _append_unique(values, "  value  ")
        assert values == ["value"]

    def test_does_not_modify_input_for_none(self):
        values: list[str] = ["existing"]
        original = values.copy()
        _append_unique(values, None)
        assert values == original

    def test_string_conversion(self):
        values: list[str] = []
        _append_unique(values, 42)
        assert values == ["42"]


class TestMaterializePublicEvidence:
    """Tests for materialize_public_evidence compatibility function."""

    def test_empty_tool_context_returns_result(self):
        result = materialize_public_evidence(tool_context={})
        assert isinstance(result, dict)
        assert "materialization_report" in result

    def test_none_tool_context_returns_result(self):
        result = materialize_public_evidence(tool_context=None)
        assert isinstance(result, dict)

    def test_string_tool_context_parsed(self):
        ctx = json.dumps({"artifacts": []})
        result = materialize_public_evidence(tool_context=ctx)
        assert isinstance(result, dict)

    def test_default_evidence_guide(self):
        result = materialize_public_evidence(tool_context={}, evidence_guide="")
        assert isinstance(result, dict)

    def test_completed_flag(self):
        result = materialize_public_evidence(tool_context={}, completed=True)
        assert isinstance(result, dict)

    def test_internal_job_status(self):
        result = materialize_public_evidence(
            tool_context={},
            internal_job_status={"status": "running"}
        )
        assert isinstance(result, dict)


class TestPublicEvidenceMaterializer:
    """Tests for PublicEvidenceMaterializer class."""

    def test_materialize_empty_context(self):
        result = PublicEvidenceMaterializer().materialize(tool_context={})
        assert isinstance(result, dict)
        assert "materialization_report" in result

    def test_materialize_none_context(self):
        result = PublicEvidenceMaterializer().materialize(tool_context=None)
        assert isinstance(result, dict)

    def test_materialize_with_artifacts(self):
        ctx = {
            "artifacts": [
                {
                    "kind": "repo_read",
                    "content": "file content",
                    "repo_path": "test.py",
                    "line_count": 10
                }
            ]
        }
        result = PublicEvidenceMaterializer().materialize(tool_context=ctx)
        assert isinstance(result, dict)

    def test_materialization_report_structure(self):
        mat = PublicEvidenceMaterializer()
        report = mat._materialization_report(
            tool_context={},
            priority_evidence={},
            payload_index={},
            evidence_guide="guide"
        )
        assert "schema" in report
        assert "owner" in report
        assert "target_owner" in report
        assert "ok" in report
        assert "diagnostic_only" in report
        assert report["diagnostic_only"] is True

    def test_materialize_returns_primary_payload(self):
        result = PublicEvidenceMaterializer().materialize(tool_context={})
        assert "primary_payload_for_30b" in result
        assert "payload_index_for_30b" in result
        assert "priority_evidence_for_30b" in result
