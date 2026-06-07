# Tool handling functions from planner.py
# This file was extracted from aicarmine_broker.planner

import json
from typing import Any, List, Dict

def _ordered_tool_names(names: set[str]) -> list[str]:
    # Implementation from original planner.py
    pass

def _apply_turn_surface_policy(contract: dict[str, Any]) -> dict[str, Any]:
    # Implementation from original planner.py
    pass

def _tool_surface_names_for_turn(
    tool_names: list[str],
    surface_policy: dict[str, Any]
) -> list[str]:
    # Implementation from original planner.py
    pass

def _available_tools_for_user_payload(compact_tools: list[dict[str, Any]]) -> Any:
    # Implementation from original planner.py
    pass

def _available_tools_window_pack(
    tools: list[dict[str, Any]], 
    max_chars: int = 1000
) -> list[dict[str, Any]]:
    # Implementation from original planner.py
    pass

def _tool_shape_examples_for_prompt() -> dict[str, Any]:
    # Implementation from original planner.py
    pass

