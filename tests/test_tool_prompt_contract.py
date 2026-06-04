from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.prompt.tool_contract import (  # noqa: E402
    REAL_TOOL_VALUE_SOURCES,
    available_tools_for_user_payload,
    tool_shape_examples_for_prompt,
)


def test_available_tools_for_user_payload_preserves_legacy_manifest() -> None:
    compact_tools = [{"name": "repo_read", "description": "Read a file"}]

    payload = available_tools_for_user_payload(compact_tools, native_tools=False)

    assert payload is compact_tools


def test_available_tools_for_user_payload_native_declares_provider_schema() -> None:
    compact_tools = [
        {"name": "repo_read", "description": "Read a file"},
        {"description": "missing name"},
        "not a dict",  # type: ignore[list-item]
    ]

    payload = available_tools_for_user_payload(compact_tools, native_tools=True)

    assert payload == [{
        "name": "repo_read",
        "transport": "message.tool_calls",
        "schema_source": "ollama_request.tools",
    }]


def test_tool_shape_examples_native_contract() -> None:
    payload = tool_shape_examples_for_prompt(
        native_tools=True,
        code_product_build_state_kind="code_product_build_state",
    )

    assert payload["schema"] == "planner_tool_shape_examples.v1"
    assert payload["transport"] == "native_tool_calls"
    assert payload["content_json_tool_calls_allowed"] is False
    assert payload["real_values_must_come_from"] == REAL_TOOL_VALUE_SOURCES
    build_state = next(
        item for item in payload["examples"]
        if item["shape"] == "code_product_build_state_write_native_tool_call"
    )
    assert build_state["function"]["name"] == "planner_scratchpad_write"
    assert build_state["function"]["arguments"]["kind"] == "code_product_build_state"


def test_tool_shape_examples_legacy_contract() -> None:
    payload = tool_shape_examples_for_prompt(
        native_tools=False,
        code_product_build_state_kind="code_product_build_state",
    )

    assert payload["schema"] == "planner_tool_shape_examples.v1"
    assert payload["transport"] == "legacy_json_content"
    assert payload["real_values_must_come_from"] == REAL_TOOL_VALUE_SOURCES
    build_state = next(
        item for item in payload["examples"]
        if item["shape"] == "code_product_build_state_write"
    )
    assert build_state["action"] == "tool"
    assert build_state["tool"] == "planner_scratchpad_write"
    assert build_state["arguments"]["kind"] == "code_product_build_state"
