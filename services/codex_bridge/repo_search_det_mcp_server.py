#!/usr/bin/env python3
"""MCP adapter for deterministic local repo search tools."""

from __future__ import annotations

import json
import sys
from typing import Any

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    self_test,
    serve,
)

SERVER_NAME = "aicarmine-repo-search-det-mcp"
SERVER_VERSION = "1.0.0"


def string_prop(default: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    return schema


def integer_prop(default: int, minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum, "maximum": maximum}


def _tools() -> dict[str, ToolSpec]:
    from aicarmine_broker.tools.repo_deterministic import (
        repo_ast_grep_dry_run,
        repo_ast_grep_search,
        repo_ctags_symbols,
        repo_fd_files,
        repo_jq_query,
        repo_rg_search,
        repo_tree_sitter_parse,
    )

    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root):
        return health_payload(SERVER_NAME, list(tools))

    tools["aicarmine_repo_search_det_health"] = ToolSpec(
        name="aicarmine_repo_search_det_health",
        description="Report Python executable, cwd, repo root, branch, commit, and no-loop guarantees.",
        input_schema=object_schema(),
        handler=health,
    )
    tools["aicarmine_repo_search_fd"] = ToolSpec(
        name="aicarmine_repo_search_fd",
        description="Find files with fd inside the configured repo root.",
        input_schema=object_schema(
            {
                "pattern": string_prop(),
                "query": string_prop(),
                "path": string_prop("."),
                "extension": string_prop(),
                "suffix": string_prop(),
                "limit": integer_prop(200, 1, 5000),
                "max_results": integer_prop(200, 1, 5000),
                "timeout_seconds": integer_prop(60, 1, 600),
            }
        ),
        handler=repo_fd_files,
    )
    tools["aicarmine_repo_search_rg"] = ToolSpec(
        name="aicarmine_repo_search_rg",
        description="Search file contents with ripgrep JSON output inside the configured repo root.",
        input_schema=object_schema(
            {
                "pattern": string_prop(),
                "query": string_prop(),
                "path": string_prop("."),
                "max_results": integer_prop(80, 1, 1000),
                "limit": integer_prop(80, 1, 1000),
                "context": integer_prop(0, 0, 5),
                "timeout_seconds": integer_prop(120, 1, 600),
            },
            any_of=[["pattern"], ["query"]],
        ),
        handler=repo_rg_search,
    )
    tools["aicarmine_repo_search_jq"] = ToolSpec(
        name="aicarmine_repo_search_jq",
        description="Run jq against json_text or a repo JSON file.",
        input_schema=object_schema(
            {
                "query": string_prop(),
                "filter": string_prop(),
                "json_text": string_prop(),
                "path": string_prop(),
                "timeout_seconds": integer_prop(60, 1, 600),
            },
            any_of=[["query"], ["filter"]],
        ),
        handler=repo_jq_query,
    )
    tools["aicarmine_repo_search_ast_grep"] = ToolSpec(
        name="aicarmine_repo_search_ast_grep",
        description="Run ast-grep search inside the configured repo root.",
        input_schema=object_schema(
            {
                "pattern": string_prop(),
                "kind": string_prop(),
                "rewrite": string_prop(),
                "lang": string_prop("python"),
                "language": string_prop(),
                "path": string_prop("."),
                "timeout_seconds": integer_prop(120, 1, 600),
            },
            any_of=[["pattern"], ["kind"]],
        ),
        handler=repo_ast_grep_search,
    )
    tools["aicarmine_repo_search_ast_grep_dry_run"] = ToolSpec(
        name="aicarmine_repo_search_ast_grep_dry_run",
        description="Run ast-grep rewrite dry-run without writing source files.",
        input_schema=object_schema(
            {
                "pattern": string_prop(),
                "rewrite": string_prop(),
                "lang": string_prop("python"),
                "language": string_prop(),
                "path": string_prop("."),
                "timeout_seconds": integer_prop(120, 1, 600),
            },
            required=["pattern", "rewrite"],
        ),
        handler=repo_ast_grep_dry_run,
    )
    tools["aicarmine_repo_search_tree_sitter_parse"] = ToolSpec(
        name="aicarmine_repo_search_tree_sitter_parse",
        description="Parse a Python file with tree-sitter and return syntax anchors.",
        input_schema=object_schema(
            {"path": string_prop(), "language": string_prop("python"), "lang": string_prop()},
            required=["path"],
        ),
        handler=repo_tree_sitter_parse,
    )
    tools["aicarmine_repo_search_ctags"] = ToolSpec(
        name="aicarmine_repo_search_ctags",
        description="List symbols with universal-ctags JSON output.",
        input_schema=object_schema(
            {
                "path": string_prop("."),
                "paths": {"type": "array", "items": {"type": "string"}},
                "limit": integer_prop(500, 1, 5000),
                "timeout_seconds": integer_prop(120, 1, 600),
            }
        ),
        handler=repo_ctags_symbols,
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
            health_tool="aicarmine_repo_search_det_health",
            real_tool="aicarmine_repo_search_rg",
            real_args={"path": "services", "pattern": "AICARMINE_LAB_REPO", "max_results": 5},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())
