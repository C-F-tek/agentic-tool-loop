"""Test tool_contract prompt module."""

import pytest


class TestAvailableToolsForUserPayload:
    """Test available_tools_for_user_payload payload building."""

    def test_non_native_returns_compact_tools(self) -> None:
        from aicarmine_broker.application.prompt.tool_contract import (
            available_tools_for_user_payload,
        )
        tools = [{"name": "repo_read"}, {"name": "repo_search"}]
        result = available_tools_for_user_payload(tools, native_tools=False)
        assert result is tools

    def test_native_returns_index_dict(self) -> None:
        from aicarmine_broker.application.prompt.tool_contract import (
            available_tools_for_user_payload,
        )
        tools = [
            {"name": "repo_read", "description": "read file"},
            {"name": "repo_write_file", "description": "write file"},
        ]
        result = available_tools_for_user_payload(tools, native_tools=True)
        assert isinstance(result, dict)
        assert result["schema"] == "planner_available_tools_index.v1"
        assert result["transport"] == "message.tool_calls"
        assert result["tool_count"] == 2
        assert result["tool_names"] == ["repo_read", "repo_write_file"]

    def test_native_empty_tools(self) -> None:
        from aicarmine_broker.application.prompt.tool_contract import (
            available_tools_for_user_payload,
        )
        result = available_tools_for_user_payload([], native_tools=True)
        assert isinstance(result, dict)
        assert result["tool_count"] == 0
        assert result["tool_names"] == []


class TestFilterToolManifestForNames:
    """Test filter_tool_manifest_for_names filtering."""

    def test_empty_manifest_returns_empty(self) -> None:
        from aicarmine_broker.application.prompt.tool_contract import (
            filter_tool_manifest_for_names,
        )
        result = filter_tool_manifest_for_names([], [])
        assert result == []

    def test_matching_names_filtered(self) -> None:
        from aicarmine_broker.application.prompt.tool_contract import (
            filter_tool_manifest_for_names,
        )
        manifest = [
            {"name": "repo_read", "description": "read file"},
            {"name": "repo_search", "description": "search files"},
            {"name": "repo_write_file", "description": "write file"},
        ]
        result = filter_tool_manifest_for_names(manifest, ["repo_read", "repo_write_file"])
        assert len(result) == 2
        names = {row["name"] for row in result}
        assert names == {"repo_read", "repo_write_file"}

    def test_no_matches_returns_empty(self) -> None:
        from aicarmine_broker.application.prompt.tool_contract import (
            filter_tool_manifest_for_names,
        )
        manifest = [
            {"name": "repo_read"},
            {"name": "repo_search"},
        ]
        result = filter_tool_manifest_for_names(manifest, ["unknown_tool"])
        assert result == []


class TestNativeToolsSchemaForPlanner:
    """Test native_tools_schema_for_planner schema building."""

    def test_native_true_returns_enabled(self) -> None:
        from aicarmine_broker.application.prompt.tool_contract import (
            native_tools_schema_for_planner,
        )
        result = native_tools_schema_for_planner(native_tools=True)
        assert result["schema"] == "planner_native_tools_schema.v1"
        assert result["transport"] == "native_tool_calls"
        assert result["enabled"] is True

    def test_native_false_returns_disabled(self) -> None:
        from aicarmine_broker.application.prompt.tool_contract import (
            native_tools_schema_for_planner,
        )
        result = native_tools_schema_for_planner(native_tools=False)
        assert result["schema"] == "planner_native_tools_schema.v1"
        assert result["transport"] == "legacy_json_content"
        assert result["enabled"] is False


class TestToolShapeExamplesForPrompt:
    """Test tool_shape_examples_for_prompt examples building."""

    def test_native_true_returns_examples(self) -> None:
        from aicarmine_broker.application.prompt.tool_contract import (
            tool_shape_examples_for_prompt,
        )
        result = tool_shape_examples_for_prompt(
            native_tools=True,
            code_product_build_state_kind="build_state",
        )
        assert isinstance(result, dict)
        assert result["schema"] == "planner_tool_shape_examples.v1"
        assert result["transport"] == "native_tool_calls"
        assert result["examples_are_not_runnable"] is True
        assert result["must_not_copy_example_values"] is True
        assert isinstance(result.get("examples"), list)

    def test_native_false_returns_json_examples(self) -> None:
        from aicarmine_broker.application.prompt.tool_contract import (
            tool_shape_examples_for_prompt,
        )
        result = tool_shape_examples_for_prompt(
            native_tools=False,
            code_product_build_state_kind="build_state",
        )
        assert isinstance(result, dict)
        assert result["schema"] == "planner_tool_shape_examples.v1"


class TestRealToolValueSources:
    """Test REAL_TOOL_VALUE_SOURCES constant."""

    def test_sources_list_exists(self) -> None:
        from aicarmine_broker.application.prompt.tool_contract import (
            REAL_TOOL_VALUE_SOURCES,
        )
        assert isinstance(REAL_TOOL_VALUE_SOURCES, list)
        assert "candidate_next_actions" in REAL_TOOL_VALUE_SOURCES
        assert "verified_content_reads" in REAL_TOOL_VALUE_SOURCES

    def test_sources_has_required_entries(self) -> None:
        from aicarmine_broker.application.prompt.tool_contract import (
            REAL_TOOL_VALUE_SOURCES,
        )
