"""Test controller module exports and functions."""

import pytest


class TestControllerMemory:
    """Test controller.memory exports."""

    def test_controller_memory_target_key_exists(self) -> None:
        """Test controller_memory_target_key can be imported."""
        from aicarmine_broker.application.controller.memory import controller_memory_target_key
        assert callable(controller_memory_target_key)

    def test_controller_memory_target_key_returns_string(self) -> None:
        """Test controller_memory_target_key returns string."""
        from aicarmine_broker.application.controller.memory import controller_memory_target_key
        result = controller_memory_target_key("test_goal", {"target_file": "test.py"})
        assert isinstance(result, str)
        assert "controller_memory" in result

    def test_controller_memory_lesson_text_exists(self) -> None:
        """Test controller_memory_lesson_text can be imported."""
        from aicarmine_broker.application.controller.memory import controller_memory_lesson_text
        assert callable(controller_memory_lesson_text)

    def test_write_controller_memory_lesson_exists(self) -> None:
        """Test write_controller_memory_lesson can be imported."""
        from aicarmine_broker.application.controller.memory import write_controller_memory_lesson
        assert callable(write_controller_memory_lesson)

    def test_loop_turn_memory_text_exists(self) -> None:
        """Test loop_turn_memory_text can be imported."""
        from aicarmine_broker.application.controller.memory import loop_turn_memory_text
        assert callable(loop_turn_memory_text)

    def test_write_loop_turn_memory_exists(self) -> None:
        """Test write_loop_turn_memory can be imported."""
        from aicarmine_broker.application.controller.memory import write_loop_turn_memory
        assert callable(write_loop_turn_memory)


class TestControllerPreseed:
    """Test controller.preseed exports."""

    def test_controller_preseed_plan_exists(self) -> None:
        """Test controller_preseed_plan can be imported."""
        from aicarmine_broker.application.controller.preseed import controller_preseed_plan
        assert callable(controller_preseed_plan)

    def test_controller_preseed_plan_returns_dict(self) -> None:
        """Test controller_preseed_plan returns dict."""
        from aicarmine_broker.application.controller.preseed import controller_preseed_plan
        result = controller_preseed_plan("test goal", {"target_kind": "file"})
        assert isinstance(result, dict)
        assert result.get("schema") == "controller_preseed_plan.v1"

    def test_controller_preplanner_rag_preseed_plan_exists(self) -> None:
        """Test controller_preplanner_rag_preseed_plan can be imported."""
        from aicarmine_broker.application.controller.preseed import controller_preplanner_rag_preseed_plan
        assert callable(controller_preplanner_rag_preseed_plan)

    def test_controller_preplanner_rag_query_plan_exists(self) -> None:
        """Test controller_preplanner_rag_query_plan can be imported."""
        from aicarmine_broker.application.controller.preseed import controller_preplanner_rag_query_plan
        assert callable(controller_preplanner_rag_query_plan)

    def test_root_surface_entries_exists(self) -> None:
        """Test root_surface_entries can be imported."""
        from aicarmine_broker.application.controller.preseed import root_surface_entries
        assert callable(root_surface_entries)
