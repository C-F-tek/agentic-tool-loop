# AICarmine MCP Proxy

## Descrizione

Proxy unificato per tutti i server MCP di AICarmine. Gestisce 21 server e 130+ tool attraverso un singolo punto di accesso.

## Architettura

```
services/codex_bridge/mcp_proxy/
├── __init__.py           # Package initialization
├── config.py             # Server configuration (21 target servers, 130 route mappings)
├── router.py             # Tool-to-server routing logic
├── hooks.py              # Hook system (before/after/on_error + TelemetryHook)
├── server_manager.py     # Server subprocess lifecycle management
├── proxy_server.py       # Main FastMCP proxy server entry point
└── test_proxy.py         # Test suite
```

### Componenti

- **proxy_server.py**: FastMCP server entry point che espone tutti i tool aggregati
- **router.py**: Routing tool → server basato su route map configurabile
- **hooks.py**: Before/after/error hooks con rate limiting e telemetry
- **server_manager.py**: Gestione processi server (start/stop/call_tool/list_tools)
- **config.py**: Configurazione 21 server, 130 route, default environment

## Comandi

### Avvio
```bash
python -m services.codex_bridge.mcp_proxy.proxy_server
```

### Test
```bash
python -m services.codex_bridge.mcp_proxy.test_proxy
```

### PowerShell
```powershell
.\services\launch\proxy.ps1
.\services\launch\test_proxy.ps1
```

## Configurazione Cline

Aggiungi a `cline_mcp_servers.json`:

```json
{
  "mcpServers": {
    "aicarmine-proxy": {
      "type": "stdio",
      "command": "C:\\Users\\sanit\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
      "args": [
        "-u",
        "-m",
        "services.codex_bridge.mcp_proxy.proxy_server"
      ],
      "cwd": ".",
      "env": {
        "PYTHONPATH": ".",
        "AICARMINE_CODEX_MCP_REPO_ROOT": ".",
        "AICARMINE_LAB_REPO": ".",
        "AICARMINE_MCP_GZIP_ENABLED": "1",
        "AICARMINE_MCP_GZIP_THRESHOLD": "8192",
        "PATH": "C:\\Users\\sanit\\AppData\\Local\\Programs\\Python\\Python314;C:\\Users\\sanit\\AppData\\Local\\Programs\\Python\\Python314\\Scripts;%PATH%"
      }
    }
  }
}
```

## Hook Disponibili

### before_tool_call
- Rate limiting (configurable max calls/minute)
- Logging dettagliato di ogni chiamata
- Short-circuit: può restituire una risposta senza chiamare il tool
- Supporto job context (job_id, step)

### after_tool_call
- Aggiunge `_proxy_meta` con metadati (tool, server, timestamp, duration_ms)
- Supporto hook personalizzati tramite `register_after()`
- TelemetryHook per analytics

### on_error
- Gestione errori centralizzata
- Struttura errore standardizzata
- Logging dettagliato del traceback

## Routing

130+ tool mappati su 21 server. Fallback su `aicarmine-codex-app`.

### Route Map Esempio
| Tool Pattern | Server Target |
|-------------|---------------|
| propose_edit / create_file | aicarmine-repo-code |
| ollama_* | aicarmine-ollama |
| planner_* | aicarmine-broker-planner |
| rag_* | aicarmine-rag |
| default | aicarmine-codex-app |

## Verifica Finale

```powershell
# 1. Test del proxy
.\services\launch\test_proxy.ps1

# 2. Avvio del proxy
.\services\launch\proxy.ps1

# 3. Test con Cline dopo aver riavviato
# Chiedi a Cline: "Lista i tool MCP disponibili"
```

## Telemetry

Per abilitare il telemetry hook, aggiungi in `proxy_server.py`:

```python
from .hooks import TelemetryHook
proxy.hooks.register_after(TelemetryHook())
```

I dati vengono scritti in `state/proxy_telemetry.jsonl`.