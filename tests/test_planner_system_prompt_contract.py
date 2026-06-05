from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.planner.system_prompt import (  # noqa: E402
    PLANNER_SYSTEM,
    planner_system_for_current_mode,
)


def test_planner_system_prompt_non_native_returns_base_contract() -> None:
    assert planner_system_for_current_mode(native_tools=False) == PLANNER_SYSTEM


def test_planner_system_prompt_native_rewrites_tool_call_contract() -> None:
    prompt = planner_system_for_current_mode(native_tools=True)

    assert "message.tool_calls" in prompt
    assert "L'azione tool nel content non e' consentita in native tool mode." in prompt
    assert "repo_propose_code_edit" in prompt

