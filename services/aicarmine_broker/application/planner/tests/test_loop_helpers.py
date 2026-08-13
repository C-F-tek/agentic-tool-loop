"""Tests for planner/loop.py helper functions."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent directory for imports
test_path = str(Path(__file__).parents[4])
if test_path not in sys.path:
    sys.path.insert(0, test_path)

from services.aicarmine_broker.application.planner.loop import (
    _dict_field,
    _list_field,
)


class TestDictField:
    """Tests for _dict_field helper."""

    def test_returns_dict_for_dict_value(self):
        """Test that _dict_field returns a copy of dict values."""
        mapping = {"key": {"a": 1, "b": 2}}
        result = _dict_field(mapping, "key")
        assert result == {"a": 1, "b": 2}
        assert result is not mapping["key"]

    def test_returns_empty_dict_for_non_dict_value(self):
        """Test that _dict_field returns {} for non-dict values."""
        mapping = {"key": "not a dict"}
        result = _dict_field(mapping, "key")
        assert result == {}

    def test_returns_empty_dict_for_missing_key(self):
        """Test that _dict_field returns {} for missing keys."""
        mapping = {"other": "value"}
        result = _dict_field(mapping, "missing")
        assert result == {}

    def test_returns_empty_dict_for_none(self):
        """Test that _dict_field returns {} for None values."""
        mapping = {"key": None}
        result = _dict_field(mapping, "key")
        assert result == {}

    def test_returns_empty_dict_for_list(self):
        """Test that _dict_field returns {} for list values."""
        mapping = {"key": [1, 2, 3]}
        result = _dict_field(mapping, "key")
        assert result == {}

    def test_preserves_nested_structure(self):
        """Test that nested dict structures are preserved."""
        inner = {"nested": {"deep": True}}
        mapping = {"key": inner}
        result = _dict_field(mapping, "key")
        assert result["nested"]["deep"] is True


class TestListField:
    """Tests for _list_field helper."""

    def test_returns_list_for_list_value(self):
        """Test that _list_field returns a copy of list values."""
        mapping = {"key": [1, 2, 3]}
        result = _list_field(mapping, "key")
        assert result == [1, 2, 3]
        assert result is not mapping["key"]

    def test_returns_empty_list_for_non_list_value(self):
        """Test that _list_field returns [] for non-list values."""
        mapping = {"key": "not a list"}
        result = _list_field(mapping, "key")
        assert result == []

    def test_returns_empty_list_for_missing_key(self):
        """Test that _list_field returns [] for missing keys."""
        mapping = {"other": "value"}
        result = _list_field(mapping, "missing")
        assert result == []

    def test_returns_empty_list_for_none(self):
        """Test that _list_field returns [] for None values."""
        mapping = {"key": None}
        result = _list_field(mapping, "key")
        assert result == []

    def test_returns_empty_list_for_dict(self):
        """Test that _list_field returns [] for dict values."""
        mapping = {"key": {"a": 1}}
        result = _list_field(mapping, "key")
        assert result == []

    def test_preserves_list_order(self):
        """Test that list order is preserved."""
        mapping = {"key": ["z", "a", "m"]}
        result = _list_field(mapping, "key")
        assert result == ["z", "a", "m"]

    def test_handles_empty_list(self):
        """Test that empty lists are handled correctly."""
        mapping = {"key": []}
        result = _list_field(mapping, "key")
        assert result == []
        assert result is not mapping["key"]