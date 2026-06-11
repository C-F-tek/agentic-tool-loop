#!/usr/bin/env python3
"""MCP adapter for deterministic repo validation tools."""

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

SERVER_NAME = "aicarmine-repo-validate-mcp"
SERVER_VERSION = "1.0.0"


def _tools() -> dict[str, ToolSpec]:
    from aicarmine_broker.tools.repo_deterministic import (
        repo_pyright_check,
        repo_pytest_run,
        repo_ruff_check,
        repo_semgrep_scan,
        repo_shellcheck,
    )
    from aicarmine_broker.tools.repo_validate import repo_validate

    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root):
        return health_payload(SERVER_NAME, list(tools))

    tools["aicarmine_repo_validate_health"] = ToolSpec(
        name="aicarmine_repo_validate_health",
        description="Report Python executable, cwd, repo root, branch, commit, and no-loop guarantees.",
        input_schema=object_schema(),
        handler=health,
    )
    tools["aicarmine_repo_validate_diffcheck"] = ToolSpec(
        name="aicarmine_repo_validate_diffcheck",
        description="Run repo_validate default git diff --check validation.",
        input_schema=object_schema(),
        handler=repo_validate,
    )
    tools["aicarmine_repo_validate_ruff"] = ToolSpec(
        name="aicarmine_repo_validate_ruff",
        description="Run ruff check with JSON diagnostics.",
        input_schema=object_schema(),
        handler=repo_ruff_check,
    )
    tools["aicarmine_repo_validate_pyright"] = ToolSpec(
        name="aicarmine_repo_validate_pyright",
        description="Run pyright with JSON diagnostics.",
        input_schema=object_schema(),
        handler=repo_pyright_check,
    )
    tools["aicarmine_repo_validate_pytest"] = ToolSpec(
        name="aicarmine_repo_validate_pytest",
        description="Run pytest on selected paths.",
        input_schema=object_schema(),
        handler=repo_pytest_run,
    )
    tools["aicarmine_repo_validate_shellcheck"] = ToolSpec(
        name="aicarmine_repo_validate_shellcheck",
        description="Run shellcheck JSON diagnostics on selected files.",
        input_schema=object_schema(),
        handler=repo_shellcheck,
    )
    tools["aicarmine_repo_validate_semgrep"] = ToolSpec(
        name="aicarmine_repo_validate_semgrep",
        description="Run semgrep JSON diagnostics with a pattern or config.",
        input_schema=object_schema(),
        handler=repo_semgrep_scan,
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
            health_tool="aicarmine_repo_validate_health",
            real_tool="aicarmine_repo_validate_diffcheck",
            real_args={"continue_on_failure": True, "timeout_seconds": 60},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())
