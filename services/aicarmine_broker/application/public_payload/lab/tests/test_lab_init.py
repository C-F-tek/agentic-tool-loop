"""Tests for services/aicarmine_broker/application/public_payload/lab/__init__.py _iter_dicts."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from services.aicarmine_broker.application.public_payload.lab import _iter_dicts


class TestIterDicts:
    """Tests for _iter_dicts generator."""

    def test_simple_dict(self):
        result = list(_iter_dicts({"key": "value"}))
        assert ("$", {"key": "value"}) in result

    def test_nested_dict(self):
        data = {"a": {"b": {"c": "deep"}}}
        result = list(_iter_dicts(data))
        paths = [r[0] for r in result]
        assert "$" in paths
        assert "$.a" in paths
        assert "$.a.b" in paths

    def test_list_iteration(self):
        """Lists are traversed but only dicts are yielded."""
        data = {"items": [{"first": 1}, {"second": 2}]}
        result = list(_iter_dicts(data))
        paths = [r[0] for r in result]
        assert "$" in paths
        # The dict items inside the list are yielded
        assert "$.items[0]" in paths
        assert "$.items[1]" in paths

    def test_mixed_structure(self):
        data = {
            "outer": {
                "inner": [
                    {"item": 1},
                    {"item": 2}
                ]
            }
        }
        result = list(_iter_dicts(data))
        paths = [r[0] for r in result]
        assert "$" in paths
        assert "$.outer" in paths
        assert "$.outer.inner[0]" in paths
        assert "$.outer.inner[1]" in paths

    def test_default_max_depth(self):
        """Test with default max_depth=8."""
        data = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": "deep"}}}}}}}}}
        result = list(_iter_dicts(data))
        # Should stop at max_depth
        assert len(result) <= 9  # $ + 8 levels

    def test_custom_max_depth(self):
        """Test with custom max_depth=2."""
        data = {"a": {"b": {"c": "deep"}}}
        result = list(_iter_dicts(data, max_depth=2))
        paths = [r[0] for r in result]
        assert "$" in paths
        assert "$.a" in paths
        assert "$.a.b" in paths
        # $.a.b.c should be included since depth goes to 2

    def test_empty_dict(self):
        result = list(_iter_dicts({}))
        assert ("$", {}) in result

    def test_empty_list(self):
        """Empty list yields nothing (only dicts are yielded)."""
        result = list(_iter_dicts([]))
        assert result == []

    def test_string_value_not_traversed(self):
        """Strings should not be traversed as dicts."""
        data = {"key": "value"}
        result = list(_iter_dicts(data))
        # Only the dict itself, not the string value
        assert len(result) == 1

    def test_path_format(self):
        """Verify path format is correct."""
        data = {"a": {"b": {"c": "deep"}}}
        result = list(_iter_dicts(data))
        result_dict = dict(result)
        assert result_dict["$"] == {"a": {"b": {"c": "deep"}}}
        assert result_dict["$.a"] == {"b": {"c": "deep"}}
        # $.a.b is a dict, so it's yielded
        assert result_dict["$.a.b"] == {"c": "deep"}
