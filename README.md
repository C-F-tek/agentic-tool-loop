# AI-Carmine Agentic Tool Loop

**Sistema agentic completo per automazione intelligente con integrazione LLM locale, RAG, e orchestrazione job.**

---

## Panoramica

Questo repository contiene il sistema AI-Carmine: un framework agentic completo che integra:

- **Broker agentic** con ciclo di vita job completo
- **Reranker BGE-v2-m3** per retrieval accurato
- **14+ MCP servers** per strumenti repository, database, e validazione
- **Integrazione OpenWebUI** con pipeline controller
- **Supporto multi-modello** (Ollama locale)

## Architettura

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

## Struttura Progetto

### Root Files

| File | Descrizione |
|------|-----------|
| `AGENTS.md` | Contratto operativo globale per agent Cline |
| `cline_mcp_servers.json` | Configurazione MCP servers per Cline |
| `PROJECT_STRUCTURE.md` | Albero completo di tutti i file (1204 linee) |
| `README.md` | Questo file - panoramica progetto |
| `flow.svg` | Diagramma flusso architettura |
| `implementation_plan.md` | Piano implementazione |
| `pytest.ini` | Configurazione pytest |
| `run_mcp.bat` | Launcher batch MCP servers |

### File di Log e Debug

| File | Descrizione |
|------|-----------|
| `Agentic_loop_GIT_LOG_FULL.txt` | Log completo git agentic loop |
| `agenti_loop_project.log` | Log progetto agentic loop |
| `storico_agentic_loop_git.log` | Storico operazioni git |
| `default` | File default (7.2 MB) |
| `qwen36-lean-show.json` | Configurazione modello Qwen (9.7 MB) |
| `same-capability-serious-scan.json` | Scan capacità equivalenti |

### Script Python

| File | Descrizione |
|------|-----------|
| `audit_mcp_allowlist.py` | Audit allowlist MCP servers |
| `check_existing_profiles.py` | Verifica profili esistenti |
| `debug_profiles.py` | Debug profili |
| `final_verify.py` | Verifica finale |
| `find_deps_config.py` | Trova dipendenze configurazione |
| `init_mcp_databases.py` | Inizializzazione database MCP |
| `probe_mcp_raw.py` | Probe MCP servers |
| `probe_r4r.py` | Probe reranker |
| `run_baseline_profiles.py` | Esecuzione baseline profiles |
| `test_mcp_client.py` | Test client MCP |
| `test_rag_mcp.py` | Test RAG MCP |
| `verify_changes.py` | Verifica modifiche |

### Script PowerShell

| File | Descrizione |
|------|-----------|
| `install_codex_app_mcp_only.ps1` | Installazione MCP solo codex app |

---

### Directory Principali

#### `.clinerules/` - Regole Cline

Contiene le regole operative per l'agent Cline.

| File | Descrizione |
|------|-----------|
| `00-aicarmine-mcp-first.md` | Regola prioritaria MCP AICarmine |
| `hooks/PostToolUse.ps1` | Hook post-tool use |
| `hooks/PreCompact.ps1` | Hook pre-compact |
| `hooks/PreToolUse.ps1` | Hook pre-tool use |
| `hooks/TaskStart.ps1` | Hook task start |
| `hooks/UserPromptSubmit.ps1` | Hook user prompt submit |
| `hooks/lib/` | Librerie hooks |
| `hooks/tests/` | Test hooks |

#### `.codex/` - Configurazione Codex

| File | Descrizione |
|------|-----------|
| `config.toml.disabled` | Configurazione Codex (disabilitata) |
| `hooks.json` | Configurazione hooks Codex |
| `hooks/aicarmine_mcp_probe_all.py` | Probe tutti MCP servers |
| `hooks/aicarmine_mcp_tool_log.py` | Log tool MCP |
| `mcp_servers_probe.json` | Report probe MCP |
| `state/mcp_probe_report.json` | Report stato MCP |
| `state/mcp_probe_report.jsonl` | Report stato MCP (JSONL) |

#### `.docs/` - Documentazione Interna

| File | Descrizione |
|------|-----------|
| `SYMBOL_IMPROVEMENTS.md` | Documentazione miglioramenti symbol |
| `tool_symbol_reference.json` | Riferimento simboli tool |

#### `cache/` - Cache

Directory cache del sistema.

#### `code-interpreter-workdir/` - Workdir Code Interpreter

Directory di lavoro per code interpreter.

---

#### `codex_ollama_bridge_applied/` - Bridge Codex-Ollama

Implementazione bridge tra Codex e Ollama.

| File | Descrizione |
|------|-----------|
| `AGENTS.md` | Regenti bridge Codex-Ollama |
| `aicarmine-executor-server.ps1/py` | Server executor |
| `aicarmine-jupyter-codeinterpreter.ps1` | Code interpreter Jupyter |
| `aicarmine-openwebui-serve.py` | Serve OpenWebUI |
| `aicarmine-run-safe-command.ps1` | Esegui comandi sicuri |
| `aicarmine-vulkan-tool-broker.ps1` | Vulkan tool broker |
| `aicarmine_vulkan_bridge_server.py` | Server bridge Vulkan |
| `aicarmine_vulkan_tool_broker.py` | Tool broker Vulkan |
| `check-dev-toolchain.ps1` | Verifica toolchain dev |
| `export_model.py` | Export modello |
| `ollama-task-vulkan.ps1` | Task Vulkan Ollama |
| `openvino-env.ps1` | Setup ambiente OpenVINO |
| `openwebui.ps1` | Launcher OpenWebUI |
| `ovms-reranker-npu.ps1` | Launcher reranker OVMS NPU |
| `sync-lab-from-main.ps1` | Sync lab da main |
| `watch-lab-mirror.ps1` | Watch lab mirror |
| `flow.svg` | Diagramma flusso |

##### `codex_ollama_bridge/` - Modulo Bridge

| File | Descrizione |
|------|-----------|
| `aicarmine_codex_mcp_server.py` | MCP server Codex |
| `aicarmine_codex_ollama_responses_bridge.py` | Bridge risposte Ollama |
| `APPLIED-MAPPING.md` | Mappatura applicata |
| `codex.aicarmine-ollama.config.toml` | Configurazione bridge |
| `README-CODEX-OLLAMA-BRIDGE.md` | Documentazione bridge |
| `start-codex-ollama-bridge.ps1` | Launcher bridge |

##### `useful_tools/` - Strumenti Utili

Strumenti ausiliari organizzati per funzionalità.

---

#### `commands/` - Comandi Git

Comandi JSON per operazioni Git.

| File | Descrizione |
|------|-----------|
| `branch.json` | Comando branch |
| `diff_check.json` | Comando diff check |
| `diff_name_status.json` | Comando diff name-status |
| `diff_stat.json` | Comando diff stat |
| `status.json` | Comando status |

#### `diag-qwen30b-*/` - Diagnostica Modello

File diagnostici per modello Qwen30B.

---

#### `docs/` - Documentazione

Documentazione principale del progetto.

| File | Descrizione |
|------|-----------|
| `ISOLATED_LAUNCH_GUIDE.md` | **Guida avvio isolato componenti** |
| `launcher_contract.md` | Contratto launcher |
| `OVMS_RERANKER_SETUP.md` | Guida setup OVMS reranker |
| `runtime_env_contract.md` | Contratto ambiente runtime |
| `START_HERE_RUNTIME.md` | Guida avvio rapido runtime |

---

#### `executor-runs/` - Esecuzioni Executor

Directory per esecioni executor.

---

#### `indexAI/` - Indicizzazione AI

Database indicizzazione AI.

| File | Descrizione |
|------|-----------|
| `agent_memory/agent_memory.sqlite` | Database memoria agent |
| `agent_memory.sqlite-shm` | Shared memory SQLite |
| `agent_memory.sqlite-wal` | Write-ahead log SQLite |

---

#### `knowledge-*/` - Knowledge Base

Diverse directory per knowledge base organizzate per dimensione/formato.

| Directory | Descrizione |
|-----------|-------------|
| `knowledge-bad-md/` | Knowledge base markdown non validato |
| `knowledge-code-packs/` | Pack codice knowledge |
| `knowledge-md/` | Knowledge base markdown |
| `knowledge-md-parts/` | Parti knowledge markdown |
| `knowledge-small-md/` | Knowledge base piccola |
| `knowledge-sync/` | Knowledge sync |
| `knowledge-tiny-md/` | Knowledge base tiny |
| `knowledge-upload-batches/` | Batch upload knowledge |

---

#### `lab-patches/` - Patch Lab

Directory per patch lab.

#### `lab-worktrees/` - Worktrees Lab

Directory per worktrees Git lab.

#### `logs/` - Log

Directory per file log.

---

#### `modelfiles/` - Modelli

Modelfile per modelli LLM.

| File | Descrizione |
|------|-----------|
| `Modelfile.devstral-32k` | Modelfile devstral 32k |
| `Modelfile.qwen3coder-32k` | Modelfile qwen3coder 32k |
| `Modelfile.qwen3task-8k` | Modelfile qwen3task 8k |
| `README.md` | Documentazione modelfile |

---

#### `models-*/` - Modelli

Directory per modelli ML.

| Directory | Descrizione |
|-----------|-------------|
| `models-cpu/` | Modelli CPU |
| `models-ovms-rerank/` | **Modelli reranker OVMS** |
| `models-task/` | Modelli task |
| `npu-models/` | Modelli NPU |

##### `models-ovms-rerank/` - Modelli Reranker

Modelli per reranking BGE-v2-m3.

| File | Descrizione |
|------|-----------|
| `config.json` | Configurazione modelli OVMS |
| `models/bge-reranker-v2-m3/` | **Modello reranker** |
| `models/bge-reranker-v2-m3/model.safetensors` | Modello originale (2.2 GB) |
| `models/bge-reranker-v2-m3/openvino_model.xml/.bin` | Modello OpenVINO |
| `models/bge-reranker-v2-m3/openvino_tokenizer.xml/.bin` | Tokenizer OpenVINO |
| `models/bge-reranker-v2-m3/openvino_detokenizer.xml/.bin` | Detokenizer OpenVINO |

---

#### `npu-models/` - Modelli NPU

Modelli per accelerazione NPU.

#### `ollama-modelfiles/` - Modelfile Ollama

| File | Descrizione |
|------|-----------|
| `qwen36-35b-codex-lean.Modelfile` | Modelfile Qwen36 35B codex lean |

---

#### `openwebui-data/` - Dati OpenWebUI

Directory dati persistenti OpenWebUI.

---

#### `output/` - Output

Output del sistema.

| Directory | Descrizione |
|-----------|-------------|
| `agent-jobs/` | Job agent |
| `ai_runtime_memory/` | Memoria runtime AI |

---

#### `ovms-runtime/` - Runtime OVMS

Runtime OpenVINO Model Server.

| File | Descrizione |
|------|-----------|
| `setupvars.ps1` | Script setup variabili ambiente |
| `bin/` | Binari OVMS |

---

#### `payloads/` - Payloads

Directory per payloads.

---

#### `project-openwebui-pipelines-controller/` - Pipeline Controller

Controller pipeline OpenWebUI.

| File | Descrizione |
|------|-----------|
| `.env.example` | Esempio variabili ambiente |
| `docker-compose.pipelines.override.yml` | Override docker compose |
| `docs/CHAIN_OF_CAUSALITY.md` | Documentazione causalità |
| `pipelines/aicarmine_vulkan_controller_pipeline.py` | Pipeline controller Vulkan |
| `README.md` | Documentazione controller |

---

#### `services/` - Servizi

Servizi principali del sistema.

##### `services/codex_bridge/` - Bridge Codex

Moduli bridge Codex.

| File | Descrizione |
|------|-----------|
| **`agentic_loop_client_mcp_server.py`** | **Client agentic loop (73 KB)** |
| `git_readonly_mcp_server.py` | MCP server Git read-only |
| `job_artifact_mcp_server.py` | MCP server artifact job |
| `job_view_mcp_server.py` | MCP server visualizzazione job |
| `local_subagent_mcp_server.py` | MCP server subagent locale |
| **`mcp_server.py`** | **MCP server principale (55 KB)** |
| `ollama_responses_bridge.py` | Bridge risposte Ollama |
| **`ops_mcp_server.py`** | **MCP server operazioni sistema (33 KB)** |
| **`ovms_alternative_reranker.py`** | **Server reranker Python-native (6 KB)** |
| `project_memory_mcp_server.py` | MCP server memoria progetto |
| `rag_index_repo.py` | Indicizzazione repository RAG |
| **`rag_mcp_server.py`** | **MCP server RAG (32 KB)** |
| `repo_code_change_set.py` | Gestione change set codice |
| `repo_code_mcp_server.py` | MCP server editing codice |
| `repo_mcp_common.py` | Utili comuni MCP repository |
| `repo_search_det_mcp_server.py` | MCP server ricerca deterministica |
| `repo_state_mcp_server.py` | MCP server stato repository |
| `repo_validate_mcp_server.py` | MCP server validazione repository |
| `sqlite_readonly_mcp_server.py` | MCP server SQLite read-only |
| `tool_surface_cache.py` | Cache superficie tool |
| `start_reranker.ps1` | **Launcher PowerShell reranker** |
| `MCP_GUIDE.md` | Guida MCP servers |
| `MODULE_REFERENCE.md` | Riferimento moduli |
| `README.md` | Documentazione modulo |

##### `services/aicarmine_broker/` - Broker

Broker agentic principale.

| File | Descrizione |
|------|-----------|
| `agent_entry.py` | Entry point agent |
| `app.py` | Applicazione broker |
| `code_edit_proposal_contract.py` | Contratto proposta edit codice |
| `flow.svg` | Diagramma flusso |
| `helper.py` | Utili helper |
| `job_html.py` | Rendering HTML job |
| `job_html_assets.py` | Assets HTML job |
| `job_planner_lab.py` | Planner lab job |
| `job_store.py` | Store job |
| `memory_tools.py` | Strumenti memoria |
| `MODULE_REFERENCE.md` | Riferimento moduli |
| `planner.py` | **Planner agentic (251 KB)** |
| `planner_intrinsic_context.py` | Contesto intrinseco planner |
| `public_wrapper.py` | Wrapper pubblico |
| `README.md` | Documentazione broker |
| `repo_tools.py` | Strumenti repository |
| `tool_contract.py` | Contratto tool |
| `tool_dispatch.py` | Dispatch tool |
| `tool_registry.py` | Registry tool |
| `tool_schemas.py` | Schemi tool |
| `tool_selection.py` | Selezione tool |

##### Altri Servizi

| File | Descrizione |
|------|-----------|
| `aicarmine-executor-server.ps1/py` | Server executor |
| `aicarmine-jupyter-codeinterpreter.ps1` | Code interpreter Jupyter |
| `aicarmine-openwebui-serve.py` | Serve OpenWebUI |
| `aicarmine-run-safe-command.ps1` | Comandi sicuri |
| `aicarmine-vulkan-tool-broker.ps1` | Vulkan tool broker |
| `aicarmine_codex_mcp_server.py` | MCP server Codex |
| `aicarmine_codex_ollama_responses_bridge.py` | Bridge risposte |
| `aicarmine_vulkan_bridge_server.py` | Server bridge Vulkan |
| `aicarmine_vulkan_tool_broker.py` | Tool broker Vulkan |
| `apply_openwebui_ps1_open_terminal.py` | Apri terminale OpenWebUI |
| `check-dev-toolchain.ps1` | Verifica toolchain |
| `MODULE_TECHNICAL_DESCRIPTIONS.md` | Descrizioni tecniche moduli |
| `OPENWEBUI_INLINE_EVIDENCE_CONTRACT.md` | Contratto evidenza inline |
| `RUNTIME_SCRIPT_REFERENCE.md` | Riferimento script runtime |
| `SERVICES_MODULE_TECHNICAL_REFERENCE.md` | Riferimento moduli servizi |
| `VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md` | Contratto validatore agentic |
| `requirements-agentic-optional.txt` | Dipendenze opzionali |

---

#### `tests/` - Test

Test del progetto.

---

#### `tools/` - Strumenti

Strumenti utilità.

| File | Descrizione |
|------|-----------|
| `generate_symbol_reference.py` | Genera riferimento simboli |
| `symbol_resolution_assistant.py` | Assistente risoluzione simboli |
| `mechanical_payload_surface_cut.py` | Taglio superficie payload |
| `mechanical_runtime_prune.py` | Potatura runtime |
| `mechanical_services_dedupe.py` | Deduplica servizi |

---

## Porte di Servizio

| Servizio | Porta | Protocollo | File Avvio |
|----------|-------|------------|------------|
| **Reranker** | 3550 | HTTP | `services/codex_bridge/ovms_alternative_reranker.py` |
| **Broker** | 3572 | HTTP | `services/aicarmine_broker/app.py` |
| **Local Agent** | 3579 | HTTP | `services/codex_bridge/agentic_loop_client_mcp_server.py` |
| **Ollama** | 11434 | HTTP | `services/ollama-task-vulkan.ps1` |
| **OpenWebUI** | 8080 | HTTP | `services/openwebui.ps1` |

---

## Avvio Rapido

### 1. Avvia Reranker Server

```powershell
cd services/codex_bridge
python ovms_alternative_reranker.py --port 3550
```

### 2. Avvia Broker

```powershell
$env:AICARMINE_LAB_REPO = "C:\Users\sanit\agentic-tool-loop"
python services\aicarmine_broker\app.py --port 3572
```

### 3. Verifica

```powershell
# Reranker
curl http://127.0.0.1:3550/health

# Broker
curl http://127.0.0.1:3572/health
```

Per la guida completa, vedere [docs/ISOLATED_LAUNCH_GUIDE.md](docs/ISOLATED_LAUNCH_GUIDE.md).

---

## Dipendenze

```powershell
# Installa tutte le dipendenze
pip install sentence-transformers huggingface_hub optimum[openvino]
```

---

## Configurazione

### Variabili Ambiente Principali

| Variabile | Descrizione | Default |
|-----------|-------------|---------|
| `AICARMINE_LAB_REPO` | Repository lab attivo | `c:\Users\sanit\agentic-tool-loop` |
| `AICARMINE_REAL_REPO` | Repository reale/index | `AICARMINE_LAB_REPO` |
| `AICARMINE_BROKER_PORT` | Porta broker | `3572` |
| `AICARMINE_RAG_RERANK_URL` | URL reranker RAG | `http://127.0.0.1:3550/v3/rerank` |

---

## Contratti

| Contratto | File |
|-----------|------|
| Launcher | `docs/launcher_contract.md` |
| Runtime Environment | `docs/runtime_env_contract.md` |
| Start Here | `docs/START_HERE_RUNTIME.md` |
| Agent Global | `AGENTS.md` |
| MCP First | `.clinerules/00-aicarmine-mcp-first.md` |

---

## Statistiche Progetto

- **File totali**: 307+
- **Linee codice**: 15,000+
- **MCP Servers**: 14
- **Porte attive**: 5
- **Modelli**: 1 (BGE-v2-m3, 2.2 GB)