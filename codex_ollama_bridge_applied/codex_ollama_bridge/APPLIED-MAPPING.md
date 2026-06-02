# Mapping applicato ai file dello ZIP

## Componenti esistenti rilevati

| File/cartella | Ruolo nel bridge Codex |
|---|---|
| `aicarmine_vulkan_tool_broker.py` | Broker centrale su `3572`, dispatcher tool, repo tools, job state, helper composito. |
| `aicarmine_vulkan_bridge_server.py` | Bridge OpenAPI su `3571`; utile per OpenWebUI, non necessario per Codex quando si usa MCP. |
| `aicarmine-executor-server.py` / `aicarmine-run-safe-command.ps1` | Esecuzione comandi controllata/sicura, integrabile via broker. |
| `useful_tools/memory/agent_memory/*` | SQLite memory, record model, state packet, report. |
| `useful_tools/context/*` | Context pack, RAG context, heap context reload, semantic evidence chunks. |
| `useful_tools/pointers/*` | Layer predisposto per pointer/ref/state extension. |

## Nuovi adapter aggiunti

| File | Funzione |
|---|---|
| `aicarmine_codex_mcp_server.py` | Espone i tool del broker e la memory come server MCP stdio per Codex. |
| `aicarmine_codex_ollama_responses_bridge.py` | Espone `http://127.0.0.1:3581/v1` e inoltra a Ollama `11434`, con proxy `/api/*`. |
| `codex.aicarmine-ollama.config.toml` | Snippet user-level Codex con provider locale e MCP tools. |
| `start-codex-ollama-bridge.ps1` | Script Windows per installare/avviare bridge, broker e generare config. |
| `../AGENTS.md` | Regole operative locali per Codex nel workspace. |

## Tool MCP esposti

- `aicarmine_repo_capabilities`
- `aicarmine_repo_status`
- `aicarmine_repo_tree`
- `aicarmine_repo_list_files`
- `aicarmine_repo_search`
- `aicarmine_repo_read`
- `aicarmine_repo_apply_patch`
- `aicarmine_repo_write_file`
- `aicarmine_repo_validate`
- `aicarmine_repo_command`
- `aicarmine_vulkan_helper`
- `aicarmine_jobs_status`
- `aicarmine_job_detail`
- `aicarmine_memory_report`
- `aicarmine_memory_state_packet`

## Flusso consigliato

1. Codex usa il modello via provider `aicarmine_ollama_bridge`.
2. Codex usa il server MCP `aicarmine_tools` per leggere repo, memory e stato lavori.
3. Il broker 3572 resta il punto unico di routing dei tool locali.
4. Il bridge 3581 simula abbastanza Ollama/OpenAI-compatible per launcher e provider locale, ma non sostituisce le funzioni cloud Codex.
