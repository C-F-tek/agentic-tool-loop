"""Tests for services/aicarmine_broker/application/public_payload/payload_index_resolver.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.aicarmine_broker.application.public_payload.payload_index_resolver import (
    SCHEMA,
    resolve_field_path,
    resolve_payload_index,
    _parse_tool_context,
    _parse_tool_context_diagnostic,
    _payload_for_resolution,
    _payload_for_resolution_with_diagnostics,
    _is_empty,
    _tokenize_with_diagnostics,
    _tokenize,
    _resolve_tokens,
    _iter_location_values,
    _iter_index_targets,
)


class TestParseToolContext:
    """Tests for _parse_tool_context helper."""

    def test_dict_returns_as_is(self):
        result = _parse_tool_context({"key": "value"})
        assert result == {"key": "value"}

    def test_string_valid_json_returns_dict(self):
        result = _parse_tool_context('{"key": "value"}')
        assert result == {"key": "value"}

    def test_string_invalid_json_returns_as_is(self):
        result = _parse_tool_context("not valid json")
        assert result == "not valid json"

    def test_string_json_array_returns_as_is(self):
        result = _parse_tool_context("[1, 2, 3]")
        # _parse_tool_context returns the original string when JSON parses to non-dict
        assert result == "[1, 2, 3]"

    def test_none_returns_as_is(self):
        result = _parse_tool_context(None)
        assert result is None

    def test_int_returns_as_is(self):
        result = _parse_tool_context(42)
        assert result == 42


class TestParseToolContextDiagnostic:
    """Tests for _parse_tool_context_diagnostic helper."""

    def test_non_string_returns_empty(self):
        result = _parse_tool_context_diagnostic("field", 42)
        assert result == {}

    def test_valid_json_returns_empty(self):
        result = _parse_tool_context_diagnostic("field", '{"key": "value"}')
        assert result == {}

    def test_invalid_json_returns_diagnostic(self):
        result = _parse_tool_context_diagnostic("field", "{invalid}")
        assert result["field"] == "field"
        assert result["reason"] == "invalid_json"
        assert "error_type" in result

    def test_json_array_returns_diagnostic(self):
        result = _parse_tool_context_diagnostic("field", "[1, 2, 3]")
        assert result["reason"] == "parsed_value_not_object"
        assert result["decoded_type"] == "list"


class TestPayloadForResolution:
    """Tests for _payload_for_resolution helper."""

    def test_simple_payload(self):
        payload = {"key": "value"}
        result = _payload_for_resolution(payload)
        assert result is not payload  # returns copy

    def test_with_tool_context_string(self):
        payload = {
            "tool_context_for_30b": '{"key": "value"}',
            "other": "value"
        }
        result = _payload_for_resolution(payload)
        assert result["tool_context_for_30b"] == {"key": "value"}
        assert result["other"] == "value"

    def test_with_tool_context_non_string(self):
        payload = {
            "tool_context_for_30b": {"key": "value"},
            "other": "value"
        }
        result = _payload_for_resolution(payload)
        assert result["tool_context_for_30b"] == {"key": "value"}


class TestPayloadForResolutionWithDiagnostics:
    """Tests for _payload_for_resolution_with_diagnostics helper."""

    def test_valid_json_returns_empty_diagnostics(self):
        payload = {"tool_context_for_30b": '{"key": "value"}'}
        resolved, diagnostics = _payload_for_resolution_with_diagnostics(payload)
        assert diagnostics == []
        assert resolved["tool_context_for_30b"] == {"key": "value"}

    def test_invalid_json_returns_diagnostic(self):
        payload = {"tool_context_for_30b": "{invalid}"}
        resolved, diagnostics = _payload_for_resolution_with_diagnostics(payload)
        assert len(diagnostics) == 1
        assert diagnostics[0]["reason"] == "invalid_json"


class TestIsEmpty:
    """Tests for _is_empty helper."""

    def test_none_is_empty(self):
        assert _is_empty(None) is True

    def test_empty_string_is_empty(self):
        assert _is_empty("") is True

    def test_empty_list_is_empty(self):
        assert _is_empty([]) is True

    def test_empty_dict_is_empty(self):
        assert _is_empty({}) is True

    def test_non_empty_values_not_empty(self):
        assert _is_empty("value") is False
        assert _is_empty([1]) is False
        assert _is_empty({"key": "value"}) is False
        assert _is_empty(0) is False
        assert _is_empty(False) is False


class TestTokenizeWithDiagnostics:
    """Tests for _tokenize_with_diagnostics helper."""

    def test_simple_path(self):
        tokens, diagnostics = _tokenize_with_diagnostics("key")
        assert tokens == [("key", None)]
        assert diagnostics == []

    def test_path_with_index(self):
        tokens, diagnostics = _tokenize_with_diagnostics("key[5]")
        assert tokens == [("key", "5")]
        assert diagnostics == []

    def test_path_with_wildcard(self):
        tokens, diagnostics = _tokenize_with_diagnostics("key[*]")
        assert tokens == [("key", "*")]
        assert diagnostics == []

    def test_nested_path(self):
        tokens, diagnostics = _tokenize_with_diagnostics("a.b.c")
        assert tokens == [("a", None), ("b", None), ("c", None)]
        assert diagnostics == []

    def test_invalid_token(self):
        tokens, diagnostics = _tokenize_with_diagnostics("invalid[]")
        assert len(diagnostics) == 1
        assert diagnostics[0]["reason"] == "invalid_token_syntax"

    def test_empty_path(self):
        tokens, diagnostics = _tokenize_with_diagnostics("")
        assert tokens == []
        assert diagnostics == []

    def test_whitespace_skipped(self):
        tokens, diagnostics = _tokenize_with_diagnostics(" . key . ")
        assert tokens == [("key", None)]


class TestTokenize:
    """Tests for _tokenize helper."""

    def test_simple_path(self):
        result = _tokenize("key")
        assert result == [("key", None)]

    def test_path_with_index(self):
        result = _tokenize("key[5]")
        assert result == [("key", "5")]


class TestResolveTokens:
    """Tests for _resolve_tokens helper."""

    def test_simple_dict_access(self):
        current = {"key": "value"}
        tokens = [("key", None)]
        result = _resolve_tokens(current, tokens)
        assert result == ["value"]

    def test_nested_dict_access(self):
        current = {"a": {"b": {"c": "deep"}}}
        tokens = [("a", None), ("b", None), ("c", None)]
        result = _resolve_tokens(current, tokens)
        assert result == ["deep"]

    def test_list_index_access(self):
        current = {"items": [0, 1, 2]}
        tokens = [("items", None), (None, None)]  # Wait, this is wrong
        # Actually: items[1]
        tokens = [("items", "1")]
        result = _resolve_tokens(current, tokens)
        assert result == [1]

    def test_wildcard_access(self):
        current = {"items": [{"val": "a"}, {"val": "b"}]}
        tokens = [("items", "*"), ("val", None)]
        result = _resolve_tokens(current, tokens)
        assert set(result) == {"a", "b"}

    def test_missing_key_returns_empty(self):
        current = {"key": "value"}
        tokens = [("missing", None)]
        result = _resolve_tokens(current, tokens)
        assert result == []

    def test_missing_list_index_returns_empty(self):
        current = {"items": [1, 2]}
        tokens = [("items", "5")]
        result = _resolve_tokens(current, tokens)
        assert result == []

    def test_negative_index_returns_empty(self):
        current = {"items": [1, 2]}
        tokens = [("items", "-1")]
        result = _resolve_tokens(current, tokens)
        assert result == []

    def test_empty_tokens_returns_current(self):
        current = {"key": "value"}
        tokens = []
        result = _resolve_tokens(current, tokens)
        assert result == [current]

    def test_non_dict_key_returns_empty(self):
        current = "string"
        tokens = [("key", None)]
        result = _resolve_tokens(current, tokens)
        assert result == []

    def test_invalid_index_returns_empty(self):
        current = {"items": [1, 2]}
        tokens = [("items", "abc")]
        result = _resolve_tokens(current, tokens)
        assert result == []


class TestResolveFieldPath:
    """Tests for resolve_field_path function."""

    def test_simple_path(self):
        payload = {"key": "value"}
        result = resolve_field_path(payload, "key")
        assert result["path"] == "key"
        assert result["exists"] is True
        assert result["non_empty"] is True
        assert result["match_count"] == 1

    def test_missing_path(self):
        payload = {"key": "value"}
        result = resolve_field_path(payload, "missing")
        assert result["exists"] is False
        assert result["non_empty"] is False

    def test_nested_path(self):
        payload = {"a": {"b": {"c": "deep"}}}
        result = resolve_field_path(payload, "a.b.c")
        assert result["exists"] is True
        assert result["non_empty"] is True

    def test_list_path(self):
        payload = {"items": ["a", "b", "c"]}
        result = resolve_field_path(payload, "items[1]")
        assert result["exists"] is True
        assert result["non_empty"] is True
        assert result["match_count"] == 1

    def test_empty_value(self):
        payload = {"key": ""}
        result = resolve_field_path(payload, "key")
        assert result["exists"] is True
        assert result["non_empty"] is False

    def test_normalized_path_strips_whitespace(self):
        payload = {"key": "value"}
        result = resolve_field_path(payload, "  key  ")
        assert result["normalized_path"] == "key"

    def test_token_count(self):
        payload = {"a": {"b": "c"}}
        result = resolve_field_path(payload, "a.b")
        assert result["token_count"] == 2


class TestIterLocationValues:
    """Tests for _iter_location_values helper."""

    def test_string_returns_single(self):
        result = list(_iter_location_values("location"))
        assert result == ["location"]

    def test_dict_recursive(self):
        result = list(_iter_location_values({"a": "loc1", "b": {"c": "loc2"}}))
        assert set(result) == {"loc1", "loc2"}

    def test_nested_dict_recursive(self):
        result = list(_iter_location_values({
            "level1": {
                "level2": {
                    "level3": "deep_location"
                }
            }
        }))
        assert result == ["deep_location"]

    def test_empty_dict_returns_empty(self):
        result = list(_iter_location_values({}))
        assert result == []

    def test_none_returns_empty(self):
        result = list(_iter_location_values(None))
        assert result == []


class TestIterIndexTargets:
    """Tests for _iter_index_targets generator."""

    def test_concrete_results_iteration(self):
        payload_index = {
            "concrete_results": [
                {"primary_location": "loc1"},
                {"field": "loc2"},
            ]
        }
        result = list(_iter_index_targets(payload_index))
        assert len(result) == 2
        assert ("concrete_results", 0, "primary_location", "loc1") in result
        assert ("concrete_results", 1, "field", "loc2") in result

    def test_partial_results_iteration(self):
        payload_index = {
            "partial_results": [
                {"full_context_location": "loc3"},
            ]
        }
        result = list(_iter_index_targets(payload_index))
        assert ("partial_results", 0, "full_context_location", "loc3") in result

    def test_non_list_section_skipped(self):
        payload_index = {"concrete_results": "not a list"}
        result = list(_iter_index_targets(payload_index))
        assert result == []

    def test_non_dict_row_skipped(self):
        payload_index = {"concrete_results": ["not a dict"]}
        result = list(_iter_index_targets(payload_index))
        assert result == []

    def test_empty_location_skipped(self):
        payload_index = {"concrete_results": [{"primary_location": ""}]}
        result = list(_iter_index_targets(payload_index))
        assert result == []

    def test_multiple_keys_in_row(self):
        payload_index = {
            "concrete_results": [
                {"primary_location": "loc1", "field": "loc2", "full_context_location": "loc3"}
            ]
        }
        result = list(_iter_index_targets(payload_index))
        assert len(result) == 3


class TestResolvePayloadIndex:
    """Tests for resolve_payload_index function."""

    def test_missing_payload_index(self):
        payload = {}
        result = resolve_payload_index(payload)
        assert result["schema"] == SCHEMA
        assert result["ok"] is True
        assert result["target_count"] == 0

    def test_non_dict_payload_index(self):
        payload = {"payload_index_for_30b": "not a dict"}
        result = resolve_payload_index(payload)
        assert result["schema"] == SCHEMA
        assert result["target_count"] == 0

    def test_empty_concrete_results(self):
        payload = {
            "payload_index_for_30b": {
                "concrete_results": [],
                "partial_results": []
            }
        }
        result = resolve_payload_index(payload)
        assert result["schema"] == SCHEMA
        assert result["target_count"] == 0

    def test_resolved_target(self):
        payload = {
            "payload_index_for_30b": {
                "concrete_results": [
                    {"primary_location": "key"}
                ]
            },
            "key": "value"
        }
        result = resolve_payload_index(payload)
        assert result["ok"] is True
        assert len(result["resolved"]) == 1
        assert result["resolved"][0]["section"] == "concrete_results"

    def test_unresolved_target(self):
        payload = {
            "payload_index_for_30b": {
                "concrete_results": [
                    {"primary_location": "missing_key"}
                ]
            }
        }
        result = resolve_payload_index(payload)
        assert result["ok"] is False
        assert len(result["unresolved"]) == 1
        assert result["unresolved"][0]["reason"] == "missing_target"

    def test_empty_target(self):
        payload = {
            "payload_index_for_30b": {
                "concrete_results": [
                    {"primary_location": "empty_key"}
                ]
            },
            "empty_key": ""
        }
        result = resolve_payload_index(payload)
        assert result["ok"] is False
        assert len(result["empty_targets"]) == 1
        assert result["empty_targets"][0]["reason"] == "empty_target"

    def test_target_count(self):
        payload = {
            "payload_index_for_30b": {
                "concrete_results": [
                    {"primary_location": "key"}
                ]
            },
            "key": "value"
        }
        result = resolve_payload_index(payload)
        assert result["target_count"] == 1

    def test_complex_resolution(self):
        payload = {
            "payload_index_for_30b": {
                "concrete_results": [
                    {"primary_location": "a.b.c"},
                    {"field": "missing"},
                ],
                "partial_results": [
                    {"full_context_location": "d.e"}
                ]
            },
            "a": {"b": {"c": "deep_value"}}
        }
        result = resolve_payload_index(payload)
        assert result["target_count"] == 3
        assert len(result["resolved"]) == 1
        assert len(result["unresolved"]) == 2