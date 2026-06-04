"""Planner prompt contract helpers for tool surface descriptions."""
from __future__ import annotations

from typing import Any


REAL_TOOL_VALUE_SOURCES = [
    "candidate_next_actions",
    "required_working_set",
    "verified_content_reads",
    "explicit user exact old_text/new_text",
]


def available_tools_for_user_payload(
    compact_tools: list[dict[str, Any]],
    *,
    native_tools: bool,
) -> Any:
    if not native_tools:
        return compact_tools
    return [
        {
            "name": row.get("name"),
            "transport": "message.tool_calls",
            "schema_source": "ollama_request.tools",
        }
        for row in compact_tools
        if isinstance(row, dict) and row.get("name")
    ]


def tool_shape_examples_for_prompt(
    *,
    native_tools: bool,
    code_product_build_state_kind: str,
) -> dict[str, Any]:
    if native_tools:
        return {
            "schema": "planner_tool_shape_examples.v1",
            "transport": "native_tool_calls",
            "examples_are_not_runnable": True,
            "must_not_copy_example_values": True,
            "real_values_must_come_from": REAL_TOOL_VALUE_SOURCES,
            "content_json_tool_calls_allowed": False,
            "examples": [
                {
                    "shape": "repo_read_known_path_native_tool_call",
                    "transport": "message.tool_calls",
                    "function": {
                        "name": "repo_read",
                        "arguments": {"path": "EXAMPLE_ONLY/path.py", "max_chars": 8000},
                    },
                    "reason": "EXAMPLE_ONLY_DO_NOT_COPY: use a real repo-relative path from evidence.",
                },
                {
                    "shape": "sqlite_prompt_context_window_read_native_tool_call",
                    "transport": "message.tool_calls",
                    "function": {
                        "name": "planner_scratchpad_read",
                        "arguments": {
                            "kind": "prompt_context_window",
                            "document_id": "EXAMPLE_ONLY_DO_NOT_COPY_document_id",
                            "offset": 2500,
                            "max_chars": 2500,
                        },
                    },
                    "reason": "EXAMPLE_ONLY_DO_NOT_COPY: use document_id/offset/max_chars from required_working_set or candidate_next_actions.",
                },
                {
                    "shape": "code_product_build_state_write_native_tool_call",
                    "transport": "message.tool_calls",
                    "function": {
                        "name": "planner_scratchpad_write",
                        "arguments": {
                            "kind": code_product_build_state_kind,
                            "target_file": "EXAMPLE_ONLY/path.py",
                            "text": "{\"schema\":\"code_product_build_state.v1\",\"target_file\":\"EXAMPLE_ONLY/path.py\",\"status\":\"collecting_source\",\"source_windows\":[{\"document_id\":\"EXAMPLE_ONLY_DO_NOT_COPY_document_id\",\"offset\":0,\"complete\":false,\"sha256\":\"EXAMPLE_ONLY_DO_NOT_COPY_hash\"}],\"rationale\":\"EXAMPLE_ONLY_DO_NOT_COPY real progress only\"}",
                        },
                    },
                    "reason": "EXAMPLE_ONLY_DO_NOT_COPY: write only a complete JSON state with real progress, never an empty template.",
                },
                {
                    "shape": "repo_propose_from_verified_old_text_native_tool_call",
                    "transport": "message.tool_calls",
                    "function": {
                        "name": "repo_propose_code_edit",
                        "arguments": {
                            "target_file": "EXAMPLE_ONLY/path.py",
                            "edit_kind": "unified_diff",
                            "rationale": "EXAMPLE_ONLY_DO_NOT_COPY: exact replacement from verified repo_read.",
                            "old_text": "EXAMPLE_ONLY_DO_NOT_COPY_verified_old_text_from_repo_read",
                            "new_text": "EXAMPLE_ONLY_DO_NOT_COPY_new_text",
                        },
                    },
                    "reason": "EXAMPLE_ONLY_DO_NOT_COPY: old_text must be exact target content already verified by repo_read.",
                },
                {
                    "shape": "typed_block_when_diff_not_constructible",
                    "transport": "message.content_json",
                    "action": "block",
                    "reason": "EXAMPLE_ONLY_DO_NOT_COPY_TYPED_BLOCK",
                    "final_answer": "EXAMPLE_ONLY_DO_NOT_COPY: use typed block when no verified text/window remains to build the diff.",
                },
            ],
        }
    return {
        "schema": "planner_tool_shape_examples.v1",
        "transport": "legacy_json_content",
        "examples_are_not_runnable": True,
        "must_not_copy_example_values": True,
        "real_values_must_come_from": REAL_TOOL_VALUE_SOURCES,
        "examples": [
            {
                "shape": "repo_read_known_path",
                "action": "tool",
                "tool": "repo_read",
                "arguments": {"path": "EXAMPLE_ONLY/path.py", "max_chars": 8000},
                "reason": "EXAMPLE_ONLY_DO_NOT_COPY: use a real repo-relative path from evidence.",
            },
            {
                "shape": "sqlite_prompt_context_window_read",
                "action": "tool",
                "tool": "planner_scratchpad_read",
                "arguments": {
                    "kind": "prompt_context_window",
                    "document_id": "EXAMPLE_ONLY_DO_NOT_COPY_document_id",
                    "offset": 2500,
                    "max_chars": 2500,
                },
                "reason": "EXAMPLE_ONLY_DO_NOT_COPY: use document_id/offset/max_chars from required_working_set or candidate_next_actions.",
            },
            {
                "shape": "code_product_build_state_write",
                "action": "tool",
                "tool": "planner_scratchpad_write",
                "arguments": {
                    "kind": code_product_build_state_kind,
                    "target_file": "EXAMPLE_ONLY/path.py",
                    "text": "{\"schema\":\"code_product_build_state.v1\",\"target_file\":\"EXAMPLE_ONLY/path.py\",\"status\":\"collecting_source\",\"source_windows\":[{\"document_id\":\"EXAMPLE_ONLY_DO_NOT_COPY_document_id\",\"offset\":0,\"complete\":false,\"sha256\":\"EXAMPLE_ONLY_DO_NOT_COPY_hash\"}],\"rationale\":\"EXAMPLE_ONLY_DO_NOT_COPY real progress only\"}",
                },
                "reason": "EXAMPLE_ONLY_DO_NOT_COPY: write only a complete JSON state with real progress, never an empty template.",
            },
            {
                "shape": "repo_propose_from_verified_old_text",
                "action": "tool",
                "tool": "repo_propose_code_edit",
                "arguments": {
                    "target_file": "EXAMPLE_ONLY/path.py",
                    "edit_kind": "unified_diff",
                    "rationale": "EXAMPLE_ONLY_DO_NOT_COPY: exact replacement from verified repo_read.",
                    "old_text": "EXAMPLE_ONLY_DO_NOT_COPY_verified_old_text_from_repo_read",
                    "new_text": "EXAMPLE_ONLY_DO_NOT_COPY_new_text",
                },
                "reason": "EXAMPLE_ONLY_DO_NOT_COPY: old_text must be exact target content already verified by repo_read.",
            },
            {
                "shape": "typed_block_when_diff_not_constructible",
                "action": "block",
                "reason": "EXAMPLE_ONLY_DO_NOT_COPY_TYPED_BLOCK",
                "final_answer": "EXAMPLE_ONLY_DO_NOT_COPY: use typed block when no verified text/window remains to build the diff.",
            },
        ],
    }
