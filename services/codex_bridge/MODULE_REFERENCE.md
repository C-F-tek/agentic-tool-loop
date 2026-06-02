<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_START -->
Regole operative non negoziabili:
1. Il contratto non va modificato se non richiesto da Carmine esplicitamente.
2. Il prodotto finale puo' essere arricchito come gia' viene fatto; non cambiare logica senza richiesta esplicita.
3. Non devi presupporre nulla: non e' il tuo compito.
<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_END -->
# codex_bridge Module Reference

Updated: 2026-06-01

`codex_bridge` contains optional Codex-facing integration services. These are
not the OpenWebUI 3571 public bridge and are not the 3572 planner runtime. Keep
their startup lightweight and avoid importing broker-heavy modules before a
tool call actually needs them.

## Module Map

| Module | Technical description |
| --- | --- |
| `__init__.py` | Package marker for bridge implementations. |
| `mcp_server.py` | JSON-RPC/MCP server implementation for Codex. It reads and writes MCP frames, declares tools, calls broker HTTP endpoints on demand and exposes memory/health helpers. Startup must stay lazy so MCP handshake does not trigger broker/repo initialization. |
| `jsonrpc.py` | Compatibility exports from `mcp_server.py` for older import paths. No behavior should be added here. |
| `ollama_responses_bridge.py` | HTTP adapter that presents an OpenAI Responses-like surface over Ollama chat/native APIs. It can save/load response state, inject previous context and stream response events. Preserve native Ollama pass-through routes. |
| `responses_proxy.py` | Compatibility exports from `ollama_responses_bridge.py`. No behavior should be added here. |
| `storage.py` | Compatibility exports for storage helpers from `ollama_responses_bridge.py`. No behavior should be added here. |

## Runtime Notes

- MCP traffic is stdio JSON-RPC; raw stdout/stderr framing matters.
- Broker calls are HTTP calls after tool invocation, not import-time side
  effects.
- The Responses bridge is protocol-sensitive. Do not mix it with the 3571
  OpenWebUI tool contract.
- If Codex bridge behavior appears stale, verify which wrapper path launched it:
  `aicarmine_codex_mcp_server.py`, `aicarmine_codex_ollama_responses_bridge.py`
  or a package module directly.

## Safe Edit Checklist

1. Verify whether the caller is MCP stdio, HTTP Responses proxy or a historical
   wrapper.
2. Keep compatibility modules as facades.
3. Do not import 3572 broker modules during MCP handshake unless proven safe.
4. For HTTP adapter changes, capture a request/response sample before patching.

