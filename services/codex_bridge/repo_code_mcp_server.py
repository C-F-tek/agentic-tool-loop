#!/usr/bin/env python3
"""Incubating MCP adapter for repo code-product tools."""

from __future__ import annotations

from collections.abc import Callable
import json
import sys
from pathlib import Path
from typing import Any

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    self_test,
    serve,
)

SERVER_NAME = "aicarmine-repo-code-mcp"
SERVER_VERSION = "0.1.0-incubator"


def string_prop(default: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    return schema


def integer_prop(default: int, minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum, "maximum": maximum}


def _report_only(
    tool_name: str,
    handler: Callable[[dict[str, Any], Path], dict[str, Any]],
) -> Callable[[dict[str, Any], Path], dict[str, Any]]:
    def wrapped(args: dict[str, Any], root: Path) -> dict[str, Any]:
        result = handler(args, root)
        if not isinstance(result, dict):
            return {
                "ok": False,
                "tool": tool_name,
                "error": "invalid_tool_result",
                "result_type": type(result).__name__,
            }
        result.setdefault("source_writes_performed", False)
        result.setdefault("patch_application_performed", False)
        result["mcp_server"] = SERVER_NAME
        result["incubation_status"] = "isolated_candidate"
        if result.get("source_writes_performed") or result.get("patch_application_performed"):
            return {
                "ok": False,
                "tool": tool_name,
                "error": "report_only_contract_violation",
                "mcp_server": SERVER_NAME,
                "upstream": result,
            }
        return result

    return wrapped


def _guarded_source_write(
    tool_name: str,
    handler: Callable[[dict[str, Any], Path], dict[str, Any]],
) -> Callable[[dict[str, Any], Path], dict[str, Any]]:
    def wrapped(args: dict[str, Any], root: Path) -> dict[str, Any]:
        if args.get("allow_source_write") is not True:
            return {
                "ok": False,
                "tool": tool_name,
                "error": "source_write_not_enabled",
                "required_arg": "allow_source_write=true",
                "mcp_server": SERVER_NAME,
                "source_writes_performed": False,
                "patch_application_performed": False,
            }
        result = handler(args, root)
        if not isinstance(result, dict):
            return {
                "ok": False,
                "tool": tool_name,
                "error": "invalid_tool_result",
                "result_type": type(result).__name__,
                "mcp_server": SERVER_NAME,
                "source_writes_performed": False,
                "patch_application_performed": False,
            }
        changed = bool(result.get("ok") and result.get("changed"))
        result["mcp_server"] = SERVER_NAME
        result["incubation_status"] = "isolated_candidate"
        result["write_scope"] = "exact_old_text_new_text_only"
        result["source_writes_performed"] = changed
        result["patch_application_performed"] = changed
        return result

    return wrapped


def _tools() -> dict[str, ToolSpec]:
    from aicarmine_broker.tools.repo_code_product import repo_propose_code_edit
    from aicarmine_broker.tools.repo_deterministic import (
        repo_git_apply_check,
        repo_unidiff_validate,
    )
    from aicarmine_broker.tools.repo_patch import repo_apply_patch

    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        payload = health_payload(SERVER_NAME, list(tools))
        payload["incubation_status"] = "isolated_candidate"
        payload["promotion_rule"] = (
            "Promote tools into semantic MCP servers only after repeated clean "
            "self-tests and no source-write contract violations."
        )
        return payload

    tools["aicarmine_repo_code_health"] = ToolSpec(
        name="aicarmine_repo_code_health",
        description="Report repo-code incubator MCP health and no-loop guarantees.",
        input_schema=object_schema(),
        handler=health,
    )
    tools["aicarmine_repo_code_propose_edit"] = ToolSpec(
        name="aicarmine_repo_code_propose_edit",
        description="Build a report-only code edit proposal. Does not apply patches or write source files.",
        input_schema=object_schema(
            {
                "target_file": string_prop(),
                "path": string_prop(),
                "edit_kind": string_prop(),
                "rationale": string_prop(),
                "reason": string_prop(),
                "unified_diff": string_prop(),
                "old_text": string_prop(),
                "new_text": string_prop(),
                "structured_operations": {"type": "array", "items": {"type": "object"}},
                "operations": {"type": "array", "items": {"type": "object"}},
                "validation_commands": {"type": "array", "items": {"type": "string"}},
                "require_unidiff": {"type": "boolean", "default": True},
                "ast_anchor": string_prop(),
                "ast_grep_rule": string_prop(),
                "tree_sitter_language": string_prop(),
            }
        ),
        handler=_report_only("repo_propose_code_edit", repo_propose_code_edit),
        required_one_of=[["target_file"], ["path"]],
    )
    tools["aicarmine_repo_code_unidiff_validate"] = ToolSpec(
        name="aicarmine_repo_code_unidiff_validate",
        description="Validate unified diff structure without applying it.",
        input_schema=object_schema(
            {
                "unified_diff": string_prop(),
                "diff": string_prop(),
            }
        ),
        handler=_report_only("repo_unidiff_validate", repo_unidiff_validate),
        required_one_of=[["unified_diff"], ["diff"]],
    )
    tools["aicarmine_repo_code_git_apply_check"] = ToolSpec(
        name="aicarmine_repo_code_git_apply_check",
        description="Run git apply --check on a unified diff without applying it.",
        input_schema=object_schema(
            {
                "unified_diff": string_prop(),
                "diff": string_prop(),
                "patch": string_prop(),
                "timeout_seconds": integer_prop(120, 1, 600),
            }
        ),
        handler=_report_only("repo_git_apply_check", repo_git_apply_check),
        required_one_of=[["unified_diff"], ["diff"], ["patch"]],
    )
    tools["aicarmine_repo_code_apply_patch"] = ToolSpec(
        name="aicarmine_repo_code_apply_patch",
        description=(
            "Apply an exact old_text/new_text source patch in the incubator MCP. "
            "Requires allow_source_write=true and does not execute commands."
        ),
        input_schema=object_schema(
            {
                "path": string_prop(),
                "old_text": string_prop(),
                "new_text": string_prop(),
                "max_replacements": integer_prop(1, 1, 100),
                "allow_source_write": {"type": "boolean", "default": False},
            },
            required=["path", "old_text", "new_text", "allow_source_write"],
        ),
        handler=_guarded_source_write("repo_apply_patch", repo_apply_patch),
    )
    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    if "--self-test" in argv:
        result = self_test(
            server_name=SERVER_NAME,
            server_version=SERVER_VERSION,
            tools=tools,
            health_tool="aicarmine_repo_code_health",
            real_tool="aicarmine_repo_code_unidiff_validate",
            real_args={
                "unified_diff": (
                    "--- a/example.txt\n"
                    "+++ b/example.txt\n"
                    "@@ -1 +1 @@\n"
                    "-old\n"
                    "+new\n"
                )
            },
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())
