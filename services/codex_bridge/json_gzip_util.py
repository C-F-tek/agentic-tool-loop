#!/usr/bin/env python3
"""GZIP JSON compression utilities for large communication payloads.

Provides gzip-based compression/decompression for MCP tool responses,
job artifacts, and all inter-process communication payloads to avoid
truncation of large JSON responses.

Environment variables:
    AICARMINE_JSON_GZIP_COMPRESSION: Enable/disable gzip compression (default: 0)
    AICARMINE_JSON_GZIP_THRESHOLD: Minimum payload size in bytes to trigger compression (default: 10000)
    AICARMINE_JSON_GZIP_LEVEL: Gzip compression level 1-9 (default: 6)
"""

from __future__ import annotations

import gzip
import json
import os
import time
from typing import Any, Tuple

# Configuration from environment
COMPRESSION_ENABLED = os.environ.get("AICARMINE_JSON_GZIP_COMPRESSION", "1").strip().lower() in {
    "1", "true", "yes", "on"
}
COMPRESSION_THRESHOLD = int(os.environ.get("AICARMINE_JSON_GZIP_THRESHOLD", "10000"))
COMPRESSION_LEVEL = int(os.environ.get("AICARMINE_JSON_GZIP_LEVEL", "6"))

# Marker prefix for compressed payloads
COMPRESSED_MARKER = "__gzip_json__:"


def json_gzip_compress(value: Any) -> str:
    """Compress a JSON-serializable value using gzip.
    
    Returns a hex-encoded string of the gzip-compressed JSON.
    """
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    raw_bytes = raw.encode("utf-8")
    compressed = gzip.compress(raw_bytes, compresslevel=COMPRESSION_LEVEL, mtime=int(time.time()))
    return compressed.hex()


def json_gzip_decompress(hex_data: str) -> Any:
    """Decompress a gzip-compressed JSON payload.
    
    Returns the parsed Python object.
    """
    raw_bytes = gzip.decompress(bytes.fromhex(hex_data))
    return json.loads(raw_bytes.decode("utf-8"))


def smart_json_dumps(value: Any, *, use_compression: bool | None = None) -> str:
    """Smart JSON serialization: compresses if payload exceeds threshold.
    
    Returns either plain JSON or marker + compressed hex string.
    """
    if use_compression is None:
        use_compression = COMPRESSION_ENABLED
    
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    
    if use_compression and len(raw.encode("utf-8")) > COMPRESSION_THRESHOLD:
        compressed = json_gzip_compress(value)
        return f"{COMPRESSED_MARKER}{compressed}"
    
    return raw


def decompress_tool_text(text: str) -> str:
    """Decompress gzip-compressed MCP tool text. Returns original or decompressed text."""
    if isinstance(text, str) and text.startswith(COMPRESSED_MARKER):
        hex_data = text[len(COMPRESSED_MARKER):]
        try:
            return json_gzip_decompress(hex_data)
        except Exception:
            return text  # Return original if decompression fails
    return text


def compact_text_gzip(value: Any, limit: int = 24000) -> str:
    """Compact text with optional gzip compression for large payloads.
    
    If the value exceeds the limit, it attempts gzip compression.
    If compression still doesn't fit, returns truncated plain JSON.
    """
    if not isinstance(value, str):
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    else:
        raw = value
    
    if len(raw) <= limit:
        return raw
    
    # Try compression for large payloads
    if COMPRESSION_ENABLED:
        try:
            compressed = smart_json_dumps(value if not isinstance(value, str) else json.loads(value), use_compression=True)
            if len(compressed) < limit * 2:  # Accept compressed even if > limit
                return compressed
        except Exception:
            pass
    
    # Fallback: truncate
    return raw[: max(0, limit - 170)].rstrip() + "\n\n...[truncated by aicarmine_json_gzip]"


def tool_content_gzip(value: Any, is_error: bool = False) -> dict[str, Any]:
    """MCP tool content wrapper with optional gzip compression for large payloads."""
    text = compact_text_gzip(value)
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error
    }


def build_compressed_response(
    server_name: str,
    tool_name: str,
    original_size: int = 0,
    compressed_size: int = 0,
    compression_ratio: float = 0.0,
    chunk_index: int = 0,
    total_chunks: int = 1,
    has_more: bool = False,
) -> dict[str, Any]:
    """Build metadata dict for compressed response."""
    return {
        "server": server_name,
        "tool": tool_name,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.gmtime()),
        "compressed": True,
        "original_size_bytes": original_size,
        "compressed_size_bytes": compressed_size,
        "compression_ratio": round(compression_ratio, 2),
        "chunk_index": chunk_index,
        "total_chunks": total_chunks,
        "has_more": has_more,
        "method": "gzip_json",
    }


def format_compressed_payload(
    payload: Any,
    server_name: str = "",
    tool_name: str = "",
) -> dict[str, Any]:
    """Format a payload with gzip compression and metadata headers.
    
    Returns a dict suitable for MCP tool content response.
    """
    raw_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    original_size = len(raw_json.encode("utf-8"))
    
    should_compress = COMPRESSION_ENABLED and original_size > COMPRESSION_THRESHOLD
    
    if should_compress:
        compressed_hex = json_gzip_compress(payload)
        compressed_size = len(compressed_hex)
        ratio = original_size / max(compressed_size, 1)
        
        return {
            "content": [{
                "type": "text",
                "text": f"{COMPRESSED_MARKER}{compressed_hex}"
            }],
            "isError": False,
            "_metadata": build_compressed_response(
                server_name=server_name,
                tool_name=tool_name,
                original_size=original_size,
                compressed_size=compressed_size,
                compression_ratio=ratio,
            )
        }
    
    return {
        "content": [{"type": "text", "text": raw_json}],
        "isError": False,
    }


def parse_compressed_text(text: str) -> Tuple[Any, bool]:
    """Parse text that may be gzip-compressed JSON.
    
    Returns (parsed_object, was_compressed).
    """
    if isinstance(text, str) and text.startswith(COMPRESSED_MARKER):
        hex_data = text[len(COMPRESSED_MARKER):]
        try:
            return json_gzip_decompress(hex_data), True
        except Exception:
            return text, False
    
    try:
        return json.loads(text), False
    except (json.JSONDecodeError, TypeError):
        return text, False


def auto_compress_payload(payload: Any) -> Any:
    """Auto-detect if payload needs compression and apply gzip if enabled.
    
    For use in MCP servers that want automatic compression.
    """
    if not COMPRESSION_ENABLED:
        return payload
    
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(raw.encode("utf-8")) <= COMPRESSION_THRESHOLD:
        return payload
    
    return f"{COMPRESSED_MARKER}{json_gzip_compress(payload)}"