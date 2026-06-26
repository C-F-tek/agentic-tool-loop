# Codex Bridge — External Provider Integration

> **Purpose**: Codex bridge services connect to external Codex providers for extended AI capabilities. Provides MCP server integration, response bridging, and standardized compressed JSON responses.

---

## Files

| File | Purpose | Key Types/Functions |
|------|---------|----------------------|
| `__init__.py` | Package init | — |
| `aicarmine_codex_mcp_server.py` | Codex MCP server | MCP server implementation |
| `aicarmine_codex_ollama_responses_bridge.py` | Responses bridge | Bridges responses from Ollama |
| `mcp_response_compression.py` | **NEW** — Compressed JSON responses | `compress_response`, `decompress_response`, `mcp_tool_result`, `mcp_error_result` |
| `repo_mcp_common.py` | Shared stdio MCP helpers | `ok`, `err`, `json_compress`, `smart_json_dumps`, `tool_content` |

---

## Architecture

```
┌─────────────────────────────────────┐
│      Codex Bridge Service           │
│      Port 3581 (optional)           │
├─────────────────────────────────────┤
│   aicarmine_codex_mcp_server.py     │ ← MCP server for Codex
│   aicarmine_codex_ollama_responses_bridge.py  ← Response bridge
│   mcp_response_compression.py       ← NEW: Standardized compression
│   repo_mcp_common.py                ← Shared stdio helpers
└─────────────────────────────────────┘
```

---

## Key Components

### MCP Server (`aicarmine_codex_mcp_server.py`)

| Item | Description |
|------|-------------|
| **Role** | Exposes Codex capabilities via MCP protocol |
| **Tools** | Code generation, analysis, refactoring |

### Response Bridge (`aicarmine_codex_ollama_responses_bridge.py`)

| Item | Description |
|------|-------------|
| **Role** | Bridges responses between Codex and Ollama |
| **Purpose** | Normalize response formats across providers |

### Compressed JSON Responses (`mcp_response_compression.py`) — NEW

| Function | Purpose |
|----------|---------|
| `compress_response()` | Build compressed JSON response with metadata headers |
| `decompress_response()` | Decompress bz2-compressed MCP response text |
| `mcp_tool_result()` | Wrap data in MCP tool content format with compression |
| `mcp_error_result()` | Build standardized MCP error result |
| `jsonrpc_response()` | Build JSON-RPC 2.0 response with metadata |
| `jsonrpc_error()` | Build JSON-RPC 2.0 error response with metadata |

**Usage:**
```python
from services.codex_bridge.mcp_response_compression import (
    compress_response,
    mcp_tool_result,
)

# Auto-compress if payload > 10KB
result = compress_response(
    {"data": large_data, "summary": "overview"},
    server_name="codex_bridge",
    tool_name="some_tool",
)

# Wrap in MCP content format
content = mcp_tool_result(
    data,
    server_name="codex_bridge",
    tool_name="my_tool",
    use_compression=True,  # Force compression
)
```

**Environment Variables:**
| Variable | Default | Purpose |
|----------|---------|---------|
| `AICARMINE_MCP_COMPRESSION` | `0` | Enable bz2 compression (`1`, `true`, `yes`, `on`) |
| `AICARMINE_MCP_MAX_TEXT_CHARS` | `24000` | Max text chars in responses |
| `AICARMINE_MCP_COMPRESS_THRESHOLD` | `10000` | Compress if payload exceeds this (bytes) |
| `AICARMINE_MCP_DEBUG` | `0` | Enable debug logging |

---

## Shared Helpers (`repo_mcp_common.py`)

| Function | Purpose |
|----------|---------|
| `ok(msg_id, result)` | JSON-RPC 2.0 success response |
| `err(msg_id, code, message, data)` | JSON-RPC 2.0 error response |
| `json_compress(value)` | bz2-compressed JSON payload |
| `json_decompress(hex_data)` | Decompress bz2 payload |
| `smart_json_dumps(value)` | Auto-compress if payload > 10KB |
| `compact_text(value, limit)` | Truncate text to limit |
| `tool_content(value, is_error)` | MCP tool content wrapper |

---

## Related Services

| Service | Location | Purpose |
|---------|----------|---------|
| `codex_ollama_bridge_applied/codex_ollama_bridge/` | Applied changes | Full Codex + Ollama integration |
| `vulkan_bridge/` | GPU service | GPU-accelerated operations |

---

## Documentation Index

| Document | Location |
|----------|----------|
| [Complete Services Index](../../docs/SERVICES_INDEX.md) | Full file-by-file documentation |
| [Python Refactoring Guide](../../docs/PYTHON_REFACTORING_GUIDE.md) | Anti-patterns and case studies |

---

*Generated from analysis of the C:\Users\carmi\AI workspace.*