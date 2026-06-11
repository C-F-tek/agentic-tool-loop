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
        input_schema=object_schema(),
        handler=repo_fd_files,
    )
    tools["aicarmine_repo_search_rg"] = ToolSpec(
        name="aicarmine_repo_search_rg",
        description="Search file contents with ripgrep JSON output inside the configured repo root.",
        input_schema=object_schema({"pattern": {"type": "string"}, "path": {"type": "string"}}),
        handler=repo_rg_search,
    )
    tools["aicarmine_repo_search_jq"] = ToolSpec(
        name="aicarmine_repo_search_jq",
        description="Run jq against json_text or a repo JSON file.",
        input_schema=object_schema({"query": {"type": "string"}, "json_text": {"type": "string"}}),
        handler=repo_jq_query,
    )
    tools["aicarmine_repo_search_ast_grep"] = ToolSpec(
        name="aicarmine_repo_search_ast_grep",
        description="Run ast-grep search inside the configured repo root.",
        input_schema=object_schema(),
        handler=repo_ast_grep_search,
    )
    tools["aicarmine_repo_search_ast_grep_dry_run"] = ToolSpec(
        name="aicarmine_repo_search_ast_grep_dry_run",
        description="Run ast-grep rewrite dry-run without writing source files.",
        input_schema=object_schema(),
        handler=repo_ast_grep_dry_run,
    )
    tools["aicarmine_repo_search_tree_sitter_parse"] = ToolSpec(
        name="aicarmine_repo_search_tree_sitter_parse",
        description="Parse a Python file with tree-sitter and return syntax anchors.",
        input_schema=object_schema({"path": {"type": "string"}}),
        handler=repo_tree_sitter_parse,
    )
    tools["aicarmine_repo_search_ctags"] = ToolSpec(
        name="aicarmine_repo_search_ctags",
        description="List symbols with universal-ctags JSON output.",
        input_schema=object_schema(),
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
