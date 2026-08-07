#!/usr/bin/env python3
"""Codex local subagent MCP facade backed by the dedicated agentic loop.

This server intentionally does not implement a direct Ollama/chat loop. The
only execution path delegates to ``aicarmine_agentic_loop_client`` so the same
broker planner/controller/validator logic remains the enforcement boundary.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any

import agentic_loop_client_mcp_server as agentic_loop_client
from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    self_test,
    serve,
)

SERVER_NAME = "aicarmine-local-subagent-mcp"
SERVER_VERSION = "0.2.0"

FORBIDDEN_PORTS = {3571, 3572, 8080, 11434, 11435}


def string_prop(default: str | None = None, *, enum: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    if enum is not None:
        schema["enum"] = enum
    return schema


def integer_prop(default: int, minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum, "maximum": maximum}


def boolean_prop(default: bool) -> dict[str, Any]:
    return {"type": "boolean", "default": default}


def object_prop() -> dict[str, Any]:
    return {"type": "object", "additionalProperties": True}


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    return default


def _subagent_contract(initial_context: str) -> dict[str, Any]:
    contract: dict[str, Any] = {
        "schema": "aicarmine_local_subagent_agentic_loop_facade.v1",
        "execution": "dedicated_agentic_loop",
        "direct_ollama_mode_removed": True,
        "approval_mode": "read_only",
        "expected_validator": "aicarmine_broker planner/controller/validator loop",
        "shared_openwebui_ports_not_used": [3571, 3572],
        "direct_model_ports_not_used": [11434, 11435],
    }
    if initial_context:
        contract["initial_context_supplied"] = True
    return contract


def _run_readonly(args: dict[str, Any], root: Path) -> dict[str, Any]:
    task = str(args.get("task") or "").strip()
    if not task:
        return {"ok": False, "error": "missing_task"}

    loop_args = dict(args)
    arguments = dict(loop_args.get("arguments")) if isinstance(loop_args.get("arguments"), dict) else {}
    context = dict(arguments.get("context")) if isinstance(arguments.get("context"), dict) else {}
    initial_context = str(loop_args.pop("initial_context", "") or "").strip()
    if initial_context:
        context["local_subagent_initial_context"] = initial_context
    context["local_subagent_contract"] = _subagent_contract(initial_context)
    arguments["context"] = context

    loop_args["arguments"] = arguments
    loop_args["task"] = (
        task.rstrip()
        + "\n\nContratto subagent locale: questa richiesta deve essere eseguita dal loop agentico "
        "dedicato Codex su porta non condivisa, non da una chat Ollama diretta. Usa la tool surface, "
        "i validator e gli artifact del planner/controller normale. Modalita' obbligatoria: read_only; "
        "non applicare patch, non scrivere file, non avviare OpenWebUI e non usare 3571/3572."
    )
    loop_args["approval_mode"] = "read_only"
    loop_args.setdefault("append_codex_final_contract", True)
    loop_args.setdefault("return_mode", "wait")

    result = agentic_loop_client._run(loop_args, root)
    payload = dict(result)
    payload.update(
        {
            "tool": "aicarmine_local_subagent_run_readonly",
            "delegated_tool": result.get("tool"),
            "delegated_to_agentic_loop": True,
            "direct_ollama_mode_removed": True,
            "read_only": True,
            "no_agentic_loop": False,
            "codex_mcp_repo_root": str(root),
        }
    )
    return payload


def _capabilities(args: dict[str, Any], root: Path) -> dict[str, Any]:
    del args
    return {
        "ok": True,
        "tool": "aicarmine_local_subagent_capabilities",
        "repo_root": str(root),
        "mode": "dedicated_agentic_loop_facade",
        "delegates_to": "aicarmine_agentic_loop_run",
        "default_port": agentic_loop_client.DEFAULT_AGENTIC_LOOP_PORT,
        "canonical_loop_endpoint": agentic_loop_client.DEFAULT_AGENT_ENDPOINT,
        "health_endpoint": agentic_loop_client.DEFAULT_HEALTH_ENDPOINT,
        "confirmation_tokens": {
            "run": agentic_loop_client.CONFIRM_RUN,
            "ensure_broker": agentic_loop_client.CONFIRM_ENSURE,
            "ensure_reranker": agentic_loop_client.CONFIRM_RERANKER,
        },
        "codex_app_subagents_inherited": False,
        "codex_app_subagents_note": "Codex /subagents are app-level agents. This MCP delegates local subagent work to the dedicated broker loop used by aicarmine_agentic_loop_client.",
        "write_tools": [],
        "read_only": True,
        "direct_ollama_mode_removed": True,
        "no_agentic_loop": False,
    }


def _health(args: dict[str, Any], root: Path, tools: dict[str, ToolSpec]) -> dict[str, Any]:
    payload = health_payload(SERVER_NAME, list(tools))
    probe_broker = _safe_bool(args.get("probe_broker"), False)
    payload.update(
        {
            "tool": "aicarmine_local_subagent_health",
            "mode": "dedicated_agentic_loop_facade",
            "delegates_to": "aicarmine_agentic_loop_run",
            "default_port": agentic_loop_client.DEFAULT_AGENTIC_LOOP_PORT,
            "canonical_loop_endpoint": agentic_loop_client.DEFAULT_AGENT_ENDPOINT,
            "health_endpoint": agentic_loop_client.DEFAULT_HEALTH_ENDPOINT,
            "root_isolation": {
                "codex_mcp_repo_root": os.environ.get("AICARMINE_CODEX_MCP_REPO_ROOT", ""),
                "effective_mcp_lab_repo": os.environ.get("AICARMINE_LAB_REPO", ""),
                "openwebui_loop_ports_not_used": [3571, 3572],
                "note": "Operational subagent runs use a dedicated Codex broker root/port through agentic_loop_client, not the OpenWebUI loop root.",
            },
            "forbidden_ports": sorted(FORBIDDEN_PORTS),
            "read_only": True,
            "no_broker_http": False,
            "broker_http_policy": "run delegates only through aicarmine_agentic_loop_client on the dedicated Codex port; health probes broker only when probe_broker=true.",
            "direct_ollama_mode_removed": True,
            "no_agentic_loop": False,
        }
    )
    if probe_broker:
        payload["broker_health"] = agentic_loop_client._health(
            {
                "port": args.get("port"),
                "health_endpoint": args.get("health_endpoint"),
                "probe_broker": True,
                "timeout_seconds": args.get("timeout_seconds"),
            },
            root,
            agentic_loop_client._tools(),
        )
    return payload


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        return _health(args, root, tools)

    tools["aicarmine_local_subagent_health"] = ToolSpec(
        name="aicarmine_local_subagent_health",
        description="Report local subagent facade health and dedicated agentic-loop root/port policy.",
        input_schema=object_schema(
            {
                "probe_broker": boolean_prop(False),
                "port": integer_prop(agentic_loop_client.DEFAULT_AGENTIC_LOOP_PORT, 1024, 65535),
                "health_endpoint": string_prop(agentic_loop_client.DEFAULT_HEALTH_ENDPOINT),
                "timeout_seconds": integer_prop(3, 1, 30),
            }
        ),
        handler=health,
    )
    tools["aicarmine_local_subagent_capabilities"] = ToolSpec(
        name="aicarmine_local_subagent_capabilities",
        description="Describe the local subagent facade over the dedicated Codex agentic loop.",
        input_schema=object_schema(),
        handler=_capabilities,
    )
    tools["aicarmine_local_subagent_run_readonly"] = ToolSpec(
        name="aicarmine_local_subagent_run_readonly",
        description="Run one bounded read-only local subagent task through the dedicated Codex agentic loop.",
        input_schema=object_schema(
            {
                "task": string_prop(),
                "initial_context": string_prop(),
                "arguments": object_prop(),
                # confirm_agentic_loop removed from schema per user request
                "port": integer_prop(agentic_loop_client.DEFAULT_AGENTIC_LOOP_PORT, 1024, 65535),
                "endpoint": string_prop(agentic_loop_client.DEFAULT_AGENT_ENDPOINT),
                "return_mode": string_prop("wait", enum=["wait", "background", "async", "fire_and_forget"]),
                "wait_seconds": integer_prop(30, 1, 600),
                "max_steps": integer_prop(20, 1, 80),
                "timeout_seconds": integer_prop(120, 15, 900),
                "response_budget_chars": integer_prop(12000, 1000, 60000),
                "include_raw_response": boolean_prop(False),
                "append_codex_final_contract": boolean_prop(True),
                "ensure_broker": boolean_prop(False),
                "confirm_ensure_broker": string_prop(),
                "ensure_reranker": boolean_prop(False),
                "confirm_ensure_reranker": string_prop(),
                "require_broker_repo_root_match": boolean_prop(True),
                "health_endpoint": string_prop(agentic_loop_client.DEFAULT_HEALTH_ENDPOINT),
                "health_timeout_seconds": integer_prop(5, 1, 20),
                "startup_timeout_seconds": integer_prop(45, 5, 180),
            },
            required=["task"],
        ),
        handler=_run_readonly,
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
            health_tool="aicarmine_local_subagent_health",
            real_tool="aicarmine_local_subagent_capabilities",
            real_args={},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())
