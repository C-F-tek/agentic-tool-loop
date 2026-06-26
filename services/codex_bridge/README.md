# Codex Bridge — External Provider Integration

> **Purpose**: Codex bridge services connect to external Codex providers for extended AI capabilities. Provides MCP server integration and response bridging.

---

## Files

| File | Purpose | Key Types/Functions |
|------|---------|----------------------|
| `__init__.py` | Package init | — |
| `aicarmine_codex_mcp_server.py` | Codex MCP server | MCP server implementation |
| `aicarmine_codex_ollama_responses_bridge.py` | Responses bridge | Bridges responses from Ollama |

---

## Architecture

```
┌─────────────────────────────────────┐
│      Codex Bridge Service           │
│      Port 3581 (optional)           │
├─────────────────────────────────────┤
│   aicarmine_codex_mcp_server.py     │ ← MCP server for Codex
│   aicarmine_codex_ollama_responses_bridge.py  ← Response bridge
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