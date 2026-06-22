"""Test planner module exports and functions."""

import pytest


class TestPlannerDecision:
    """Test planner.decision exports."""

    def test_import_planner_decision(self) -> None:
        """Test planner.decision can be imported."""
        from aicarmine_broker.application.planner.decision import (
            controller_preplanner_rag_preseed_plan,
            controller_preplanner_rag_query_plan,
            controller_preseed_plan,
        )
        assert callable(controller_preplanner_rag_preseed_plan)
        assert callable(controller_preplanner_rag_query_plan)
        assert callable(controller_preseed_plan)


class TestPlannerHistoryMessages:
    """Test prompt.history_messages exports."""

    def test_planner_scratchpad_window_signature(self) -> None:
        """Test planner_scratchpad_window_signature returns dict."""
        from aicarmine_broker.application.prompt.history_messages import planner_scratchpad_window_signature
        result = planner_scratchpad_window_signature([])
        assert isinstance(result, dict)
        assert result.get("schema") == "planner_scratchpad_window_signature.v1"
        assert result.get("count") == 0

    def test_repo_read_window_signature(self) -> None:
        """Test repo_read_window_signature returns dict."""
        from aicarmine_broker.application.prompt.history_messages import repo_read_window_signature
        result = repo_read_window_signature([])
        assert isinstance(result, dict)
        assert result.get("schema") == "repo_read_window_signature.v1"
        assert result.get("count") == 0


class TestPlannerToolContract:
    """Test prompt.tool_contract exports."""

    def test_filter_tool_manifest_for_names(self) -> None:
        """Test filter_tool_manifest_for_names filters correctly."""
        from aicarmine_broker.application.prompt.tool_contract import filter_tool_manifest_for_names
        manifest = [
            {"name": "repo_read", "description": "read"},
            {"name": "repo_search", "description": "search"},
        ]
        result = filter_tool_manifest_for_names(manifest, ["repo_read"])
        assert len(result) == 1
        assert result[0]["name"] == "repo_read"

    def test_native_tools_schema_for_planner(self) -> None:
        """Test native_tools_schema_for_planner returns correct schema."""
        from aicarmine_broker.application.prompt.tool_contract import native_tools_schema_for_planner
        result_enabled = native_tools_schema_for_planner(native_tools=True)
        result_disabled = native_tools_schema_for_planner(native_tools=False)
        assert result_enabled.get("enabled") is True
        assert result_disabled.get("enabled") is False


class TestPlannerCodeProductHistory:
    """Test code_product.history exports."""

    def test_invalid_code_product_decision_signature_count_empty(self) -> None:
        """Test invalid_code_product_decision_signature_count with empty history."""
        from aicarmine_broker.application.code_product.history import invalid_code_product_decision_signature_count
        result = invalid_code_product_decision_signature_count([])
        assert result == 0

    def test_invalid_decision_signature_key_empty(self) -> None:
        """Test invalid_decision_signature_key with empty history."""
        from aicarmine_broker.application.code_product.history import invalid_decision_signature_key
        result = invalid_decision_signature_key([])
        assert result == "invalid_decision_signature_count:0"


class TestInfrastructureOllamaPlannerClient:
    """Test infrastructure.ollama_planner_client exports."""

    def test_post_json_exists(self) -> None:
        """Test post_json function exists."""
        from aicarmine_broker.infrastructure.ollama_planner_client import post_json
        assert callable(post_json)

    def test_post_json_signature(self) -> None:
        """Test post_json has correct signature."""
        from aicarmine_broker.infrastructure.ollama_planner_client import post_json
        import inspect
        sig = inspect.signature(post_json)
        params = list(sig.parameters.keys())
        assert "url" in params
        assert "payload" in params
        assert "timeout_seconds" in params