"""Endpoint validation utilities for agentic loop MCP server.

This module extracts endpoint validation logic from agentic_loop_client_mcp_server.py
into a reusable, testable validation layer.
"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import urllib.parse


class EndpointValidationError(Exception):
    """Exception raised when endpoint validation fails."""
    pass


RESERVED_PORTS = {3550, 3571, 3572, 8080, 11434, 11435}
DEFAULT_AGENTIC_LOOP_PORT = 3579
DEFAULT_RERANKER_PORT = 3550


def validate_endpoint(
    value: Any,
    expected_path: str,
    port: int | None = None,
) -> tuple[str | None, dict[str, Any] | None]:
    """Validate an agentic loop endpoint against allowlist rules.
    
    Returns (validated_url, error_dict) - error_dict is None on success.
    """
    raw = str(value or "").strip()
    if not raw:
        if port is not None:
            raw = _default_endpoint_for_path(expected_path, port=_safe_int(port, DEFAULT_AGENTIC_LOOP_PORT, 1024, 65535))
        else:
            raw = ""
    parsed = urllib.parse.urlparse(raw)
    port_value = parsed.port
    problem = {
        "ok": False,
        "error": "agentic_loop_endpoint_not_allowlisted",
        "endpoint": raw,
        "expected": _default_endpoint_for_path(expected_path, port=port_value or DEFAULT_AGENTIC_LOOP_PORT),
        "allowed_host": "127.0.0.1",
        "default_port": DEFAULT_AGENTIC_LOOP_PORT,
        "reserved_ports": sorted(RESERVED_PORTS),
        "allowed_path": expected_path,
        "forbidden": ["3571", "3572_shared_openwebui_broker", "11434", "11435", "OpenWebUI", "vulkan_helper_public_bridge"],
    }
    if parsed.scheme != "http":
        return None, problem | {"reason": "scheme_not_http"}
    if parsed.hostname != "127.0.0.1":
        return None, problem | {"reason": "host_not_127_0_0_1"}
    if port_value is None:
        return None, problem | {"reason": "missing_port"}
    if port_value in RESERVED_PORTS:
        return None, problem | {"reason": "reserved_port"}
    if port_value < 1024 or port_value > 65535:
        return None, problem | {"reason": "port_out_of_range"}
    if parsed.path.rstrip("/") != expected_path:
        return None, problem | {"reason": "path_mismatch"}
    if parsed.params or parsed.query or parsed.fragment or parsed.username or parsed.password:
        return None, problem | {"reason": "endpoint_must_not_include_auth_query_or_fragment"}
    return raw, None


def validate_local_http_endpoint(
    value: Any,
    default_url: str,
    expected_path_prefix: str,
    default_port: int,
    tool: str,
) -> tuple[str | None, dict[str, Any] | None]:
    """Validate a local HTTP endpoint against allowlist rules.
    
    Returns (validated_url, error_dict) - error_dict is None on success.
    """
    raw = str(value or default_url or "").strip()
    parsed = urllib.parse.urlparse(raw)
    problem = {
        "ok": False,
        "tool": tool,
        "error": "local_http_endpoint_not_allowlisted",
        "endpoint": raw,
        "allowed_host": "127.0.0.1",
        "default_port": default_port,
        "allowed_path_prefix": expected_path_prefix,
    }
    if parsed.scheme != "http":
        return None, problem | {"reason": "scheme_not_http"}
    if parsed.hostname != "127.0.0.1":
        return None, problem | {"reason": "host_not_127_0_0_1"}
    if parsed.port is None:
        return None, problem | {"reason": "missing_port"}
    if parsed.path.rstrip("/") and not parsed.path.startswith(expected_path_prefix):
        return None, problem | {"reason": "path_prefix_mismatch"}
    if parsed.params or parsed.query or parsed.fragment or parsed.username or parsed.password:
        return None, problem | {"reason": "endpoint_must_not_include_auth_query_or_fragment"}
    return raw, None


def port_listening(host: str = "127.0.0.1", port: int = DEFAULT_AGENTIC_LOOP_PORT, timeout_seconds: float = 0.5) -> bool:
    """Check if a port is listening."""
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def safe_int(value: Any, default: int, low: int, high: int) -> int:
    """Safely convert value to int with bounds checking."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def _default_endpoint_for_path(expected_path: str, port: int) -> str:
    """Build default endpoint URL for given path and port."""
    return f"http://127.0.0.1:{port}{expected_path}"