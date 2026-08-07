#!/usr/bin/env python3
"""Standardized compressed JSON response format for all MCP servers.

Provides a unified response structure with bz2 compression, pagination,
metadata headers, and smart auto-compression so agents can read more
data per call without hitting token limits.

Usage:
    from services.codex_bridge.mcp_response_compression import (
        compress_response,
        decompress_response,
        mcp_tool_result,
        mcp_error_result,
    )

    result = compress_response(
        {"data": large_data, "summary": "overview"},
        use_compression=True,
    )
"""

from __future__ import annotations

import bz2
import json
import os
import sys
import time
import hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVICES_ROOT = Path(__file__).resolve().parent
REPO_HOME_ROOT = SERVICES_ROOT.parents[1] if SERVICES_ROOT.parents else Path.cwd()

COMPRESSION_ENABLED = os.environ.get(
    "AICARMINE_MCP_COMPRESSION",
    "0"
).strip().lower() in {"1", "true", "yes", "on"}

MAX_TEXT_CHARS = int(
    os.environ.get("AICARMINE_MCP_MAX_TEXT_CHARS", "24000")
)

COMPRESS_THRESHOLD = int(
    os.environ.get("AICARMINE_MCP_COMPRESS_THRESHOLD", "10000")
)

DEBUG_MODE = os.environ.get("AICARMINE_MCP_DEBUG", "0").strip().lower() in {
    "1", "true", "yes", "on"
}


# ---------------------------------------------------------------------------
# Compression helpers
# ---------------------------------------------------------------------------

def json_compress(value: Any) -> str:
    """Compress JSON payload using bz2. Returns hex-encoded compressed data."""
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    compressed = bz2.compress(raw.encode("utf-8"))
    return compressed.hex()


def json_decompress(hex_data: str) -> Any:
    """Decompress bz2-compressed JSON payload. Returns parsed JSON."""
    raw = bz2.decompress(bytes.fromhex(hex_data))
    return json.loads(raw.decode("utf-8"))


def smart_json_dumps(value: Any, *, use_compression: bool | None = None) -> str:
    """Smart JSON serialization: compresses if payload exceeds threshold."""
    if use_compression is None:
        use_compression = COMPRESSION_ENABLED
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    if use_compression and len(raw) > COMPRESS_THRESHOLD:
        return f"__compressed__:{json_compress(value)}"
    return raw


# ---------------------------------------------------------------------------
# Response structure
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResponseMetadata:
    """Metadata attached to every compressed MCP response."""
    server_name: str
    tool_name: str
    timestamp: float
    elapsed_ms: float
    compressed: bool
    original_size: int
    compressed_size: int
    chunk_index: int = 0
    total_chunks: int = 1
    next_offset: Optional[int] = None
    has_more: bool = False


def build_response_metadata(
    server_name: str,
    tool_name: str,
    start_time: float,
    compressed: bool = False,
    original_size: int = 0,
    compressed_size: int = 0,
    chunk_index: int = 0,
    total_chunks: int = 1,
    next_offset: Optional[int] = None,
    has_more: bool = False,
) -> dict[str, Any]:
    """Build metadata dict for response."""
    elapsed = (time.time() - start_time) * 1000
    return {
        "server": server_name,
        "tool": tool_name,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.gmtime()),
        "elapsed_ms": round(elapsed, 2),
        "compressed": compressed,
        "original_size_bytes": original_size,
        "compressed_size_bytes": compressed_size,
        "compression_ratio": round(original_size / max(compressed_size, 1), 2),
        "chunk_index": chunk_index,
        "total_chunks": total_chunks,
        "next_offset": next_offset,
        "has_more": has_more,
    }


# ---------------------------------------------------------------------------
# Compressed response builder
# ---------------------------------------------------------------------------

def compress_response(
    data: Any,
    *,
    server_name: str = "unknown",
    tool_name: str = "unknown",
    use_compression: bool | None = None,
    offset: int = 0,
    limit: int = MAX_TEXT_CHARS,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build a compressed JSON response with metadata headers.

    Args:
        data: The response data to serialize.
        server_name: MCP server name for metadata.
        tool_name: Tool name that was called.
        use_compression: Force compression (None = auto-detect).
        offset: Pagination offset for large results.
        limit: Max characters before truncation/compression.
        metadata: Additional metadata to include.

    Returns:
        Dict with 'result' and optional 'metadata' keys.
    """
    start_time = time.time()

    if use_compression is None:
        use_compression = COMPRESSION_ENABLED

    # Apply pagination if offset/limit specified
    if isinstance(data, dict) and "data" in data:
        original_data = dict(data)
        payload = data.get("data", {})
        if isinstance(payload, list) and (offset > 0 or limit < len(payload)):
            truncated = payload[offset:offset + limit]
            has_more = (offset + limit) < len(payload)
            original_data["data"] = truncated
            original_data["pagination"] = {
                "offset": offset,
                "limit": limit,
                "total": len(payload),
                "has_more": has_more,
            }
            data = original_data

    # Serialize and compress if needed
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    original_size = len(raw.encode("utf-8"))

    compressed_hex = None
    if use_compression and original_size > COMPRESS_THRESHOLD:
        compressed_hex = json_compress(data)
        compressed_size = len(compressed_hex)
        is_compressed = True
    else:
        compressed_size = original_size
        is_compressed = False

    # Build metadata
    response_metadata = build_response_metadata(
        server_name=server_name,
        tool_name=tool_name,
        start_time=start_time,
        compressed=is_compressed,
        original_size=original_size,
        compressed_size=compressed_size,
    )

    if metadata:
        response_metadata.update(metadata)

    # Build result structure
    result = {
        "ok": True,
        "data": data if not is_compressed else f"__compressed__:{compressed_hex}",
        "metadata": response_metadata,
    }

    return result


# ---------------------------------------------------------------------------
# Decompression helper
# ---------------------------------------------------------------------------

def decompress_response(text: str) -> Any:
    """Decompress a bz2-compressed MCP response text.

    Args:
        text: The response text, possibly prefixed with __compressed__:

    Returns:
        Decompressed JSON data or original text if not compressed.
    """
    if isinstance(text, str) and text.startswith("__compressed__:"):
        hex_data = text[len("__compressed__:"):]
        try:
            return json_decompress(hex_data)
        except Exception:
            return text  # Return original if decompression fails
    return text


# ---------------------------------------------------------------------------
# MCP tool result helpers
# ---------------------------------------------------------------------------

def mcp_tool_result(
    data: Any,
    *,
    server_name: str = "unknown",
    tool_name: str = "unknown",
    is_error: bool = False,
    use_compression: bool | None = None,
) -> dict[str, Any]:
    """Wrap data in MCP tool content format with optional compression.

    Args:
        data: The response data to wrap.
        server_name: MCP server name for metadata.
        tool_name: Tool name that was called.
        is_error: Whether this is an error response.
        use_compression: Force compression (None = auto-detect).

    Returns:
        Dict with 'content' list and 'isError' flag.
    """
    start_time = time.time()

    if use_compression is None:
        use_compression = COMPRESSION_ENABLED

    # Serialize data
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    original_size = len(raw.encode("utf-8"))

    text = raw
    compressed_hex = None
    if use_compression and original_size > COMPRESS_THRESHOLD:
        compressed_hex = json_compress(data)
        text = f"__compressed__:{compressed_hex}"

    response_metadata = build_response_metadata(
        server_name=server_name,
        tool_name=tool_name,
        start_time=start_time,
        compressed=(compressed_hex is not None),
        original_size=original_size,
        compressed_size=len(text.encode("utf-8")),
    )

    # Build MCP content structure
    content = [
        {
            "type": "text",
            "text": text,
        }
    ]

    # Add metadata as second content item if compression was used
    if response_metadata.get("compressed"):
        content.append({
            "type": "text",
            "text": json.dumps(response_metadata, ensure_ascii=False, indent=2),
        })

    return {
        "content": content,
        "isError": is_error,
    }


def mcp_error_result(
    message: str,
    *,
    code: int = -1,
    server_name: str = "unknown",
    tool_name: str = "unknown",
    data: Any = None,
) -> dict[str, Any]:
    """Build a standardized MCP error result.

    Args:
        message: Error message.
        code: JSON-RPC error code.
        server_name: MCP server name for metadata.
        tool_name: Tool name that was called.
        data: Additional error data.

    Returns:
        Dict with 'error' structure.
    """
    start_time = time.time()

    error = {
        "code": code,
        "message": message,
    }

    if data is not None:
        error["data"] = data

    response_metadata = build_response_metadata(
        server_name=server_name,
        tool_name=tool_name,
        start_time=start_time,
        compressed=False,
        original_size=len(message.encode("utf-8")),
        compressed_size=len(message.encode("utf-8")),
    )

    error["metadata"] = response_metadata

    return {
        "ok": False,
        "error": error,
    }


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 response builder
# ---------------------------------------------------------------------------

def jsonrpc_response(
    msg_id: Any,
    result: Any,
    *,
    server_name: str = "unknown",
    tool_name: str = "unknown",
) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 response with metadata.

    Args:
        msg_id: Request message ID.
        result: The response data.
        server_name: MCP server name for metadata.
        tool_name: Tool name that was called.

    Returns:
        JSON-RPC 2.0 compliant response dict.
    """
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": result,
    }


def jsonrpc_error(
    msg_id: Any,
    code: int,
    message: str,
    *,
    server_name: str = "unknown",
    tool_name: str = "unknown",
    data: Any = None,
) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 error response with metadata.

    Args:
        msg_id: Request message ID.
        code: Error code.
        message: Error message.
        server_name: MCP server name for metadata.
        tool_name: Tool name that was called.
        data: Additional error data.

    Returns:
        JSON-RPC 2.0 compliant error response dict.
    """
    error = {
        "code": code,
        "message": message,
    }
    if data is not None:
        error["data"] = data

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": error,
    }


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def log(server_name: str, message: str) -> None:
    """Debug logging to stderr if DEBUG_MODE is enabled."""
    if DEBUG_MODE:
        print(f"[{server_name}] {message}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

__all__ = [
    "compress_response",
    "decompress_response",
    "mcp_tool_result",
    "mcp_error_result",
    "jsonrpc_response",
    "jsonrpc_error",
    "json_compress",
    "json_decompress",
    "smart_json_dumps",
    "build_response_metadata",
    "log",
]