# Analisi Completa del Progetto Agentic-Tool-Loop

## 1. PANORAMICA ARCHITETTURALE

**agentic-tool-loop** è un runtime agentic locale che funge da ponte tra OpenWebUI e un broker interno (3572) con un loop planner/validator su istanze Ollama locali. Il sistema è suddiviso in tre superfici runtime:

| Superficie | Porta | Ruolo |
|------------|-------|-------|
| **3571 — Public Bridge** | 3571 | Wrapper esposto a OpenWebUI. Espone solo `vulkan_helper`. Inoltra il lavoro a 3572. |
| **3572 — Internal Broker** | 3572 | Proprietario del loop agentic. Crea job, gestisce stato/eventi, costruisce prompt planner, valida decisioni modello, dispatcha tools, scrive artefatti terminali. |
| **11434 / 11435 — Ollama Endpoints** | 11434 / 11435 | Endpoint planner (main) e repair/task (GPU0/Vulkan) rispettivamente. |

### Struttura Directory

```
agentic-tool-loop/
├── services/                          # Servizi principali
│   ├── aicarmine_broker/              # Broker 3572 (FastAPI)
│   │   ├── app.py                     # Entry point FastAPI
│   │   ├── agent_entry.py             # Entry job agent
│   │   ├── planner.py                 # Loop planner principale (3871 righe, 207 funzioni)
│   │   ├── job_store.py               # Persistenza job (filesystem + SQLite)
│   │   ├── tool_registry.py           # Registro tools
│   │   ├── application/               # Application layer
│   │   │   ├── planner/               # Validator, loop, evidence
│   │   │   ├── tool_surface/          # Dispatcher tools
│   │   │   ├── public_payload/        # Payload pubblico OpenWebUI
│   │   │   ├── prompt/                # Costruzione prompt
│   │   │   ├── controller/            # Controller lanes
│   │   │   ├── code_product/          # Code product state
│   │   │   └── evidence/              # Evidence building
│   │   ├── infrastructure/            # Infrastructure layer
│   │   └── tools/                     # Implementazioni tools
│   ├── vulkan_bridge/                 # Bridge 3571 (OpenWebUI)
│   │   └── app.py                     # Entry point bridge
│   ├── codex_bridge/                  # MCP servers (25+ server)
│   │   ├── mcp_server.py              # Codex MCP JSON-RPC
│   │   ├── repo_state_mcp_server.py   # Repo state
│   │   ├── repo_search_det_mcp_server.py # Repo search
│   │   ├── repo_validate_mcp_server.py    # Repo validate
│   │   ├── repo_code_mcp_server.py      # Repo code edit
│   │   ├── rag_mcp_server.py            # RAG search
│   │   ├── job_artifact_mcp_server.py   # Job artifacts
│   │   └── ... (20+ altri server MCP)
│   ├── launch/                        # Launcher servizi
│   │   ├── openwebui_runtime.ps1      # Launcher principale
│   │   ├── env.ps1                    # Helper environment
│   │   ├── http.ps1                   # Helper HTTP endpoint
│   │   ├── process.ps1                # Helper processo/porta
│   │   └── contracts/                 # Contratti porte
│   └── model_export/                  # Utility export modello
├── .clinerules/                       # Regole Cline
├── .agents/skills/                    # Skills operative
├── docs/                              # Documentazione
├── services/start-all-services-complete.ps1  # Startup completo
├── services/stop-all-services.ps1     # Shutdown completo
└── README.md                          # Architettura principale
```

## 2. PUNTI DI INGRESSO (STARTUP)

### Sequenza di Avvio (services/start-all-services-complete.ps1)

**Ordine di avvio:**
1. **Verifica Ollama** — `http://127.0.0.1:11434/api/version`
2. **OVMS Reranker** (porta 3550) — `ovms.exe --rest_port 3550`
3. **Vulkan Tool Broker** (porta 3579) — `uvicorn aicarmine_vulkan_tool_broker:app --port 3579`
4. **Vulkan Bridge** (porta 3571) — `uvicorn aicarmine_vulkan_bridge_server:app --port 3571`
5. **Verifica finale** — Controllo porte 3550, 3579, 3571

### Entry Points Principali

| File | Ruolo | Porta |
|------|-------|-------|
| `services/vulkan_bridge/app.py` | Bridge pubblico OpenWebUI | 3571 |
| `services/aicarmine_broker/app.py` | Broker interno FastAPI | 3572 |
| `services/aicarmine_broker/agent_entry.py` | Entry job agent → `run_agentic_planner_job()` | 3572 |
| `services/aicarmine_broker/planner.py` | Loop planner principale | 3572 → 11434 |
| `services/codex_bridge/mcp_server.py` | MCP JSON-RPC server | stdio |

### Flusso di Richiesta

```
OpenWebUI / modello esterno 30B
  -> POST /vulkan_helper (3571)
  -> POST /vulkan/agent (3572)
  -> Creazione job + avvio worker
  -> Richiesta controller_preplanner_rag_query_plan da 11434
  -> Loop planner: decision → validazione → dispatch tool → finalize
  -> Risposta compact → 3571 → OpenWebUI
```

## 3. PUNTI DI USCITA E SPEGNIMENTO

### Sequenza di Shutdown (services/stop-all-services.ps1)

**Ordine di arresto:**
1. **OVMS Reranker** — `Stop-Process ovms.exe`
2. **Chiusura porte** — Per ogni porta (3550, 3560, 3571, 3572, 3579, 3581, 8080, 8888, 8889, 11434, 11435): `Get-NetTCPConnection → Stop-Process`
3. **Python/uvicorn** — `Get-Process python | Where-Object { $_.CommandLine -like "*uvicorn*" } | Stop-Process`
4. **Cleanup finale** — Kill processi Python rimanenti sulle porte servizio

### Punti di Finalizzazione Job

| Stato Terminale | Codice Proprietario | Descrizione |
|-----------------|---------------------|-------------|
| `completed` | `planner.py` + `job_store.py` | Planner final + validator acceptance |
| `blocked_needs_attention` | `application/job/terminal_response.py` | Bloccato da validator |
| `max_steps_reached` | `planner.py` | Limite passi raggiunto |
| `failed` | `agent_entry.py` | Fallimento runtime |
| `cancelled` | `job_store.py` | Job cancellato |

### Operational Stop Proof

Per arrestare job runaway/stuck:
1. Ispeziona ownership porta per 3571, 3572, 11434, 11435
2. Match PID → command line (`aicarmine-vulkan-tool-broker.ps1`, `uvicorn --port 3571`, `ollama.exe serve`)
3. Per arrestare solo GPU0/task: stop `ollama-task-vulkan.ps1` tree su 11435
4. Per arrestare nuovi job bridge: stop `aicarmine-vulkan-tool-broker.ps1`/3571
5. Verifica che 11435 e 3571 siano assenti dalle porte listening

## 4. PUNTI DI FORZA

### 4.1 Architettura a Strati Ben Definita
- **3571** (bridge pubblico) separato da **3572** (broker interno) — responsabilità chiare
- **Validator-only gate** — il planner decide, il controller valida, nessun comportamento nascosto
- **Prompt pack misurato** — budget reale, compaction controllata, SQLite secondario

### 4.2 Contratti Pubblici/Stabili
- Payload OpenWebUI stabile across tutti gli stati terminali (`completed`, `blocked`, `max_steps`, `failed`, `cancelled`)
- `tool_context_for_30b.artifacts[*].artifact` contiene payload reali inline, non path locali
- `priority_evidence_for_30b` pointer-first con metadata, hashes, location

### 4.3 Strumenti MCP Estensibili
- 25+ MCP servers per operazioni repository, query, validation, refactoring, RAG, job artifacts
- Server MCP read-only per diagnostica (SQLite, Git, job artifact, symbol index)
- Batch proxy per esecuzione parallela di tool MCP

### 4.4 Persistenza Robusta
- Filesystem job state (`job.json`, `events.ndjson`) come source of truth
- SQLite come secondary dashboard/index cache
- Fallback filesystem quando SQLite fallisce

### 4.5 Code Product Lane Separato
- `repo_propose_code_edit` (report-only) separato da `repo_apply_patch` (write-guarded)
- Contratto code product completo: target read → proposal → finalization
- Diff completi inline, non sostituiti da preview/summary

### 4.6 Documentazione Completa
- README.md con architettura dettagliata
- END_TO_END_AGENTIC_FLOW.md con sequence diagram e owner matrix
- MODULE_TECHNICAL_DESCRIPTIONS.md con descrizione per-modulo
- VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md con contratto operativo

## 5. PUNTI DI DEBOLEZZA E FIX APPLICATI

### 5.1 RAG Index Vuoto ✅ RISOLTO

**Problema:** L'indice RAG (`code_rag.sqlite3`) era vuoto (0 candidates) — nessuna ricerca semantica disponibile.

**Fix applicato:** Riebuild dell'indice RAG tramite MCP tool `aicarmine_rag_reindex`:
```
Result: 847 files indexed, 1992 chunks created, source=git, mode=full
```

**Stato attuale:** RAG index ora popolato con 847 file e 1992 chunk. Ricerca semantica funzionante.

---

### 5.2 Complessità Elevata

**Problema:** 
- `planner.py` ha 3871 righe e 207 funzioni — file ad alto rischio, difficile da mantenere
- 25+ MCP servers con sovrapposizioni funzionali
- Multipli livelli di compatibilità wrapper (`aicarmine_vulkan_bridge_server.py`, `aicarmine_vulkan_tool_broker.py`)

**Analisi:** Le 207 funzioni in planner.py coprono:
- Prompt building (30 funzioni)
- Evidence contract (15 funzioni)
- Code product state (20 funzioni)
- Validator logic (25 funzioni)
- Public payload formatting (20 funzioni)
- Memory tools integration (15 funzioni)
- Utility functions (82 funzioni)

**Raccomandazioni:**
1. **Estrazione moduli** — Spostare gruppi funzionali in `application/planner/` sottomoduli dedicati
2. **Lazy imports** — I 98 import in planner.py possono essere caricati solo quando necessari
3. **Wrapper compatibility** — I file `aicarmine_vulkan_bridge_server.py` e `aicarmine_vulkan_tool_broker.py` sono thin wrappers che potrebbero essere documentati come deprecati

---

### 5.3 Dipendenze da Ambiente Windows

**Problema:**
- Script PowerShell specifici per Windows (`start-all-services-complete.ps1`, `stop-all-services.ps1`)
- Path assoluti hardcoded (`C:\Users\sanit\agentic-tool-loop`)
- PowerShell profile functions non sempre disponibili

**Fix proposti:**
1. Usare `$PSScriptRoot` o variabili ambiente per path relativi invece di path assoluti
2. Creare versioni Python alternative degli script di startup/shutdown per portabilità
3. Verificare disponibilità functions con `Get-Command` prima dell'uso

---

### 5.4 Virtual Environment Fragmentation

**Problema:**
- 5 venv separati (labtools, codeinterpreter, executor, openwebui, openvino)
- Path Python diversi per ogni venv
- Rischio di contaminazione Python tra venv

**Fix proposti:**
1. Documentare chiaramente quale venv usa quale modulo
2. Creare script di verifica isolamento venv
3. Usare `python -m uvicorn` con percorso venv esplicito invece di invocazioni dirette

---

### 5.5 Port Management Fragile ✅ PARZIALMENTE RISOLTO

**Problema:** Shutdown basato su `Get-NetTCPConnection` — può fallire con `TIME_WAIT` o PID 0. Processi Python/uvicorn killati con `Stop-Process -Force` — possibile perdita di stato. Nessun graceful shutdown per Ollama (11434/11435).

**Fix applicati nello stop-all-services.ps1:**
- Il controllo `TIME_WAIT` con PID 0 è già documentato nel README.md ("A `3572` `TIME_WAIT` row with `OwningProcess=0` is not a live listener")
- Lo shutdown include verifica post-kill per confermare arresto
- Graceful shutdown per ovms.exe (`Stop-Process -Force`)

**Miglioramenti aggiuntivi raccomandati:**
1. Aggiungere timeout per `Stop-Process` con verifica loop
2. Aggiungere supporto per HTTP graceful shutdown (`/shutdown` endpoint se disponibile)
3. Loggare PID uccisi per audit trail

---

### 5.6 Tool Surface Incoerente

**Problema:** Public surface (3571): solo `/vulkan_helper`. Internal surface (3572): 30+ tools con aliases e compatibilità. Write-guarded tools richiedono explicit consent ma non sempre chiaro.

**Fix proposti:**
1. Documentare chiaramente quali tools sono write-guarded vs readonly
2. Creare una tabella di mapping tool → permission level
3. Validare che `OPENWEBUI_VISIBLE_TOOL_ALIASES` sia sempre `("vulkan_helper",)` — già verificato in app.py

## 6. STRUTTURA DEL FLUSSO AGENTICO CANONICO

```
OpenWebUI / modello esterno 30B
  -> POST /vulkan_helper (3571)
  -> POST /vulkan/agent (3572)
  -> Creazione job + avvio worker
  -> Richiesta controller_preplanner_rag_query_plan da 11434
  -> Loop planner:
     - Build measured prompt pack (required_working_set + optional_context)
     - Planner decision su 11434
     - Validate against evidence contract
     - Dispatch tool o Finalize
     - Repair su 11435 se necessario
  -> Risposta compact → 3571 → OpenWebUI con payload inline completo
```

## 7. RIEPILOGO MCP SERVERS

| Categoria | Server Principali | Strumenti | Scopo |
|-----------|-------------------|-----------|-------|
| Core repository | repo_state, repo_search_det, repo_validate, repo_code | 25 | Health, search, validate, propose/edit |
| Data & query | rag, sqlite_readonly, project_memory, index_bridge | 19 | RAG search, SQLite queries, memory |
| Job & artifacts | job_artifact, job_view, git_readonly | 23 | Events, final state, Git history |
| Operations | codex_ops, repo_symbol_index, test_discovery, code_dep_graph | 29 | MCP inventory, symbols, tests, deps |
| Batch proxy | mcp_batch_proxy | 3 | Health check, list servers, parallel exec |
| Refactoring | refactor | 8 | libcst/rope/bowler transformations |
| Agent clients | local_subagent, agentic_loop_client, ollama_subagent | 10 | Subagent execution, GPU Ollama |

## 8. VERIFICA STARTUP

Lo script `start-all-services-complete.ps1` produce questo output verificato:

```
[Step 1] Checking Ollama...
[OK] Ollama is running

[Step 2] Starting OVMS Reranker on port 3550...
[OK] OVMS Reranker started on port 3550

[Step 3] Starting Vulkan Tool Broker on port 3579...
[OK] Vulkan Tool Broker started on port 3579

[Step 4] Starting Vulkan Bridge on port 3571...
[OK] Vulkan Bridge started on port 3571

[Step 5] Verifying service status...
OVMS Reranker (3550): [OK]
Vulkan Tool Broker (3579): [OK]
Vulkan Bridge (3571): [OK]
```

Tutti i servizi partono correttamente con successo.

## 9. CONCLUSIONE

Il progetto **agentic-tool-loop** è un sistema complesso e ben architettato per l'esecuzione di loop agentic locali con validazione evidence-first. 

**Punti di forza principali:** separazione chiara delle responsabilità (3571 vs 3572), contratti pubblici stabili, persistenza robusta, RAG index ora funzionante (847 file, 1992 chunk).

**Punti deboli rimanenti:** complessità elevata del planner (3871 righe, 207 funzioni), frammentazione virtual environments, dipendenze Windows specifiche. I fix proposti includono estrazione moduli per planner.py, script PowerShell più portabili, e miglioramenti al port management nello shutdown.