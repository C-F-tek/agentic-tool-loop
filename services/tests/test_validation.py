"""Tests for validation logic in aicarmine_broker."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aicarmine_broker.tool_contract import normalize_tool_name


class TestToolContract:
    """Test tool contract normalization."""

    def test_normalize_tool_name_basic(self):
        """Test that tool names are normalized consistently."""
        assert normalize_tool_name("repo_read") == "repo_read"
        assert normalize_tool_name("Repo_Read") == "repo_read"
        assert normalize_tool_name("REPO_READ") == "repo_read"

    def test_normalize_tool_name_with_underscores(self):
        """Test normalization preserves underscores."""
        assert normalize_tool_name("planner_scratchpad_write") == "planner_scratchpad_write"


class TestErrorHandling:
    """Test error handling module."""

    def test_error_categories(self):
        """Test that error categories are defined."""
        from aicarmine_broker.error_handling import ErrorCategory
        # Check that common categories exist
        categories = [c for c in ErrorCategory]
        assert len(categories) > 0

    def test_error_severity_levels(self):
        """Test that error severity levels are defined."""
        from aicarmine_broker.error_handling import ErrorSeverity
        levels = [s for s in ErrorSeverity]
        assert len(levels) > 0


class TestConfigModels:
    """Test configuration models."""

    def test_env_loader_import(self):
        """Test that env_loader can be imported."""
        from aicarmine_broker.config import env_loader
        assert hasattr(env_loader, '__file__')

    def test_models_import(self):
        """Test that config models can be imported."""
        from aicarmine_broker.config.models import (
            AGENT_JOB_DB,
            AGENT_JOB_ROOT,
            PLANNER_MODEL,
            PLANNER_URL,
        )
        # These should be set from environment or defaults
        assert AGENT_JOB_DB is not None
        assert PLANNER_MODEL is not None