# Codex Ollama Bridge — Core Bridge Implementation

> **Purpose**: Core bridge implementation connecting Codex MCP server with Ollama GPU acceleration. Handles response bridging between providers.

---

## Files

| File | Purpose | Key Types/Functions |
|------|---------|----------------------|
| `aicarmine_codex_mcp_server.py` | Codex MCP server | MCP server implementation |
| `aicarmine_codex_ollama_responses_bridge.py` | Responses bridge | Bridges responses from Ollama |

---

## Architecture

```
┌─────────────────────────────────────┐
│   Codex + Ollama Bridge             │
├─────────────────────────────────────┤
│   aicarmine_codex_mcp_server.py     │ ← MCP server for Codex
│   aicarmine_codex_ollama_responses_bridge.py  ← Response bridge
└─────────────────────────────────────┘
```

---

## Documentation Index

| Document | Location |
|----------|----------|
| [Applied README](../README.md) | Full integration overview |
| [Complete Services Index](../../../docs/SERVICES_INDEX.md) | Full file-by-file documentation |

---

*Generated from analysis of the C:\Users\carmi\AI workspace.*