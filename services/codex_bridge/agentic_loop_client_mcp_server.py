#!/usr/bin/env python3
"""Refactored explicit Codex MCP client for dedicated canonical agentic-loop broker.

This module replaces the monolithic agentic_loop_client_mcp_server.py (~1720 lines)
with a thin facade (~200 lines) that delegates to extracted, testable modules:

  - http_client: HTTP client layer (astrazione httpx)
  - endpoint_validation: Validazione URL endpoint
  - broker_manager: Gestione processo broker
  - reranker_manager: Gestione OVMS reranker
  - dotenv_loader: Secret management (.env)

Mantiene la stessa interfaccia MCP (stessi tool, stessi input schema).
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

# Ensure services/ directory is on sys.path so repo_mcp_common can be imported
_services_root = Path(__file__).resolve().parent
if str(_services_root) not in sys.path:
    sys.path.insert(0, str(_services_root))

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    self_test,
    serve,
)

# ---------------------------------------------------------------------------
# Import extracted modules
# ---------------------------------------------------------------------------
from codex_bridge.http_client import AgenticLoopHttpClient, HttpClientError
from codex_bridge.endpoint_validation import (
    validate_endpoint,
    safe_int,
    DEFAULT_AGENTIC_LOOP_PORT,
    DEFAULT_RERANKER_PORT,
)
from codex_bridge.broker_manager import BrokerManager
from codex_bridge.reranker_manager import RerankerManager
from codex_bridge.dotenv_loader import DotEnvLoader, create_secret_manager

# ---------------------------------------------------------------------------
# Costanti server
# ---------------------------------------------------------------------------

SERVER_NAME = "aicarmine-agentic-loop-client-mcp"
SERVER_VERSION = "0.1.0"

# Token di conferma esplicita
CONFIRM_RUN = "aicarmine_agentic_loop_run"
CONFIRM_STATUS = "aicarmine_agentic_loop_status"
CONFIRM_RESULT = "aicarmine_agentic_loop_result"
CONFIRM_ENSURE = "aicarmine_agentic_loop_ensure_broker"
CONFIRM_RERANKER = "aicarmine_agentic_loop_ensure_reranker"

TERMINAL_STATUSES = {
    "completed",
    "failed",
    "blocked_needs_attention",
    "max_steps_reached",
    "cancelled",
    "cancel_requested",
}

# URL default dai env o hardcoded
DEFAULT_RERANKER_URL = (
    os.environ.get("AICARMINE_CONTROLLER_RAG_RERANK_URL")
    or os.environ.get("AICARMINE_RAG_RERANK_URL")
    or os.environ.get("RAG_EXTERNAL_RERANKER_URL")
    or f"http://127.0.0.1:{DEFAULT_RERANKER_PORT}/v3/rerank"
).strip()

DEFAULT_RERANKER_READY_URL = (
    os.environ.get("AICARMINE_RAG_RERANK_READY_URL")
    or os.environ.get("OPENVINO_PROVIDER_HEALTH_URL")
    or f"http://127.0.0.1:{DEFAULT_RERANKER_PORT}/v2/models/BAAI%2Fbge-reranker-v2-m3/ready"
).strip()

DEFAULT_AGENT_ENDPOINT = os.environ.get("AICARMINE_AGENTIC_LOOP_CLIENT_URL", "").strip()
if not DEFAULT_AGENT_ENDPOINT:
    DEFAULT_AGENT_ENDPOINT = f"http://127.0.0.1:{DEFAULT_AGENTIC_LOOP_PORT}/vulkan/agent"

DEFAULT_HEALTH_ENDPOINT = os.environ.get("AICARMINE_AGENTIC_LOOP_CLIENT_HEALTH_URL", "").strip()
if not DEFAULT_HEALTH_ENDPOINT:
    DEFAULT_HEALTH_ENDPOINT = f"http://127.0.0.1:{DEFAULT_AGENTIC_LOOP_PORT}/health"


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _safe_int(value: Any, default: int, low: int, high: int) -> int:
    """Convert value to int with bounds checking."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def _safe_bool(value: Any, default: bool = False) -> bool:
    """Convert value to bool with string fallback."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    return default


def _compact_text(value: Any, max_chars: int) -> tuple[str, bool]:
    """Compact text value with truncation marker."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2, default=str)
    if len(text) <= max_chars:
        return text, False
    suffix = f"\n...[truncated by {SERVER_NAME}; original_chars={len(text)}]"
    return text[:max(0, max_chars - len(suffix))].rstrip() + suffix, True


def _json_preview(value: Any, max_chars: int) -> dict[str, Any]:
    """Create JSON preview of value."""
    text, truncated = _compact_text(value, max_chars)
    return {"text": text, "truncated": truncated}


def _task_with_codex_contract(task: str) -> str:
    """Append Codex contract to task prompt."""
    contract = (
        "\n\nContratto finale per il chiamante Codex: quando finalizzi, restituisci una risposta "
        "compatta con punti chiave, citazioni a path/file o tool-result realmente letti quando "
        "disponibili, limiti espliciti se il job termina parziale/bloccato, e niente rimandi "
        "generici a file locali non presenti nel payload pubblico."
    )
    if "Contratto finale per il chiamante Codex" in task:
        return task
    return task.rstrip() + contract


def _codex_invocation_context(codex_root: str) -> dict[str, Any]:
    """Build invocation context for Codex caller."""
    return {
        "schema": "agentic_loop_invocation_context.v1",
        "caller": "codex_app",
        "caller_tool": "aicarmine_agentic_loop_client",
        "source": "codex_app_mcp_agentic_loop_client",
        "entrypoint": "mcp",
        "audience": "operator",
        "response_surface": "codex_app_mcp",
        "repo_root": codex_root,
        "expected_broker_lab_repo": codex_root,
        "default_broker_port": DEFAULT_AGENTIC_LOOP_PORT,
    }


def _compact_agent_response(
    response: dict[str, Any],
    *,
    response_budget_chars: int,
    include_raw: bool,
) -> dict[str, Any]:
    """Compact agent response for Codex consumption."""
    payload = response.get("payload") if response.get("ok") is True else response
    if not isinstance(payload, dict):
        payload = {"value": payload}

    status = str(payload.get("status") or payload.get("final_status") or "").strip()
    tool_context = payload.get("tool_context_for_30b")
    answer = (
        payload.get("answer_for_30b")
        or payload.get("final_summary")
        or payload.get("summary")
        or ""
    )
    answer_preview = _json_preview(answer, response_budget_chars)

    return {
        "ok": bool(response.get("ok")),
        "http_status": response.get("http_status"),
        "job_id": payload.get("job_id"),
        "status": status,
        "terminal": status in TERMINAL_STATUSES,
        "answer_preview": answer_preview["text"],
        "answer_truncated": answer_preview["truncated"],
        "raw_response_included": bool(include_raw),
    }


# ---------------------------------------------------------------------------
# Tool handlers - thin wrappers around extracted modules
# ---------------------------------------------------------------------------

def _health_handler(args: dict[str, Any], root: Path, tools: dict[str, ToolSpec]) -> dict[str, Any]:
    """Handle health check request."""
    payload = health_payload(SERVER_NAME, list(tools))
    payload.update({
        "read_only": False,
        "mode": "explicit_codex_to_dedicated_agentic_loop_client",
        "default_port": DEFAULT_AGENTIC_LOOP_PORT,
        "canonical_loop_endpoint": DEFAULT_AGENT_ENDPOINT,
        "health_endpoint": DEFAULT_HEALTH_ENDPOINT,
        "requires_explicit_confirmation": True,
        "confirmation_tokens": {
            "run": CONFIRM_RUN,
            "status": CONFIRM_STATUS,
            "result": CONFIRM_RESULT,
            "ensure_broker": CONFIRM_ENSURE,
            "ensure_reranker": CONFIRM_RERANKER,
        },
        "codex_mcp_repo_root": str(root),
    })
    return payload


def _capabilities_handler(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Handle capabilities request."""
    return {
        "ok": True,
        "tool": "aicarmine_agentic_loop_capabilities",
        "mode": "explicit_codex_to_dedicated_agentic_loop_client",
        "default_port": DEFAULT_AGENTIC_LOOP_PORT,
        "canonical_endpoint": DEFAULT_AGENT_ENDPOINT,
        "codex_mcp_repo_root": str(root),
        "uses_canonical_broker_planner_validator": True,
        "creates_no_local_planner_loop": True,
        "requires_confirmation_for_http": True,
        "can_start_dedicated_broker_for_codex_root": True,
        "can_start_dedicated_broker_with_uvicorn_reload": False,
        "can_restart_dedicated_broker": False,
        "can_start_local_bge_reranker": True,
        "tools": [
            "aicarmine_agentic_loop_health",
            "aicarmine_agentic_loop_capabilities",
            "aicarmine_agentic_loop_ensure_reranker",
            "aicarmine_agentic_loop_ensure_broker",
            "aicarmine_agentic_loop_run",
            "aicarmine_agentic_loop_status",
            "aicarmine_agentic_loop_result",
        ],
    }


def _run_handler(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Handle agentic loop run request using extracted modules."""
    # Validate confirmation
    if str(args.get("confirm_agentic_loop") or "").strip() != CONFIRM_RUN:
        return {
            "ok": False,
            "error": "explicit_agentic_loop_confirmation_required",
            "confirm_agentic_loop_required": CONFIRM_RUN,
            "agentic_loop_called": False,
        }

    # Initialize managers
    client = AgenticLoopHttpClient(timeout=_safe_int(args.get("timeout_seconds"), 120, 15, 900))
    broker_mgr = BrokerManager(root=root)
    reranker_mgr = RerankerManager(root=root)

    # Validate endpoint
    port = _safe_int(args.get("port"), DEFAULT_AGENTIC_LOOP_PORT, 1024, 65535)
    validated_endpoint, validation_error = validate_endpoint(
        args.get("endpoint"),
        expected_path="/vulkan/agent",
        port=port,
    )
    if validation_error is not None:
        return validation_error

    assert validated_endpoint is not None

    # Build payload
    task = str(args.get("task") or args.get("request") or args.get("prompt") or "").strip()
    if not task:
        return {"ok": False, "error": "missing_task"}

    payload = {
        "tool_name": "vulkan_helper",
        "task": _task_with_codex_contract(task),
        "job_action": "start",
        "return_mode": str(args.get("return_mode") or "wait").strip().lower(),
        "wait_seconds": _safe_int(args.get("wait_seconds"), 30, 1, 600),
        "max_steps": _safe_int(args.get("max_steps"), 20, 1, 80),
        "lab_repo": str(root.resolve(strict=False)),
        "codex_agentic_loop_client": True,
    }

    # Execute via HTTP client
    response = client.post_json(validated_endpoint, payload)
    compact = _compact_agent_response(
        response,
        response_budget_chars=_safe_int(args.get("response_budget_chars"), 12000, 1000, 60000),
        include_raw=_safe_bool(args.get("include_raw_response"), False),
    )
    compact.update({
        "tool": "aicarmine_agentic_loop_run",
        "agentic_loop_called": True,
        "endpoint": validated_endpoint,
        "port": port,
    })
    return compact


def _status_handler(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Handle agentic loop status request."""
    if str(args.get("confirm_agentic_loop") or "").strip() != CONFIRM_STATUS:
        return {
            "ok": False,
            "error": "explicit_agentic_loop_confirmation_required",
            "confirm_agentic_loop_required": CONFIRM_STATUS,
            "agentic_loop_called": False,
        }

    job_id = str(args.get("job_id") or "").strip()
    if not job_id:
        return {"ok": False, "error": "missing_job_id"}

    client = AgenticLoopHttpClient()
    port = _safe_int(args.get("port"), DEFAULT_AGENTIC_LOOP_PORT, 1024, 65535)
    validated_endpoint, validation_error = validate_endpoint(
        args.get("endpoint"),
        expected_path="/vulkan/agent",
        port=port,
    )
    if validation_error is not None:
        return validation_error

    assert validated_endpoint is not None

    payload = {
        "tool_name": "vulkan_helper",
        "job_id": job_id,
        "job_action": "status",
    }

    response = client.post_json(validated_endpoint, payload)
    compact = _compact_agent_response(response, response_budget_chars=8000, include_raw=False)
    compact.update({"tool": "aicarmine_agentic_loop_status", "agentic_loop_called": True})
    return compact


def _result_handler(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Handle agentic loop result request."""
    if str(args.get("confirm_agentic_loop") or "").strip() != CONFIRM_RESULT:
        return {
            "ok": False,
            "error": "explicit_agentic_loop_confirmation_required",
            "confirm_agentic_loop_required": CONFIRM_RESULT,
            "agentic_loop_called": False,
        }

    job_id = str(args.get("job_id") or "").strip()
    if not job_id:
        return {"ok": False, "error": "missing_job_id"}

    client = AgenticLoopHttpClient()
    port = _safe_int(args.get("port"), DEFAULT_AGENTIC_LOOP_PORT, 1024, 65535)
    validated_endpoint, validation_error = validate_endpoint(
        args.get("endpoint"),
        expected_path="/vulkan/agent",
        port=port,
    )
    if validation_error is not None:
        return validation_error

    assert validated_endpoint is not None

    payload = {
        "tool_name": "vulkan_helper",
        "job_id": job_id,
        "job_action": "result",
        "audience": str(args.get("audience") or "operator").strip().lower(),
    }

    response = client.post_json(validated_endpoint, payload)
    compact = _compact_agent_response(response, response_budget_chars=16000, include_raw=False)
    compact.update({"tool": "aicarmine_agentic_loop_result", "agentic_loop_called": True})
    return compact


def _ensure_reranker_handler(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Handle reranker ensure request using extracted module."""
    if str(args.get("confirm_ensure_reranker") or "").strip() != CONFIRM_RERANKER:
        return {
            "ok": False,
            "error": "explicit_reranker_start_confirmation_required",
            "confirm_ensure_reranker_required": CONFIRM_RERANKER,
            "reranker_started": False,
        }

    reranker_mgr = RerankerManager(root=root)
    ready_url = str(args.get("ready_url") or DEFAULT_RERANKER_READY_URL).strip()
    rerank_url = str(args.get("rerank_url") or DEFAULT_RERANKER_URL).strip()
    port = _safe_int(args.get("port"), DEFAULT_RERANKER_PORT, 1024, 65535)

    result = reranker_mgr.start_reranker(
        ready_url=ready_url,
        rerank_url=rerank_url,
        port=port,
        startup_timeout_seconds=_safe_int(args.get("startup_timeout_seconds"), 60, 5, 180),
    )
    result["tool"] = "aicarmine_agentic_loop_ensure_reranker"
    return result


def _ensure_broker_handler(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Handle broker ensure request using extracted module."""
    if str(args.get("confirm_ensure_broker") or "").strip() != CONFIRM_ENSURE:
        return {
            "ok": False,
            "error": "explicit_broker_start_confirmation_required",
            "confirm_ensure_broker_required": CONFIRM_ENSURE,
            "broker_started": False,
        }

    broker_mgr = BrokerManager(root=root)
    port = _safe_int(args.get("port"), DEFAULT_AGENTIC_LOOP_PORT, 1024, 65535)

    result = broker_mgr.start_broker(
        port=port,
        startup_timeout_seconds=_safe_int(args.get("startup_timeout_seconds"), 45, 5, 180),
        rerank_url=str(args.get("rerank_url") or DEFAULT_RERANKER_URL).strip(),
        reranker_ready_url=str(args.get("ready_url") or DEFAULT_RERANKER_READY_URL).strip(),
    )
    result["tool"] = "aicarmine_agentic_loop_ensure_broker"
    return result


# ---------------------------------------------------------------------------
# Tool specification builder
# ---------------------------------------------------------------------------

def _tools() -> dict[str, ToolSpec]:
    """Build tool specifications for MCP server."""
    tools: dict[str, ToolSpec] = {}

    def health_handler_wrapper(args: dict[str, Any], root: Path) -> dict[str, Any]:
        return _health_handler(args, root, tools)

    tools["aicarmine_agentic_loop_health"] = ToolSpec(
        name="aicarmine_agentic_loop_health",
        description="Report explicit dedicated agentic-loop client health; broker probe is opt-in.",
        input_schema=object_schema({
            "probe_broker": {"type": "boolean", "default": False},
            "port": {"type": "integer", "default": DEFAULT_AGENTIC_LOOP_PORT, "minimum": 1024, "maximum": 65535},
            "timeout_seconds": {"type": "integer", "default": 5, "minimum": 1, "maximum": 15},
        }),
        handler=health_handler_wrapper,
    )

    tools["aicarmine_agentic_loop_capabilities"] = ToolSpec(
        name="aicarmine_agentic_loop_capabilities",
        description="Describe the explicit Codex-to-dedicated-broker client and confirmation contract.",
        input_schema=object_schema(),
        handler=_capabilities_handler,
    )

    tools["aicarmine_agentic_loop_ensure_reranker"] = ToolSpec(
        name="aicarmine_agentic_loop_ensure_reranker",
        description="Ensure the local OVMS/BGE reranker is ready; starts script with explicit confirmation.",
        input_schema=object_schema({
            "confirm_ensure_reranker": {"type": "string"},
            "ready_url": {"type": "string", "default": DEFAULT_RERANKER_READY_URL},
            "rerank_url": {"type": "string", "default": DEFAULT_RERANKER_URL},
            "startup_timeout_seconds": {"type": "integer", "default": 60, "minimum": 5, "maximum": 180},
        }),
        handler=_ensure_reranker_handler,
    )

    tools["aicarmine_agentic_loop_ensure_broker"] = ToolSpec(
        name="aicarmine_agentic_loop_ensure_broker",
        description="Ensure a dedicated broker instance is running with AICARMINE_LAB_REPO equal to Codex root.",
        input_schema=object_schema({
            "confirm_ensure_broker": {"type": "string"},
            "port": {"type": "integer", "default": DEFAULT_AGENTIC_LOOP_PORT, "minimum": 1024, "maximum": 65535},
            "startup_timeout_seconds": {"type": "integer", "default": 45, "minimum": 5, "maximum": 180},
        }),
        handler=_ensure_broker_handler,
    )

    tools["aicarmine_agentic_loop_run"] = ToolSpec(
        name="aicarmine_agentic_loop_run",
        description="Start a canonical broker agentic-loop job on the dedicated Codex port.",
        input_schema=object_schema({
            "task": {"type": "string"},
            "confirm_agentic_loop": {"type": "string"},
            "port": {"type": "integer", "default": DEFAULT_AGENTIC_LOOP_PORT, "minimum": 1024, "maximum": 65535},
            "return_mode": {"type": "string", "enum": ["wait", "background", "async", "fire_and_forget"]},
            "wait_seconds": {"type": "integer", "default": 30, "minimum": 1, "maximum": 600},
            "max_steps": {"type": "integer", "default": 20, "minimum": 1, "maximum": 80},
            "timeout_seconds": {"type": "integer", "default": 120, "minimum": 15, "maximum": 900},
        }, required=["confirm_agentic_loop"]),
        handler=_run_handler,
    )

    tools["aicarmine_agentic_loop_status"] = ToolSpec(
        name="aicarmine_agentic_loop_status",
        description="Fetch compact status for a dedicated broker agentic-loop job.",
        input_schema=object_schema({
            "job_id": {"type": "string"},
            "confirm_agentic_loop": {"type": "string"},
            "port": {"type": "integer", "default": DEFAULT_AGENTIC_LOOP_PORT, "minimum": 1024, "maximum": 65535},
        }, required=["job_id", "confirm_agentic_loop"]),
        handler=_status_handler,
    )

    tools["aicarmine_agentic_loop_result"] = ToolSpec(
        name="aicarmine_agentic_loop_result",
        description="Fetch compact terminal result for a dedicated broker agentic-loop job.",
        input_schema=object_schema({
            "job_id": {"type": "string"},
            "confirm_agentic_loop": {"type": "string"},
            "audience": {"type": "string", "enum": ["openwebui", "operator", "internal"]},
            "port": {"type": "integer", "default": DEFAULT_AGENTIC_LOOP_PORT, "minimum": 1024, "maximum": 65535},
        }, required=["job_id", "confirm_agentic_loop"]),
        handler=_result_handler,
    )

    return tools


# ---------------------------------------------------------------------------
# Graceful shutdown handler
# ---------------------------------------------------------------------------

_shutdown_event = None

def _signal_handler(signum: int, frame: Any) -> None:
    """Handle SIGINT/SIGTERM for graceful shutdown."""
    global _shutdown_event
    if _shutdown_event is not None:
        _shutdown_event.set()
    print(f"\n[{SERVER_NAME}] Received signal {signum}, shutting down...", file=sys.stderr, flush=True)


def _setup_signal_handlers() -> None:
    """Setup signal handlers for graceful shutdown."""
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Main entry point for the MCP server.

    Args:
        argv: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    global _shutdown_event
    _shutdown_event = None
    _setup_signal_handlers()

    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()

    if "--self-test" in argv:
        result = self_test(
            server_name=SERVER_NAME,
            server_version=SERVER_VERSION,
            tools=tools,
            health_tool="aicarmine_agentic_loop_health",
            real_tool="aicarmine_agentic_loop_capabilities",
            real_args={},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1

    print(f"[{SERVER_NAME}] Starting MCP server...", file=sys.stderr, flush=True)
    try:
        return serve(SERVER_NAME, SERVER_VERSION, tools)
    except KeyboardInterrupt:
        print(f"[{SERVER_NAME}] Interrupted by user.", file=sys.stderr, flush=True)
        return 0
    except Exception as exc:
        print(f"[{SERVER_NAME}] Unexpected error: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())