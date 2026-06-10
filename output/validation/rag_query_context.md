# RAG Context Pack

- Passed: `True`
- Context pack id: `3781383f9f3653b308fa7b570b0dc663`
- Retrieved chunks: `12`
- Total selected chars: `31844`
- DB: `services/codex_bridge/aicarmine_rag.db`
- Provider execution performed: `False`
- Source writes performed: `False`
- Patch application performed: `False`

## Sources

- `AGENTS.md`
- `codex_ollama_bridge_applied/codex_ollama_bridge/APPLIED-MAPPING.md`
- `codex_ollama_bridge_applied/codex_ollama_bridge/README.md`
- `codex_ollama_bridge_applied/openwebui.ps1`
- `project-openwebui-pipelines-controller/README.md`
- `project-openwebui-pipelines-controller/docs/CHAIN_OF_CAUSALITY.md`
- `services/MODULE_TECHNICAL_DESCRIPTIONS.md`
- `services/RUNTIME_SCRIPT_REFERENCE.md`
- `services/aicarmine_broker/README.md`
- `services/aicarmine_broker/planner_core/README.md`
- `services/vulkan_bridge/README.md`
- `services/vulkan_bridge/__init__.py`

## Chunks

### `project-openwebui-pipelines-controller/docs/CHAIN_OF_CAUSALITY.md#0`

- Chunk id: `6fcc1350f2148c49f7384cf1c3a2299d`
- Fused score: `0.028438886647841874`
- Vector rank: `14`
- FTS rank: `7`

```text
# Catena causale della conversione

## Sintomo

La conversione precedente rendeva la Pipeline un forwarder statico.

## Evidenza

Il progetto originale espone `vulkan_bridge/app.py`, che pubblica endpoint OpenWebUI-facing come `/vulkan_helper`, `/helper_for_all`, `/repo_status`, `/repo_search`, `/repo_read`, `/repo_command`.

La funzione `_build_agent_payload()` costruisce il payload per il backend 3572 e dichiara nel contratto:

```text
30B/OpenWebUI -> 3571 public tool ... -> 3572 broker -> 3572 starts the planner loop;
Vulkan/11435 is a repair/helper lane only when needed
```

## Causa

Il componente corretto da preservare e' il bridge 3571, non il helper come logica interna statica e non il broker 3572 chiamato direttamente.

## Fix minimo

Creare una Pipe OpenWebUI che:

1. chiama il modello OpenWebUI per produrre un piano JSON;
2. invia gli step al bridge pubblico `3571/vulkan_helper`;
3. lascia al bridge/broker la pianificazione interna dinamica;
4. richiama il modello OpenWebUI per generare la risposta finale dalle evidenze.

## Verifica

- `py_compile` passa.
- La Pipeline contiene chiamate a `/api/chat/completions` per planner e synth.
- La Pipeline contiene una sola URL operativa esterna configurabile: `VULKAN_BRIDGE_URL` verso `3571/vulkan_helper`.
- Non ci sono chiamate dirette hardcoded a `3572/vulkan/agent`.

```

### `codex_ollama_bridge_applied/codex_ollama_bridge/APPLIED-MAPPING.md#0`

- Chunk id: `3e877ef532cb04dc902d4942784b4970`
- Fused score: `0.02797339593114241`
- Vector rank: `11`
- FTS rank: `12`

```text
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

```

### `project-openwebui-pipelines-controller/README.md#0`

- Chunk id: `eeb18c6d2c9f7df1a9e09572461489df`
- Fused score: `0.027205882352941177`
- Vector rank: `8`
- FTS rank: `20`

```text
# AI-Carmine Vulkan Controller Pipeline

Questa conversione sostituisce il vecchio adapter statico con una Pipeline controller.

## Flusso reale

```text
OpenWebUI chat
  -> Pipeline `AI-Carmine Vulkan Controller`
  -> chiamata modello OpenWebUI `/api/chat/completions` per piano JSON
  -> una o piu' chiamate a `vulkan_bridge` endpoint pubblico `/vulkan_helper`
  -> bridge 3571 inoltra al broker/planner 3572
  -> planner interno decide tool/helper/repo actions
  -> Pipeline richiama il modello OpenWebUI per sintesi finale evidence-bound
```

La Pipeline non chiama direttamente il planner interno 3572 e non bypassa il bridge. Il bridge resta il punto operativo dinamico; la Pipeline aggiunge solo uno strato esterno di pianificazione/sintesi usando il modello OpenWebUI.

## File principale

```text
pipelines/aicarmine_vulkan_controller_pipeline.py
```

## Configurazione Valves principali

| Valve | Default | Significato |
|---|---:|---|
| `OPENWEBUI_BASE_URL` | `http://open-webui:8080` | URL raggiungibile dal container Pipelines verso OpenWebUI |
| `OPENWEBUI_API_KEY` | vuoto | Token Bearer per `/api/chat/completions`, se richiesto |
| `PLANNER_MODEL` | `gpt-oss:latest` | modello OpenWebUI usato per produrre piano strutturato |
| `SYNTH_MODEL` | `gpt-oss:latest` | modello OpenWebUI usato per sintesi finale |
| `VULKAN_BRIDGE_URL` | `http://host.docker.internal:3571/vulkan_helper` | endpoint pubblico 3571, non 3572 diretto |
| `MAX_BRIDGE_CALLS` | `3` | limite step operativi |
| `DEFAULT_APPROVAL_MODE` | `safe_write_lab` | policy default per scritture safe |

## Test discriminanti

### 1. Sintassi Pipeline

```bash
python -m py_compile pipelines/aicarmine_vulkan_controller_pipeline.py
```

### 2. Raggiungibilita' OpenWebUI dal container Pipelines

```bash
curl -sS "$OPENWEBUI_BASE_URL/api/models" \
  -H "Authorization: Bearer $OPENWEBUI_API_KEY" | head
```

### 3. Raggiungibilita' bridge 3571

```bash
curl -sS http://host.docker.internal:3571/health | jq .
```

### 4. Verifica che non venga bypassato il bridge

Nel risultato bridge devono comparire campi simili a:

```text
service=vulkan_bridge
bridge_status=AGENT_RESULT_RETURNED
bridge_agent_url=http://127.0.0.1:3572/vulkan/agent
bridge_contract=30B/OpenWebUI -> 3571 public tool ... -> 3572 broker
```

Se la Pipeline chiama direttamente `3572/vulkan/agent`, la conversione e' sbagliata.

## Differenza rispetto allo zip precedente

Lo zip precedente faceva sostanzialmente:

```text
OpenWebUI -> Pipeline -> vulkan_helper -> risposta
```

Questo zip fa:

```text
OpenWebUI -> Pipeline planner LLM -> bridge dinamico -> planner interno -> Pipeline synth LLM -> risposta
```

Quindi non e' un chatbot proxy: e' un controller multi-step sopra il tuo bridge dinamico.

```

### `services/MODULE_TECHNICAL_DESCRIPTIONS.md#0`

- Chunk id: `5f4c0c12385517701ef812433d9905cd`
- Fused score: `0.02628900949796472`
- Vector rank: `7`
- FTS rank: `28`

```text
<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_START -->
Regole operative non negoziabili:
1. Il contratto non va modificato se non richiesto da Carmine esplicitamente.
2. Il prodotto finale puo' essere arricchito come gia' viene fatto; non cambiare logica senza richiesta esplicita.
3. Non devi presupporre nulla: non e' il tuo compito.
<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_END -->
# Module Technical Descriptions

Updated: 2026-06-01

This file is the detailed per-module technical reference for
`C:\Users\carmi\AI\services`. It complements the higher-level maps:

- `SERVICES_MODULE_TECHNICAL_REFERENCE.md`
- `RUNTIME_SCRIPT_REFERENCE.md`
- package-level `MODULE_REFERENCE.md` files

Generated/runtime areas are intentionally excluded: `.venv`, `openwebui-data`,
`BCKUP`, `__pycache__`, job workspaces and uploads.

## Reading Order For Future Changes

1. `C:\Users\carmi\AI\AGENTS.md`
2. `services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md`
3. `services/SERVICES_MODULE_TECHNICAL_REFERENCE.md`
4. `services/END_TO_END_AGENTIC_FLOW.md`
5. This file
6. Package `MODULE_REFERENCE.md` for the module being edited

## Top-Level Python Modules

### `aicarmine-executor-server.py`

FastAPI service for guarded command execution. It defines request models for
direct command execution and file-backed payload execution, validates bearer
auth when `AICARMINE_EXECUTOR_TOKEN` is set, resolves payload files under the
configured payload root and delegates actual command execution to
`aicarmine-run-safe-command.ps1`.

- Reads: `AI_ROOT`, `AICARMINE_SAFE_COMMAND_RUNNER`,
  `AICARMINE_EXECUTOR_TOKEN`, payload-root env.
- Exposes: `/health`, `/run`, `/payload_health`, `/run_payload_file`.
- Writes: none directly except through the delegated runner command.
- Risk: security boundary. Do not bypass auth, payload-root validation,
  timeout limits or runner delegation.
- Verify: call `/health`, then a harmless `/run` with explicit timeout and repo
  mode.

### `aicarmine-openwebui-serve.py`

OpenWebUI boot wrapper. It normalizes integer/float/bool environment values,
creates required boot secrets/defaults and starts the OpenWebUI application
inside the OpenWebUI venv.

- Reads: OpenWebUI data/cache/secret and keepalive env values.
- Exposes: OpenWebUI ASGI app through the launcher, not AI-Carmine tool routes.
- Writes: environment defaults during boot.
- Risk: must stay in the OpenWebUI venv. Do not start 3571/3572 services from
  this module.
- Verify: confirm process command line uses `venvs\openwebui`.

### `aicarmine_vulkan_bridge_server.py`

Compatibility uvicorn target for the 3571 public bridge. It imports
`vulkan_bridge.app:app` under the historical module name used by launchers and
process-match cleanup.

- Reads: implementation from `vulkan_bridge.app`.
- Exposes: the 3571 FastAPI app.
- Writes: none.
- Risk: import path stability. Do not move behavior here.
- Verify: launcher command line still contains this import target.

### `aicarmine_vulkan_tool_broker.py`

Compatibility uvicorn target for the 3572 broker/runtime. It imports
`aicarmine_broker.app:app` under the historical module name.

- Reads: implementation from `aicarmine_broker.app`.
- Exposes: the 3572 FastAPI app.
- Writes: none.
- Risk: import path stability. Do not move behavior here.
- Verify: launcher command line still contains this import target.

### `aicarmine_codex_mcp_server.py`

Historical wrapper for `codex_bridge.mcp_server`. It keeps existing command
paths working for Codex MCP startup.

- Reads: `codex_bridge.mcp_server`.
- Exposes: MCP stdio server when executed.
- Writes: only what the delegated module writes.
- Risk: should stay a thin wrapper.
- Verify: import/execute path resolves to the package module.

### `aicarmine_codex_ollama_responses_bridge.py`

Historical wrapper for `codex_bridge.ollama_responses_bridge`. It keeps old
startup paths for the Ollama/OpenAI Responses-compatible H
```

### `services/aicarmine_broker/README.md#0`

- Chunk id: `14c2a75e0c054cf29a914e033ae681d7`
- Fused score: `0.02607709750566893`
- Vector rank: `3`
- FTS rank: `38`

```text
# services/aicarmine_broker

`services/aicarmine_broker/` is the internal 3572 broker/runtime. It owns job
lifecycle, planner prompt construction, validator-only gates, internal tool
dispatch, memory context, code-product contracts and job dashboards.

## Initial Reading Index

Start from these documents before changing runtime behavior:

- [AGENTS.md](../../AGENTS.md)
  - Workspace operating rules and non-negotiable runtime contract notes.
- [services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md](../VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md)
  - Core validator/controller contract for the agentic loop.
- [services/END_TO_END_AGENTIC_FLOW.md](../END_TO_END_AGENTIC_FLOW.md)
  - End-to-end flow between OpenWebUI, 3571, 3572, planner, tools, and final payload.
- [services/SERVICES_MODULE_TECHNICAL_REFERENCE.md](../SERVICES_MODULE_TECHNICAL_REFERENCE.md)
  - Service-level technical map and module references.
- [services/MODULE_TECHNICAL_DESCRIPTIONS.md](../MODULE_TECHNICAL_DESCRIPTIONS.md)
  - File-by-file technical descriptions for the `services/` tree.
- [services/CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md](../CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md)
  - Operational limit for Codex when inspecting large OpenWebUI payloads.
- [services/aicarmine_broker/MODULE_REFERENCE.md](MODULE_REFERENCE.md)
  - Broker module reference.
- [services/vulkan_bridge/MODULE_REFERENCE.md](../vulkan_bridge/MODULE_REFERENCE.md)
  - Public bridge module reference.
- [services/codex_bridge/MODULE_REFERENCE.md](../codex_bridge/MODULE_REFERENCE.md)
  - Codex bridge module reference.
- [services/launch/MODULE_REFERENCE.md](../launch/MODULE_REFERENCE.md)
  - Launch-script module reference.
- [services/model_export/MODULE_REFERENCE.md](../model_export/MODULE_REFERENCE.md)
  - Model export module reference.

Core code entry points:

- [services/vulkan_bridge/app.py](../vulkan_bridge/app.py)
  - Public OpenWebUI wrapper surface.
- [services/vulkan_bridge/agentic_v9.py](../vulkan_bridge/agentic_v9.py)
  - Agentic bridge integration surface.
- [services/aicarmine_broker/app.py](app.py)
  - Internal broker application.
- [services/aicarmine_broker/planner.py](planner.py)
  - Planner/controller facade and high-risk loop entry; owner packages live under services/aicarmine_broker/application/.
- [services/aicarmine_broker/repo_tools.py](repo_tools.py)
  - Compatibility facade for repo/tool helpers; concrete implementations live under services/aicarmine_broker/tools/.
- [services/aicarmine_broker/tool_registry.py](tool_registry.py)
  - Internal tool registry.
- [services/aicarmine_broker/tool_dispatch.py](tool_dispatch.py)
  - Compatibility facade for the explicit registry dispatcher in services/aicarmine_broker/application/tool_surface/dispatcher.py.
- [services/aicarmine_broker/job_store.py](job_store.py)
  - Job state and artifact persistence.
- [services/aicarmine_broker/public_wrapper.py](public_wrapper.py)
  - Public result packaging support.
- [services/aicarmine_broker/planner_intrinsic_context.py](planner_intrinsic_context.py)
  - Intrinsic planner context builder.
- [services/aicarmine_broker/code_edit_proposal_contract.py](code_edit_proposal_contract.py)
  - Report-only code edit proposal contract.
- [services/aicarmine_broker/memory_tools.py](memory_tools.py)
  - Runtime memory tool support.

## 
```

### `AGENTS.md#1`

- Chunk id: `4770cee581efc8de6266231ace01fd53`
- Fused score: `0.026008827238335436`
- Vector rank: `44`
- FTS rank: `1`

```text
1. Il contratto non va modificato se non richiesto da Carmine esplicitamente.
2. Il prodotto finale puo' essere arricchito come gia' viene fatto; non cambiare logica senza richiesta esplicita.
3. Non devi presupporre nulla: non e' il tuo compito.
<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_END -->
# AGENTS.md - Operational Notes For This Workspace

## Metodo obbligatorio

Per problemi su servizi, launcher, tool loop, OpenWebUI o log:

1. Separa sintomo, ipotesi, evidenza, causa e fix.
2. Non usare fallback o workaround per nascondere il problema.
3. Prima di proporre patch verifica chi legge, chi scrive, quale processo gira,
   quale file viene caricato e quale comando produce il sintomo.
4. Se un comportamento ricompare, sospetta prima processo vecchio, cache,
   rigenerazione, profilo sbagliato, PATH o venv errata.
5. Ogni ipotesi deve avere un test discriminante.
6. Una soluzione e valida solo con catena: sintomo -> prova -> causa confermata
   -> fix minimo -> verifica.

## Contratto agentic loop

Prima di modificare `services/aicarmine_broker/planner.py`,
`services/vulkan_bridge/app.py` o il launcher dei servizi, leggere:

- `services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md`
- `services/END_TO_END_AGENTIC_FLOW.md`
- `services/SERVICES_MODULE_TECHNICAL_REFERENCE.md`
- Per dettagli modulo per modulo, seguire i link `MODULE_REFERENCE.md`
  indicati nella reference centrale.
- Per una scheda tecnica di ogni singolo file sotto `services`, leggere
  `services/MODULE_TECHNICAL_DESCRIPTIONS.md`.

Punti non negoziabili del contratto corrente:

- 3571 espone a OpenWebUI solo il tool pubblico `vulkan_helper`.
- 3572 esegue il loop interno; il planner decide, il controller valida.
- Il controller non deve sostituire il planner con sequenze hard-coded o
  auto-final nascosti.
- `final` puo passare solo con evidenza verificata: un `repo_read ok=True`
  deve avere contenuto reale (`content`) ricaricabile dallo stesso tool result.
- `content_preview`, path, conteggi o artifact path locali non soddisfano il
  gate di finalizzazione.
- OpenWebUI non puo aprire file locali sotto `C:\Users\...`; quindi 3571 deve
  trasportare i risultati reali dei tool riusciti dentro `tool_context_for_30b`.
- Nel payload pubblico `artifact` significa risultato reale del tool, non path
  locale.
- Stati terminali come `completed`, `max_steps_reached`,
  `blocked_needs_attention` e `failed` devono usare la stessa regola di
  trasporto: `content` compatto e `tool_context_for_30b` JSON pretty-printed
  con soli tool riusciti.
- I path dei tool repo sono relativi al root runtime `AICARMINE_LAB_REPO`, non
  alla cwd della shell Codex. Prima di diagnosticare un rigetto come
  `repo_read_path_not_from_prior_file_evidence`, verificare
  `planner-prompts/step-*-planner-payload.json -> user_payload.lab_repo` e la
  coerenza con `OPEN_TERMINAL_CWD` / `AICARMINE_OPEN_TERMINAL_WORKDIR`.

## Cosa non fare

- Non cambiare modello, ctx, max step, venv o launcher mentre si sta correggendo
  il protocollo 3571/3572, salvo evidenza diretta che il difetto stia li.
- Non reintrodurre `continuation_surface`, `call_protocol`, `call_examples`,
  raw events o diagnostica transport nella superficie OpenWebUI.
- Non usare `final_path`, `reads/*.json`, `tool-results/*.json` o altri path
  locali come sostituto del risultato inline.

```

### `services/vulkan_bridge/README.md#0`

- Chunk id: `d94c79a7c786b8acb0a6548c893a33f9`
- Fused score: `0.024259113558877526`
- Vector rank: `2`
- FTS rank: `63`

```text
# services/vulkan_bridge

`services/vulkan_bridge/` is the public 3571 OpenWebUI-facing bridge. It exposes
the `vulkan_helper` public tool, forwards work to 3572 and returns inline
model-usable terminal evidence.

## Initial Reading Index

Start from these documents before changing runtime behavior:

- [AGENTS.md](../../AGENTS.md)
  - Workspace operating rules and non-negotiable runtime contract notes.
- [services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md](../VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md)
  - Core validator/controller contract for the agentic loop.
- [services/END_TO_END_AGENTIC_FLOW.md](../END_TO_END_AGENTIC_FLOW.md)
  - End-to-end flow between OpenWebUI, 3571, 3572, planner, tools, and final payload.
- [services/SERVICES_MODULE_TECHNICAL_REFERENCE.md](../SERVICES_MODULE_TECHNICAL_REFERENCE.md)
  - Service-level technical map and module references.
- [services/MODULE_TECHNICAL_DESCRIPTIONS.md](../MODULE_TECHNICAL_DESCRIPTIONS.md)
  - File-by-file technical descriptions for the `services/` tree.
- [services/CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md](../CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md)
  - Operational limit for Codex when inspecting large OpenWebUI payloads.
- [services/aicarmine_broker/MODULE_REFERENCE.md](../aicarmine_broker/MODULE_REFERENCE.md)
  - Broker module reference.
- [services/vulkan_bridge/MODULE_REFERENCE.md](MODULE_REFERENCE.md)
  - Public bridge module reference.
- [services/codex_bridge/MODULE_REFERENCE.md](../codex_bridge/MODULE_REFERENCE.md)
  - Codex bridge module reference.
- [services/launch/MODULE_REFERENCE.md](../launch/MODULE_REFERENCE.md)
  - Launch-script module reference.
- [services/model_export/MODULE_REFERENCE.md](../model_export/MODULE_REFERENCE.md)
  - Model export module reference.

Core code entry points:

- [services/vulkan_bridge/app.py](app.py)
  - Public OpenWebUI wrapper surface.
- [services/vulkan_bridge/agentic_v9.py](agentic_v9.py)
  - Agentic bridge integration surface.
- [services/aicarmine_broker/app.py](../aicarmine_broker/app.py)
  - Internal broker application.
- [services/aicarmine_broker/planner.py](../aicarmine_broker/planner.py)
  - Planner/controller facade and high-risk loop entry; owner packages live under services/aicarmine_broker/application/.
- [services/aicarmine_broker/repo_tools.py](../aicarmine_broker/repo_tools.py)
  - Compatibility facade for repo/tool helpers; concrete implementations live under services/aicarmine_broker/tools/.
- [services/aicarmine_broker/tool_registry.py](../aicarmine_broker/tool_registry.py)
  - Internal tool registry.
- [services/aicarmine_broker/tool_dispatch.py](../aicarmine_broker/tool_dispatch.py)
  - Compatibility facade for the explicit registry dispatcher in services/aicarmine_broker/application/tool_surface/dispatcher.py.
- [services/aicarmine_broker/job_store.py](../aicarmine_broker/job_store.py)
  - Job state and artifact persistence.
- [services/aicarmine_broker/public_wrapper.py](../aicarmine_broker/public_wrapper.py)
  - Public result packaging support.
- [services/aicarmine_broker/planner_intrinsic_context.py](../aicarmine_broker/planner_intrinsic_context.py)
  - Intrinsic planner context builder.
- [services/aicarmine_broker/code_edit_proposal_contract.py](../aicarmine_broker/code_edit_proposal_contract.py)
  - Report-only code edit proposal contract.
- [services/aicarmine_broker/memory_tools.py](../aicarmine_broker/memory_tools.py)
  - Runtime memory tool support.

## Current Folder Structure

- [app.py](app.py)
  - Main 3571 FastAPI app, forwarding logic and OpenWebUI response shaping.
- [agentic_v9.py](agentic_v9.py)
  - Compatibility facade for agentic v9 helpers.
- [client.py](client.py)
  - Compatibility facade for client/helper functions.
- [compact.py](compact.py)
  - Compatibility facade for compaction helpers.
- [MODULE_REFERENCE.md](MODULE_REFERENCE.md)
  - Detailed module contract and public result shape.

## 
```

### `codex_ollama_bridge_applied/openwebui.ps1#6`

- Chunk id: `7f1a77906e0c256d3cb97e4bd52bd4b0`
- Fused score: `0.023959827833572454`
- Vector rank: `22`
- FTS rank: `25`

```text
l_broker.py"
    $BridgePy = "C:\Users\carmi\AI\services\aicarmine_vulkan_bridge_server.py"

    if (-not (Test-Path $AgentPy)) {
        throw "Vulkan Agent Python non trovato: $AgentPy"
    }

    if (-not (Test-Path $BridgePy)) {
        throw "Vulkan Bridge Python non trovato: $BridgePy"
    }

    if (-not (Test-OllamaEndpoint "http://127.0.0.1:11435")) {
        throw "AI-Carmine Vulkan Bridge richiede Ollama Task GPU0/Vulkan sano su http://127.0.0.1:11435"
    }

    Start-UvicornServiceIfNeeded `
        -Name "AI-Carmine Vulkan Agent interno" `
        -Port 3572 `
        -Module "aicarmine_vulkan_tool_broker" `
        -HealthCheck { Test-AICarmineVulkanAgent }

    Start-UvicornServiceIfNeeded `
        -Name "AI-Carmine Vulkan Bridge pubblico" `
        -Port 3571 `
        -Module "aicarmine_vulkan_bridge_server" `
        -HealthCheck { Test-AICarmineVulkanBridge }

    Write-Host "AI-Carmine Vulkan Bridge pronto: http://127.0.0.1:3571/openapi.json"
    Write-Host "AI-Carmine Vulkan Agent interno: http://127.0.0.1:3572/health"
}

Start-AICarmineVulkanBridgeStack


# ------------------------------------------------------------------
# OpenVINO/NPU provider opzionale su 3550
# ------------------------------------------------------------------

Start-OpenVINOProviderIfEnabled `
    -Enabled $ENABLE_OPENVINO_PROVIDER `
    -Script $OPENVINO_PROVIDER_SCRIPT `
    -HealthUrl $OPENVINO_PROVIDER_HEALTH_URL `
    -Port ([int]$OPENVINO_PROVIDER_PORT)

Set-Location $AI_ROOT

Write-Host ""
# ------------------------------------------------------------------
# Servizio: AI-Carmine Executor prima di Open WebUI
# ------------------------------------------------------------------

function Test-AICarmineExecutor {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:3560/health" -TimeoutSec 3
        return ($r.ok -eq $true)
    }
    catch {
        return $false
    }
}

function New-AICarmineExecutorWrapper {
    $ExecutorScript = "C:\Users\carmi\AI\services\aicarmine-executor-server.ps1"
    $ExecutorPy = "C:\Users\carmi\AI\services\aicarmine-executor-server.py"
    $SafeRunner = "C:\Users\carmi\AI\services\aicarmine-run-safe-command.ps1"

    if (-not (Test-Path $ExecutorPy)) {
        throw "Executor Python server non trovato: $ExecutorPy"
    }

    if (-not (Test-Path $SafeRunner)) {
        throw "Safe command runner non trovato: $SafeRunner"
    }

    $Content = @'
$ErrorActionPreference = "Stop"

$AI_ROOT = "C:\Users\carmi\AI"
$Python = [Environment]::GetEnvironmentVariable("AICARMINE_EXECUTOR_PYTHON", "User")

if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = "$AI_ROOT\venvs\labtools\Scripts\python.exe"
}

if (-not (Test-Path $Python)) {
    throw "Python executor non trovato: $Python"
}

Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

$env:AICARMINE_SAFE_COMMAND_RUNNER = "C:\Users\carmi\AI\services\aicarmine-run-safe-command.ps1"
$env:AICARMINE_LAB_REPO = "C:\Users\carmi\AI\lab-worktrees\blender-audio-project-lab"
$env:AICARMINE_REAL_REPO = "C:\Users\carmi\ProjectsDir\blender-audio-project"

Set-Location "$AI_ROOT\services"

& $Python -m uvicorn aicarmine-executor-server:app --host 127.0.0.1 --port 3560
'@

    # Speed: non riscrivere il wrapper a ogni avvio se il contenuto e' gia' identico.
    if ((-not (Test-Path $ExecutorScript)) -or ((Get-Content $ExecutorScript -Raw) -ne $Content)) {
        Set-Content -Path $ExecutorScript -Value $Content -Encoding UTF8
    }

    return $ExecutorScript
}

function Start-AICarmineExecutor {
    $ExecutorScript = New-AICarmineExecutorWrapper

    if (Test-AICarmineExecutor) {
        Write-Host "AI-Carmine Executor giÃƒÆ’Ã‚Â  sano su http://127.0.0.1:3560/health"
        return
    }

    $existing = Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -match "aicarmine-executor-server"
        }


```

### `services/aicarmine_broker/planner_core/README.md#0`

- Chunk id: `c19a3fdfb70a4b0f9c6a991513973687`
- Fused score: `0.0237879767291532`
- Vector rank: `5`
- FTS rank: `59`

```text
# services/aicarmine_broker/planner_core

`services/aicarmine_broker/planner_core/` contains support modules for planner
cache handling and strict Ollama JSON transport. It supports the 3572 planner
loop but does not own planner policy or finalization.

## Initial Reading Index

Start from these documents before changing runtime behavior:

- [AGENTS.md](../../../AGENTS.md)
  - Workspace operating rules and non-negotiable runtime contract notes.
- [services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md](../../VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md)
  - Core validator/controller contract for the agentic loop.
- [services/END_TO_END_AGENTIC_FLOW.md](../../END_TO_END_AGENTIC_FLOW.md)
  - End-to-end flow between OpenWebUI, 3571, 3572, planner, tools, and final payload.
- [services/SERVICES_MODULE_TECHNICAL_REFERENCE.md](../../SERVICES_MODULE_TECHNICAL_REFERENCE.md)
  - Service-level technical map and module references.
- [services/MODULE_TECHNICAL_DESCRIPTIONS.md](../../MODULE_TECHNICAL_DESCRIPTIONS.md)
  - File-by-file technical descriptions for the `services/` tree.
- [services/CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md](../../CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md)
  - Operational limit for Codex when inspecting large OpenWebUI payloads.
- [services/aicarmine_broker/MODULE_REFERENCE.md](../MODULE_REFERENCE.md)
  - Broker module reference.
- [services/vulkan_bridge/MODULE_REFERENCE.md](../../vulkan_bridge/MODULE_REFERENCE.md)
  - Public bridge module reference.
- [services/codex_bridge/MODULE_REFERENCE.md](../../codex_bridge/MODULE_REFERENCE.md)
  - Codex bridge module reference.
- [services/launch/MODULE_REFERENCE.md](../../launch/MODULE_REFERENCE.md)
  - Launch-script module reference.
- [services/model_export/MODULE_REFERENCE.md](../../model_export/MODULE_REFERENCE.md)
  - Model export module reference.

Core code entry points:

- [services/vulkan_bridge/app.py](../../vulkan_bridge/app.py)
  - Public OpenWebUI wrapper surface.
- [services/vulkan_bridge/agentic_v9.py](../../vulkan_bridge/agentic_v9.py)
  - Agentic bridge integration surface.
- [services/aicarmine_broker/app.py](../app.py)
  - Internal broker application.
- [services/aicarmine_broker/planner.py](../planner.py)
  - Planner/controller facade and high-risk loop entry; owner packages live under services/aicarmine_broker/application/.
- [services/aicarmine_broker/repo_tools.py](../repo_tools.py)
  - Compatibility facade for repo/tool helpers; concrete implementations live under services/aicarmine_broker/tools/.
- [services/aicarmine_broker/tool_registry.py](../tool_registry.py)
  - Internal tool registry.
- [services/aicarmine_broker/tool_dispatch.py](../tool_dispatch.py)
  - Compatibility facade for the explicit registry dispatcher in services/aicarmine_broker/application/tool_surface/dispatcher.py.
- [services/aicarmine_broker/job_store.py](../job_store.py)
  - Job state and artifact persistence.
- [services/aicarmine_broker/public_wrapper.py](../public_wrapper.py)
  - Public result packaging support.
- [services/aicarmine_broker/planner_intrinsic_context.py](../planner_intrinsic_context.py)
  - Intrinsic planner context builder.
- [services/aicarmine_broker/code_edit_proposal_contract.py](../code_edit_proposal_contract.py)
  - Report-only code edit proposal contract.
- [services/aicarmine_broker/memory_tools.py](../memory_tools.py)
  - Runtime memory tool support.

## Current Folder Structure

- [cache.py](cache.py)
  - Per-job cache helpers for read-only tool results and repair outcomes.
- [json_io.py](json_io.py)
  - Ollama HTTP streaming, stream capture and strict planner JSON parsing.
- [__init__.py](__init__.py)
  - Package marker.

## 
```

### `services/RUNTIME_SCRIPT_REFERENCE.md#0`

- Chunk id: `d070de899ebb09418b8e553a31aff6b9`
- Fused score: `0.023317307692307693`
- Vector rank: `4`
- FTS rank: `70`

```text
<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_START -->
Regole operative non negoziabili:
1. Il contratto non va modificato se non richiesto da Carmine esplicitamente.
2. Il prodotto finale puo' essere arricchito come gia' viene fatto; non cambiare logica senza richiesta esplicita.
3. Non devi presupporre nulla: non e' il tuo compito.
<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_END -->
# Runtime Script Reference

Updated: 2026-06-02

This document covers top-level service scripts under `C:\Users\carmi\AI\services`
that are not package modules. These scripts are entrypoints, compatibility
wrappers, diagnostics or operational helpers.

## Python Entrypoints And Wrappers

| File | Technical description |
| --- | --- |
| `aicarmine_vulkan_bridge_server.py` | Uvicorn import target for the 3571 public bridge. It keeps the historical module path stable while implementation lives in `vulkan_bridge.app`. |
| `aicarmine_vulkan_tool_broker.py` | Uvicorn import target for the 3572 broker/runtime. It keeps the historical module path stable while implementation lives in `aicarmine_broker.app`. |
| `aicarmine-executor-server.py` | FastAPI safe-command executor. It exposes `/health`, `/run`, `/payload_health` and `/run_payload_file`, validates bearer token when configured and calls `aicarmine-run-safe-command.ps1`. |
| `aicarmine-openwebui-serve.py` | OpenWebUI ASGI boot wrapper. It prepares OpenWebUI environment defaults and launches OpenWebUI through the OpenWebUI venv. |
| `aicarmine_codex_mcp_server.py` | Historical entrypoint that delegates to `codex_bridge.mcp_server`. |
| `aicarmine_codex_ollama_responses_bridge.py` | Historical entrypoint that delegates to `codex_bridge.ollama_responses_bridge`. |
| `export_model.py` | Historical CLI entrypoint that delegates to `model_export.cli`. |
| `apply_openwebui_ps1_open_terminal.py` | Text/zip patcher for OpenWebUI PowerShell artifacts so Open Terminal integration replaces the older Jupyter integration where configured. |

## 
```

### `services/vulkan_bridge/__init__.py#0`

- Chunk id: `07112b62ee95bf9877c814bc9345fe4c`
- Fused score: `0.013157894736842105`
- Vector rank: `16`
- FTS rank: ``

```text
"""Internal modules for the AI-Carmine Vulkan bridge service."""


```

### `codex_ollama_bridge_applied/codex_ollama_bridge/README.md#1`

- Chunk id: `40813cf678a5ed13af17c9f45dde389d`
- Fused score: `0.012048192771084338`
- Vector rank: `23`
- FTS rank: ``

```text
ices/aicarmine_broker/code_edit_proposal_contract.py](../../services/aicarmine_broker/code_edit_proposal_contract.py)
  - Report-only code edit proposal contract.
- [services/aicarmine_broker/memory_tools.py](../../services/aicarmine_broker/memory_tools.py)
  - Runtime memory tool support.

## Current Folder Structure

- [README-CODEX-OLLAMA-BRIDGE.md](README-CODEX-OLLAMA-BRIDGE.md)
  - Bridge-specific README.
- [APPLIED-MAPPING.md](APPLIED-MAPPING.md)
  - Applied bridge mapping.
- [aicarmine_codex_mcp_server.py](aicarmine_codex_mcp_server.py)
  - Applied MCP server entrypoint.
- [aicarmine_codex_ollama_responses_bridge.py](aicarmine_codex_ollama_responses_bridge.py)
  - Applied Responses bridge entrypoint.
- [codex.aicarmine-ollama.config.toml](codex.aicarmine-ollama.config.toml)
  - Codex/Ollama bridge config template.
- [start-codex-ollama-bridge.ps1](start-codex-ollama-bridge.ps1)
  - Bridge startup script.

```
