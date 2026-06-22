"""Test suite for services/.venv module import verification.

Tests that all 36 core modules import successfully in the services/.venv environment.
"""

import sys
import pytest


# List of all modules to test
CORE_BROKER_MODULES = [
    "aicarmine_broker.contracts",
    "aicarmine_broker.config.models",
    "aicarmine_broker.config.compatibility",
    "aicarmine_broker.planner",
    "aicarmine_broker.planner_loop",
    "aicarmine_broker.planner_core.cache",
    "aicarmine_broker.planner_core.rag_cache_manager",
    "aicarmine_broker.job_html",
    "aicarmine_broker.application.shared.validation_utils",
    "aicarmine_broker.application.shared.evidence_builder",
    "aicarmine_broker.application.evidence.builder",
    "aicarmine_broker.application.evidence.final_quality",
    "aicarmine_broker.application.evidence.entry_point_analyzer",
    "aicarmine_broker.application.planner.lane_authority",
    "aicarmine_broker.application.planner.judge_lane",
    "aicarmine_broker.application.planner.evidence_contract_manager",
    "aicarmine_broker.application.planner.validator_utils",
    "aicarmine_broker.application.planner.contract_validator",
    "aicarmine_broker.application.planner.final_quality_validator",
    "aicarmine_broker.application.planner.route_validator",
    "aicarmine_broker.application.planner.validator",
    "aicarmine_broker.application.planner.validator.contract_utils",
    "aicarmine_broker.application.planner.validator.final_quality_route",
    "aicarmine_broker.application.planner.validator.validate_decision",
    "aicarmine_broker.application.planner.decision",
    "aicarmine_broker.application.planner.turn",
    "aicarmine_broker.application.planner.guard_evaluator",
    "aicarmine_broker.application.planner.loop",
    "aicarmine_broker.application.planner.loop_controller",
    "aicarmine_broker.application.controller.orientation_lane",
    "aicarmine_broker.application.controller.rag_preseed",
]

CODEX_BRIDGE_MODULES = [
    "codex_bridge.repo_validate_mcp_server",
    "codex_bridge.repo_search_det_mcp_server",
    "codex_bridge.repo_code_mcp_server",
    "codex_bridge.repo_probe_profiles",
]

VULKAN_BRIDGE_MODULES = [
    "vulkan_bridge.config",
]


ALL_MODULES = CORE_BROKER_MODULES + CODEX_BRIDGE_MODULES + VULKAN_BRIDGE_MODULES


class TestServicesImports:
    """Test that all services modules import successfully."""

    @pytest.mark.parametrize("module_name", ALL_MODULES, ids=lambda x: x.split(".")[-1])
    def test_import(self, module_name: str) -> None:
        """Test that a module can be imported without errors."""
        try:
            __import__(module_name)
        except Exception as e:
            pytest.fail(f"Failed to import {module_name}: {e}")

    def test_total_module_count(self) -> None:
        """Verify we have exactly 36 modules to test."""
        assert len(ALL_MODULES) == 36, f"Expected 36 modules, got {len(ALL_MODULES)}"

    def test_core_broker_count(self) -> None:
        """Verify we have 31 core broker modules."""
        assert len(CORE_BROKER_MODULES) == 31, f"Expected 31 core modules, got {len(CORE_BROKER_MODULES)}"

    def test_codex_bridge_count(self) -> None:
        """Verify we have 4 codex bridge modules."""
        assert len(CODEX_BRIDGE_MODULES) == 4, f"Expected 4 codex modules, got {len(CODEX_BRIDGE_MODULES)}"

    def test_vulkan_bridge_count(self) -> None:
        """Verify we have 1 vulkan bridge module."""
        assert len(VULKAN_BRIDGE_MODULES) == 1, f"Expected 1 vulkan module, got {len(VULKAN_BRIDGE_MODULES)}"


class TestSpecificMissingSymbols:
    """Test that specific missing symbols were added correctly."""

    def test_code_product_build_state_kind(self) -> None:
        """Test CODE_PRODUCT_BUILD_STATE_KIND is exported from aicarmine_broker.config."""
        from aicarmine_broker.config import CODE_PRODUCT_BUILD_STATE_KIND
        assert CODE_PRODUCT_BUILD_STATE_KIND == "code_product"

    def test_goal_requires_code_product_report(self) -> None:
        """Test goal_requires_code_product_report is exported from goal_classifier."""
        from aicarmine_broker.application.evidence.goal_classifier import goal_requires_code_product_report
        assert goal_requires_code_product_report("code_product report") is True
        assert goal_requires_code_product_report("simple task") is False

    def test_planner_scratchpad_window_signature(self) -> None:
        """Test planner_scratchpad_window_signature is exported from history_messages."""
        from aicarmine_broker.application.prompt.history_messages import planner_scratchpad_window_signature
        result = planner_scratchpad_window_signature([])
        assert result["schema"] == "planner_scratchpad_window_signature.v1"
        assert result["count"] == 0

    def test_repo_read_window_signature(self) -> None:
        """Test repo_read_window_signature is exported from history_messages."""
        from aicarmine_broker.application.prompt.history_messages import repo_read_window_signature
        result = repo_read_window_signature([])
        assert result["schema"] == "repo_read_window_signature.v1"
        assert result["count"] == 0

    def test_invalid_code_product_decision_signature_count(self) -> None:
        """Test invalid_code_product_decision_signature_count is exported from code_product.history."""
        from aicarmine_broker.application.code_product.history import invalid_code_product_decision_signature_count
        result = invalid_code_product_decision_signature_count([])
        assert result == 0

    def test_invalid_decision_signature_key(self) -> None:
        """Test invalid_decision_signature_key is exported from code_product.history."""
        from aicarmine_broker.application.code_product.history import invalid_decision_signature_key
        result = invalid_decision_signature_key([])
        assert result == "invalid_decision_signature_count:0"

    def test_repo_readable_evidence_file(self) -> None:
        """Test repo_readable_evidence_file is exported from required_working_set."""
        from aicarmine_broker.application.evidence.required_working_set import repo_readable_evidence_file
        result = repo_readable_evidence_file([], "test.py")
        assert result == {}