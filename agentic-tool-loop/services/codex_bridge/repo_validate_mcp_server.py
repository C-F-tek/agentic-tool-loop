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
from repo_probe_profiles import (
    PROFILE_ORIENTATION_SELECTOR,
    PROFILE_ORIENTATION_SHADOW_HELPERS,
    PROFILE_ORIENTATION_SHADOW_EVALUATOR,
    repo_probe_profiles,
    repo_probe_run,
)

SERVER_NAME = "aicarmine-repo-validate-mcp"
SERVER_VERSION = "1.1.0"


def string_prop(default: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    return schema


def integer_prop(default: int, minimum: int, maximum: int) -> dict[str, Any]:
    return {
        "type": "integer",
        "default": default,
        "minimum": minimum,
        "maximum": maximum,
    }


def paths_schema(*, default_path: str | None = None) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "path": string_prop(default_path),
        "paths": {"type": "array", "items": {"type": "string"}},
    }
    return properties


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
        del args
        payload = health_payload(SERVER_NAME, list(tools))
        payload["probe_profiles_available"] = True
        payload["arbitrary_python_probe_allowed"] = False
        payload["probe_source_writes_performed"] = False
        return payload

    tools["aicarmine_repo_validate_health"] = ToolSpec(
        name="aicarmine_repo_validate_health",
        description=(
            "Report Python executable, cwd, repo root, branch, commit, "
            "available tools, and no-loop guarantees."
        ),
        input_schema=object_schema(),
        handler=health,
    )
    tools["aicarmine_repo_validate_diffcheck"] = ToolSpec(
        name="aicarmine_repo_validate_diffcheck",
        description="Run repo_validate default git diff --check validation.",
        input_schema=object_schema(
            {
                "commands": {"type": "array", "items": {"type": "string"}},
                "timeout_seconds": integer_prop(300, 1, 1800),
                "continue_on_failure": {
                    "type": "boolean",
                    "default": False,
                },
            }
        ),
        handler=repo_validate,
    )
    tools["aicarmine_repo_validate_ruff"] = ToolSpec(
        name="aicarmine_repo_validate_ruff",
        description="Run ruff check with JSON diagnostics.",
        input_schema=object_schema(
            {
                **paths_schema(default_path="."),
                "timeout_seconds": integer_prop(180, 1, 1200),
            }
        ),
        handler=repo_ruff_check,
    )
    tools["aicarmine_repo_validate_pyright"] = ToolSpec(
        name="aicarmine_repo_validate_pyright",
        description="Run pyright with JSON diagnostics.",
        input_schema=object_schema(
            {
                **paths_schema(default_path="."),
                "timeout_seconds": integer_prop(240, 1, 1200),
            }
        ),
        handler=repo_pyright_check,
    )
    tools["aicarmine_repo_validate_pytest"] = ToolSpec(
        name="aicarmine_repo_validate_pytest",
        description=(
            "Run pytest on selected paths only when explicitly requested "
            "by the user."
        ),
        input_schema=object_schema(
            {
                **paths_schema(default_path="."),
                "marker": string_prop(),
                "maxfail": integer_prop(1, 1, 20),
                "timeout_seconds": integer_prop(300, 1, 1800),
            }
        ),
        handler=repo_pytest_run,
    )
    tools["aicarmine_repo_validate_shellcheck"] = ToolSpec(
        name="aicarmine_repo_validate_shellcheck",
        description="Run shellcheck JSON diagnostics on selected files.",
        input_schema=object_schema(
            {
                **paths_schema(),
                "timeout_seconds": integer_prop(120, 1, 600),
            }
        ),
        handler=repo_shellcheck,
        required_one_of=[["path"], ["paths"]],
    )
    tools["aicarmine_repo_validate_semgrep"] = ToolSpec(
        name="aicarmine_repo_validate_semgrep",
        description=(
            "Run semgrep JSON diagnostics with a pattern or config."
        ),
        input_schema=object_schema(
            {
                "pattern": string_prop(),
                "config": string_prop(),
                "lang": string_prop("python"),
                "language": string_prop(),
                **paths_schema(default_path="."),
                "timeout_seconds": integer_prop(240, 1, 1200),
            }
        ),
        handler=repo_semgrep_scan,
        required_one_of=[["pattern"], ["config"]],
    )
    tools["aicarmine_repo_validate_probe_profiles"] = ToolSpec(
        name="aicarmine_repo_validate_probe_profiles",
        description=(
            "List static read-only probe profiles and report optional "
            "Hypothesis availability. Does not execute arbitrary Python."
        ),
        input_schema=object_schema(),
        handler=repo_probe_profiles,
    )
    tools["aicarmine_repo_validate_probe_run"] = ToolSpec(
        name="aicarmine_repo_validate_probe_run",
        description=(
            "Run a reviewed read-only probe profile with deterministic "
            "cases, Hypothesis-generated cases, or both. No network calls "
            "or source writes are permitted by the profile."
        ),
        input_schema=object_schema(
            {
                "profile_id": {
                    "type": "string",
                    "default": PROFILE_ORIENTATION_SELECTOR,
                    "enum": [PROFILE_ORIENTATION_SELECTOR, PROFILE_ORIENTATION_SHADOW_HELPERS, PROFILE_ORIENTATION_SHADOW_EVALUATOR],
                },
                "engine": {
                    "type": "string",
                    "default": "deterministic",
                    "enum": ["deterministic", "hypothesis", "both"],
                },
                "max_examples": integer_prop(200, 1, 1000),
                "seed": integer_prop(42, 0, 2_147_483_647),
            }
        ),
        handler=repo_probe_run,
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
            real_args={
                "continue_on_failure": True,
                "timeout_seconds": 60,
            },
        )
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())
