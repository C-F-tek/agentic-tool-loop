# Guida all'Avvio Isolato dei Componenti

Questa guida descrive come avviare isolatamente ogni componente del sistema AI-Carmine:
- **Broker** (porta 3572)
- **Reranker Server** (porta 3550) - Alternativa Python-native a OVMS
- **MCP Server** (stdio)
- **Local Agent** (porta 3579)

---

## Panoramica Architettura

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AI-Carmine System                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │   Broker     │    │   Reranker   │    │   MCP Servers        │  │
│  │  (3572)      │    │   (3550)     │    │   (stdio)            │  │
│  │              │    │              │    │                      │  │
│  │  - Agentic   │    │  - BGE-v2-m3 │    │  - git-readonly      │  │
│  │    loop      │    │  - CrossEn-  │    │  - sqlite-readonly   │  │
│  │  - Job mgmt  │    │    coder     │    │  - repo-validate     │  │
│  └──────┬───────┘    └──────────────┘    │  - repo-search       │  │
│         │                                │  - project-memory    │  │
│         │                                └──────────────────────┘  │
│         │                                                           │
│  ┌──────┴───────┐                                                   │
│  │ Local Agent  │                                                   │
│  │  (3579)      │                                                   │
│  │              │                                                   │
│  │  - Subagent  │                                                   │
│  │  - Task exec │                                                   │
│  └──────────────┘                                                   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. Reranker Server (Porta 3550)

### Descrizione
Server HTTP Python-native che sostituisce OVMS (OpenVINO Model Server). Utilizza CrossEncoder da sentence-transformers per il reranking dei risultati RAG.

### Prerequisiti
```powershell
# Dipendenze già installate
pip install sentence-transformers huggingface_hub optimum[openvino]
```

### Modello
- **Nome**: `BAAI/bge-reranker-v2-m3`
- **Dimensione**: ~2.2 GB
- **Posizione**: `models-ovms-rerank/models/bge-reranker-v2-m3/`
- **Formato**: Safetensors (originale) + OpenVINO IR (convertito)

### Avvio Isolato

```powershell
# Dalla root del repository
cd services/codex_bridge

# Avvia il server reranker
python ovms_alternative_reranker.py --port 3550 --model BAAI/bge-reranker-v2-m3
```

### Con Launcher PowerShell

```powershell
cd services/codex_bridge
.\start_reranker.ps1
```

### Verifica

```powershell
# Health check
curl http://127.0.0.1:3550/health

# Model ready
curl http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready

# Test rerank
$body = @{
    model = "BAAI/bge-reranker-v2-m3"
    query = "test query"
    documents = @("document 1", "document 2", "document 3")
    top_k = 2
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:3550/v3/rerank" -Method Post -Body $body -ContentType "application/json"
```

### API Endpoints

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/health` | GET | Health check del server |
| `/models/list` | GET | Lista modelli disponibili |
| `/v3/rerank` | POST | Rerank documenti |
| `/v2/models/{name}/ready` | GET | Ready check modello |

### Variabili d'Ambiente per RAG

```powershell
$env:AICARMINE_RAG_RERANK_URL = "http://127.0.0.1:3550/v3/rerank"
$env:AICARMINE_RAG_RERANK_READY_URL = "http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready"
$env:AICARMINE_RAG_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
```

---

## 2. Broker (Porta 3572)

### Descrizione
Il broker è il cuore del sistema agentic. Gestisce il ciclo di vita dei job, il routing delle richieste MCP e la coordinazione tra i componenti.

### Prerequisiti
```powershell
# Verifica Python
python --version  # Python 3.10+ consigliato
```

### Avvio Isolato

```powershell
# Dalla root del repository
$env:AICARMINE_LAB_REPO = "C:\Users\sanit\agentic-tool-loop"
$env:AICARMINE_BROKER_PORT = 3572

python services\aicarmine_broker\aicarmine_broker.py --port 3572 --host 127.0.0.1
```

### Con Variabili d'Ambiente Complete

```powershell
$env:AICARMINE_LAB_REPO = "C:\Users\sanit\agentic-tool-loop"
$env:AICARMINE_REAL_REPO = "C:\Users\sanit\agentic-tool-loop"
$env:AICARMINE_VULKAN_WORKSPACE = "C:\Users\sanit\agentic-tool-loop\output"
$env:AICARMINE_AGENT_JOB_ROOT = "C:\Users\sanit\agentic-tool-loop\output\jobs"
$env:AICARMINE_BROKER_PORT = 3572

python services\aicarmine_broker\aicarmine_broker.py --port 3572
```

### Verifica

```powershell
# Controlla porta
netstat -ano | findstr "3572"

# Health check
curl http://127.0.0.1:3572/health

# Status endpoint
curl http://127.0.0.1:3572/status
```

---

## 3. MCP Server (stdio)

### Descrizione
I MCP (Model Context Protocol) server forniscono strumenti e risorse al sistema. Ogni server espone tool specifici tramite stdio.

### Lista MCP Server Disponibili

| Server | File | Descrizione |
|--------|------|-------------|
| `aicarmine-codex-app` | `services/codex_bridge/mcp_server.py` | Server principale con tool repo, memory, jobs |
| `aicarmine-repo-state` | `services/codex_bridge/repo_state_mcp_server.py` | Stato repository Git |
| `aicarmine-repo-search-det` | `services/codex_bridge/repo_search_det_mcp_server.py` | Ricerca file e contenuto |
| `aicarmine-rag` | `services/codex_bridge/rag_mcp_server.py` | RAG context e indicizzazione |
| `aicarmine-repo-validate` | `services/codex_bridge/repo_validate_mcp_server.py` | Validazione codice |
| `aicarmine-git-readonly` | `services/codex_bridge/git_readonly_mcp_server.py` | Operazioni Git read-only |
| `aicarmine-sqlite-readonly` | `services/codex_bridge/sqlite_readonly_mcp_server.py` | Query SQLite read-only |
| `aicarmine-job-artifact` | `services/codex_bridge/job_artifact_mcp_server.py` | Artifact job agent |
| `aicarmine-job-view` | `services/codex_bridge/job_view_mcp_server.py` | Visualizzazione job |
| `aicarmine-project-memory` | `services/codex_bridge/project_memory_mcp_server.py` | Memoria progetto |
| `aicarmine-local-subagent` | `services/codex_bridge/local_subagent_mcp_server.py` | Subagent locale |
| `aicarmine-agentic-loop-client` | `services/codex_bridge/agentic_loop_client_mcp_server.py` | Client agentic loop |
| `aicarmine-repo-code` | `services/codex_bridge/repo_code_mcp_server.py` | Editing codice repository |
| `aicarmine-codex-ops` | `services/codex_bridge/ops_mcp_server.py` | Operazioni sistema |

### Avvio Isolato (Esempio: RAG MCP)

```powershell
# Dalla root del repository
cd services/codex_bridge

# Il MCP server viene avviato automaticamente dal client Cline
# Per test manuale:
python rag_mcp_server.py
```

### Configurazione Cline MCP

I server MCP sono configurati in `cline_mcp_servers.json`:

```json
{
  "mcpServers": {
    "aicarmine-codex-app": {
      "command": "python",
      "args": ["C:\\Users\\sanit\\agentic-tool-loop\\services\\codex_bridge\\mcp_server.py"],
      "env": {}
    },
    "aicarmine-rag": {
      "command": "python",
      "args": ["C:\\Users\\sanit\\agentic-tool-loop\\services\\codex_bridge\\rag_mcp_server.py"],
      "env": {}
    }
  }
}
```

---

## 4. Local Agent (Porta 3579)

### Descrizione
Il Local Agent è un wrapper che permette di eseguire task agentic isolati attraverso il broker dedicato sulla porta 3579.

### Prerequisiti
- Broker in esecuzione sulla porta 3579 (o configurato)
- Reranker in esecuzione sulla porta 3550 (opzionale ma consigliato)

### Avvio Isolato

```powershell
# Assicurati che il broker sia in esecuzione
# Poi usa il client agentic loop

# Metodo 1: Via PowerShell con il server agentic loop
$env:AICARMINE_LAB_REPO = "C:\Users\sanit\agentic-tool-loop"

# Il local agent viene avviato tramite agentic_loop_client_mcp_server
# che si connette al broker su 3579
```

### Configurazione

```powershell
# Porta broker dedicato
$env:AICARMINE_BROKER_PORT = 3579

# Endpoint agentic
$env:AICARMINE_AGENT_ENDPOINT = "http://127.0.0.1:3579/vulkan/agent"

# Health check
$env:AICARMINE_AGENT_HEALTH = "http://127.0.0.1:3579/health"
```

### Verifica

```powershell
# Controlla porta
netstat -ano | findstr "3579"

# Health check
curl http://127.0.0.1:3579/health
```

---

## Script di Avvio Rapido

### Avvio Completo di Tutti i Componenti

```powershell
# ============================================
# Script di Avvio Completo AI-Carmine
# ============================================

$REPO_ROOT = "C:\Users\sanit\agentic-tool-loop"
$env:AICARMINE_LAB_REPO = $REPO_ROOT

Write-Host "=== AI-Carmine System Startup ===" -ForegroundColor Cyan

# 1. Avvia Reranker Server (porta 3550)
Write-Host "`n[1/4] Starting Reranker Server..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", 
    "cd '$REPO_ROOT\services\codex_bridge'; python ovms_alternative_reranker.py --port 3550"

Start-Sleep -Seconds 5  # Attendi caricamento modello

# 2. Avvia Broker (porta 3572)
Write-Host "[2/4] Starting Broker..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "$env:AICARMINE_LAB_REPO='$REPO_ROOT'; python '$REPO_ROOT\services\aicarmine_broker\aicarmine_broker.py' --port 3572"

Start-Sleep -Seconds 3

# 3. Verifica servizi
Write-Host "[3/4] Verifying services..." -ForegroundColor Yellow

$checks = @(
    @{Name="Reranker"; Port=3550},
    @{Name="Broker"; Port=3572}
)

foreach ($check in $checks) {
    $listening = netstat -ano | findstr ":$($check.Port)" | findstr "LISTENING"
    if ($listening) {
        Write-Host "  $($check.Name) (port $($check.Port)): OK" -ForegroundColor Green
    } else {
        Write-Host "  $($check.Name) (port $($check.Port)): NOT RUNNING" -ForegroundColor Red
    }
}

# 4. Imposta variabili ambiente
Write-Host "[4/4] Setting environment variables..." -ForegroundColor Yellow
$env:AICARMINE_RAG_RERANK_URL = "http://127.0.0.1:3550/v3/rerank"
$env:AICARMINE_RAG_RERANK_READY_URL = "http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready"

Write-Host "`n=== System Ready ===" -ForegroundColor Green
Write-Host "Reranker: http://127.0.0.1:3550/health" -ForegroundColor Cyan
Write-Host "Broker:   http://127.0.0.1:3572/health" -ForegroundColor Cyan
```

---

## Risoluzione Problemi

### Reranker Non Parte

```powershell
# Verifica dipendenze
python -c "import sentence_transformers; print('OK')"

# Verifica modello
Test-Path "models-ovms-rerank\models\bge-reranker-v2-m3\model.safetensors"

# Prova avvio manuale con verbose
cd services/codex_bridge
python ovms_alternative_reranker.py --port 3550 --model BAAI/bge-reranker-v2-m3
```

### Broker Non Parte

```powershell
# Verifica porta libera
netstat -ano | findstr "3572"

# Verifica dipendenze
python -c "import aicarmine_broker; print('OK')" 2>&1

# Avvio con logging
$env:AICARMINE_BROKER_PORT = 3572
python services\aicarmine_broker\aicarmine_broker.py --port 3572 --debug
```

### MCP Server Non Si Connette

```powershell
# Verifica configurazione Cline
Get-Content cline_mcp_servers.json | ConvertFrom-Json

# Verifica che i file esistano
Test-Path "services\codex_bridge\mcp_server.py"
Test-Path "services\codex_bridge\rag_mcp_server.py"
```

### Porta Già in Uso

```powershell
# Trova processo che usa la porta
netstat -ano | findstr "3550"

# Uccidi processo (sostituisci PID)
Stop-Process -Id <PID> -Force
```

---

## Riepilogo Porte

| Servizio | Porta | Protocollo | File Avvio |
|----------|-------|------------|------------|
| Reranker | 3550 | HTTP | `services/codex_bridge/ovms_alternative_reranker.py` |
| Broker | 3572 | HTTP | `services/aicarmine_broker/aicarmine_broker.py` |
| Local Agent | 3579 | HTTP | `services/codex_bridge/agentic_loop_client_mcp_server.py` |
| Ollama | 11434 | HTTP | `services/ollama-task-vulkan.ps1` |
| OpenWebUI | 8080 | HTTP | `services/openwebui.ps1` |

---

## Struttura File

```
agentic-tool-loop/
├── services/
│   ├── codex_bridge/
│   │   ├── ovms_alternative_reranker.py    # Server reranker Python-native
│   │   ├── start_reranker.ps1              # Launcher reranker
│   │   ├── mcp_server.py                   # MCP server principale
│   │   ├── rag_mcp_server.py               # MCP server RAG
│   │   ├── agentic_loop_client_mcp_server.py # Client agentic loop
│   │   └── ... (altri MCP server)
│   └── aicarmine_broker/
│       └── aicarmine_broker.py             # Broker principale
├── models-ovms-rerank/
│   ├── config.json                         # Config modelli
│   └── models/
│       └── bge-reranker-v2-m3/             # Modello reranker
│           ├── model.safetensors
│           ├── openvino_model.xml
│           ├── openvino_model.bin
│           └── ... (file OpenVINO)
├── docs/
│   ├── OVMS_RERANKER_SETUP.md              # Guida OVMS originale
│   └── ISOLATED_LAUNCH_GUIDE.md            # Questa guida
└── cline_mcp_servers.json                  # Configurazione MCP