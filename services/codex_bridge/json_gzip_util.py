#!/usr/bin/env python3
"""
Gzip compression utility for large JSON payloads in MCP servers.

Provides transparent gzip compression/decompression for JSON-RPC messages
when payloads exceed a configurable threshold.

Environment variables:
    AICARMINE_MCP_GZIP_ENABLED: "1" to enable gzip compression (default: "0")
    AICARMINE_MCP_GZIP_THRESHOLD: Minimum payload size in bytes to compress (default: 8192)
    AICARMINE_MCP_GZIP_COMPRESSION_LEVEL: gzip compression level 1-9 (default: 6)

Usage:
    from .json_gzip_util import compress_json, decompress_json, should_compress
    
    # In _write_message or similar:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if should_compress(raw):
        raw = compress_json(raw)
    # send raw to stdout
    
    # In _read_message or similar:
    data = receive_from_stdin()
    if is_gzip(data):
        data = decompress_json(data)
    payload = json.loads(data)
"""
from __future__ import annotations

import gzip
import json
import os
import sys
from typing import Any

# Configuration
_GZIP_ENABLED = os.environ.get("AICARMINE_MCP_GZIP_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
_GZIP_THRESHOLD = int(os.environ.get("AICARMINE_MCP_GZIP_THRESHOLD", "8192"))
_GZIP_LEVEL = int(os.environ.get("AICARMINE_MCP_GZIP_COMPRESSION_LEVEL", "6"))

# Gzip magic bytes
_GZIP_MAGIC = b'\x1f\x8b'

# Content-Type header for gzip-encoded JSON
_GZIP_CONTENT_TYPE = "application/json+gzip"


def is_gzip(data: bytes) -> bool:
    """Check if data starts with gzip magic bytes."""
    return len(data) >= 2 and data[:2] == _GZIP_MAGIC


def should_compress(data: bytes) -> bool:
    """Check if data should be compressed based on size and configuration."""
    if not _GZIP_ENABLED:
        return False
    return len(data) >= _GZIP_THRESHOLD


def compress_json(data: bytes) -> bytes:
    """Compress bytes using gzip. Returns gzip-compressed data with magic bytes."""
    return gzip.compress(data, compresslevel=_GZIP_LEVEL)


def decompress_json(data: bytes) -> bytes:
    """Decompress gzip-compressed bytes. Returns original bytes."""
    return gzip.decompress(data)


def dumps_compressed(value: Any, separators: tuple[str, str] = (",", ":"), 
                     ensure_ascii: bool = True, default: Any = None) -> bytes:
    """
    Serialize to JSON and compress if above threshold.
    
    Returns compressed bytes if should_compress, otherwise raw JSON bytes.
    """
    raw = json.dumps(value, separators=separators, ensure_ascii=ensure_ascii, default=default).encode("utf-8")
    if should_compress(raw):
        return compress_json(raw)
    return raw


def loads_compressed(data: bytes) -> Any:
    """
    Deserialize JSON from potentially gzip-compressed bytes.
    
    Automatically detects and decompresses gzip data.
    """
    if is_gzip(data):
        data = decompress_json(data)
    return json.loads(data)


def format_message_compressed(payload: dict[str, Any]) -> bytes:
    """
    Format a JSON-RPC message with optional gzip compression.
    
    For Content-Length transport, adds Content-Encoding header if compressed.
    """
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    
    if should_compress(raw):
        compressed = compress_json(raw)
        # Add Content-Encoding header for HTTP-like framing
        header = f"Content-Length: {len(compressed)}\r\nContent-Encoding: {_GZIP_CONTENT_TYPE}\r\n\r\n".encode("ascii")
        return header + compressed
    return raw


def parse_message_compressed(raw: bytes) -> dict[str, Any]:
    """
    Parse a JSON-RPC message with optional gzip decompression.
    
    Handles both compressed and uncompressed messages.
    """
    # Check for gzip Content-Encoding header
    if b"Content-Encoding: " in raw[:200]:
        header_end = raw.find(b"\r\n\r\n")
        if header_end > 0:
            header = raw[:header_end].decode("ascii", errors="replace")
            if "Content-Encoding: " + _GZIP_CONTENT_TYPE in header:
                body = raw[header_end + 4:]
                return loads_compressed(body)
    
    # Check for direct gzip data
    if is_gzip(raw):
        return loads_compressed(raw)
    
    # Plain JSON
    return json.loads(raw)


def compression_ratio(original: bytes, compressed: bytes) -> float:
    """Calculate compression ratio (0.0 to 1.0, where 1.0 = no compression)."""
    if len(original) == 0:
        return 1.0
    return len(compressed) / len(original)


def log_compression_stats(original_size: int, compressed_size: int, msg_id: Any = None) -> None:
    """Log compression statistics to stderr."""
    if not DEBUG:
        return
    ratio = compression_ratio(bytes(original_size), bytes(compressed_size))
    saved = original_size - compressed_size
    prefix = f"[{SERVER_NAME}]" if (msg_id is not None) else ""
    print(
        f"{prefix} compression: {original_size} -> {compressed_size} bytes "
        f"({ratio:.1%} ratio, saved {saved} bytes)",
        file=sys.stderr, flush=True
    )


# Debug mode
DEBUG = os.environ.get("AICARMINE_MCP_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
SERVER_NAME = "aicarmine-gzip-util"


def test_compression() -> dict[str, Any]:
    """Run a quick compression test and return results."""
    test_data = {
        "test": "compression",
        "repeated": "x" * 10000,
        "nested": {
            "level1": {
                "level2": {
                    "level3": list(range(100))
                }
            }
        }
    }
    
    raw = json.dumps(test_data, separators=(",", ":")).encode("utf-8")
    compressed = compress_json(raw)
    
    decompressed = decompress_json(compressed)
    roundtrip_ok = decompressed == raw
    
    return {
        "original_size": len(raw),
        "compressed_size": len(compressed),
        "ratio": len(compressed) / len(raw) if raw else 1.0,
        "saved_bytes": len(raw) - len(compressed),
        "roundtrip_ok": roundtrip_ok,
        "enabled": _GZIP_ENABLED,
        "threshold": _GZIP_THRESHOLD,
    }


if __name__ == "__main__":
    result = test_compression()
    print(json.dumps(result, indent=2))
    print(f"\nGzip compression: {'ENABLED' if _GZIP_ENABLED else 'DISABLED'}")
    print(f"Threshold: {_GZIP_THRESHOLD} bytes")
    print(f"Level: {_GZIP_LEVEL}")