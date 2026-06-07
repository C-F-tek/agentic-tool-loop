# Prompt and context handling functions from planner.py
# This file was extracted from aicarmine_broker.planner

import json
from typing import Any, List, Dict

def _compact_prompt_context_window_item(item: dict[str, Any]) -> dict[str, Any]:
    # Implementation from original planner.py
    pass

def _tool_shape_examples_for_prompt() -> dict[str, Any]:
    # Implementation from original planner.py
    pass

def _compact_history_for_prompt(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Implementation from original planner.py
    pass

def _compact_evidence_contract_for_prompt(contract: dict[str, Any]) -> dict[str, Any]:
    # Implementation from original planner.py
    pass

def _windowed_evidence_contract_for_prompt(
    contract: dict[str, Any], 
    max_chars: int = 1000
) -> dict[str, Any]:
    # Implementation from original planner.py
    pass

def _prompt_section_window_pack(
    sections: list[dict[str, Any]], 
    max_chars: int = 1000
) -> list[dict[str, Any]]:
    # Implementation from original planner.py
    pass

def _hard_budget_evidence_contract_for_prompt(
    contract: dict[str, Any], 
    headroom_char_budget: int
) -> bool:
    # Implementation from original planner.py
    pass

def _preserve_required_next_tool_call_for_prompt(
    contract: dict[str, Any]
) -> dict[str, Any]:
    # Implementation from original planner.py
    pass

def _compact_intrinsic_context_for_prompt(context: dict[str, Any]) -> dict[str, Any]:
    # Implementation from original planner.py
    pass

def _windowed_optional_context_value(
    value: Any, 
    max_chars: int = 1000
) -> Any:
    # Implementation from original planner.py
    pass

