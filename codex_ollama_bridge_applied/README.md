# Codex Ollama Bridge Applied — Full Integration

> **Purpose**: Applied changes for Codex + Ollama integration. This directory contains the production-ready implementation combining Codex MCP server with Ollama GPU acceleration.

---

## Structure

```
codex_ollama_bridge_applied/
├── README.md                    ← You are here
├── aicarmine_vulkan_bridge_server.py   ← Vulkan bridge server
├── aicarmine_vulkan_tool_broker.py     ← Vulkan tool broker
├── export_model.py                      ← Model export utility
├── codex_ollama_bridge/                 ← Core bridge implementation
│   ├── aicarmine_codex_mcp_server.py    ← MCP server
│   └── aicarmine_codex_ollama_responses_bridge.py  ← Response bridge
├── useful_tools/                          ← Utility library
│   ├── chunks/                           ← Code/evidence chunking
│   ├── context/                          ← Agent context management
│   └── memory/                           ← Agent memory operations
└── ...                                    ← PowerShell scripts, configs
```

---

## Core Files

| File | Purpose | Key Types |
|------|---------|-----------|
| `aicarmine_vulkan_bridge_server.py` | Vulkan bridge server | Server implementation |
| `aicarmine_vulkan_tool_broker.py` | Vulkan tool broker | Tool broker logic |
| `export_model.py` | Model export | Exports Ollama models |

---

## Codex Bridge (`codex_ollama_bridge/`)

| File | Purpose |
|------|---------|
| `aicarmine_codex_mcp_server.py` | MCP server for Codex integration |
| `aicarmine_codex_ollama_responses_bridge.py` | Bridges responses between Codex and Ollama |

---

## Useful Tools (`useful_tools/`)

### Chunks (`chunks/`)

| Directory | Purpose |
|-----------|---------|
| `code_chunks/` | Code chunking utilities |
| `evidence_chunks/` | Evidence chunking utilities |
| `proposal_chunks/` | Proposal chunking utilities |

### Context (`context/`)

| Directory | Purpose |
|-----------|---------|
| `agent_context/` | Agent context management |
| `context_pack/` | Context pack operations |
| `file_refs/` | File reference management |

### Memory (`memory/`)

| Directory | Purpose |
|-----------|---------|
| `agent_memory/` | Agent memory operations |
| `agent_memory/review/` | Memory review CLI |

---

## Documentation Index

| Document | Location |
|----------|----------|
| [Complete Services Index](../docs/SERVICES_INDEX.md) | Full file-by-file documentation |
| [Python Refactoring Guide](../docs/PYTHON_REFACTORING_GUIDE.md) | Anti-patterns and case studies |

---

*Generated from analysis of the C:\Users\carmi\AI workspace.*