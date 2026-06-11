#!/usr/bin/env python3
"""MCP adapter for read-only deterministic repo state tools."""

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

SERVER_NAME = "aicarmine-repo-state-mcp"
SERVER_VERSION = "1.0.0"


def _tools() -> dict[str, ToolSpec]:
    from aicarmine_broker.tools.repo_status import repo_capabilities, repo_status

    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root):
        return health_payload(SERVER_NAME, list(tools))

    tools["aicarmine_repo_state_health"] = ToolSpec(
        name="aicarmine_repo_state_health",
        description="Report Python executable, cwd, repo root, branch, commit, and no-loop guarantees.",
        input_schema=object_schema(),
        handler=health,
    )
    tools["aicarmine_repo_state_status"] = ToolSpec(
        name="aicarmine_repo_state_status",
        description="Run deterministic read-only repo_status against the configured repo root.",
        input_schema=object_schema(),
        handler=repo_status,
    )
    tools["aicarmine_repo_state_capabilities"] = ToolSpec(
        name="aicarmine_repo_state_capabilities",
        description="Run deterministic read-only repo_capabilities against the configured repo root.",
        input_schema=object_schema(),
        handler=repo_capabilities,
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
            health_tool="aicarmine_repo_state_health",
            real_tool="aicarmine_repo_state_status",
            real_args={},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())
