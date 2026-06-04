from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.tool_manifest_builder import (  # noqa: E402
    compact_tool_manifest_for_prompt,
    filter_tool_manifest_for_names,
    json_char_len,
    native_tools_schema_for_planner,
    tool_schema_name,
)


def test_compact_tool_manifest_keeps_contract_outside_native_schema() -> None:
    manifest = [{
        "name": "repo_read",
        "description": "x" * 1000,
        "parameters": {
            "required": ["path"],
            "properties": {"path": {"type": "string"}, "max_chars": {"type": "integer"}},
        },
        "argument_contract": {"path": "repo-relative"},
    }]

    compacted = compact_tool_manifest_for_prompt(manifest)

    assert compacted[0]["name"] == "repo_read"
    assert compacted[0]["required"] == ["path"]
    assert compacted[0]["properties"] == ["path", "max_chars"]
    assert compacted[0]["argument_contract"] == {"path": "repo-relative"}
    assert compacted[0]["description"].endswith("<prompt_preview_truncated>")


def test_native_tools_schema_is_slim_and_filtered() -> None:
    schema = [
        {
            "type": "function",
            "function": {
                "name": "repo_read",
                "description": "r" * 500,
                "parameters": {"type": "object"},
                "argument_contract": {"large": "policy"},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "repo_tree",
                "description": "tree",
                "parameters": {"type": "object"},
            },
        },
    ]

    native = native_tools_schema_for_planner(schema, {"repo_read"})

    assert len(native) == 1
    assert native[0]["function"]["name"] == "repo_read"
    assert "argument_contract" not in native[0]["function"]
    assert native[0]["function"]["description"].endswith("<prompt_preview_truncated>")
    assert tool_schema_name(native[0]) == "repo_read"


def test_filter_tool_manifest_for_names_and_json_len() -> None:
    manifest = [{"name": "a"}, {"name": "b"}]

    assert filter_tool_manifest_for_names(manifest, ["b"]) == [{"name": "b"}]
    assert json_char_len({"a": 1}) == len('{"a": 1}')
