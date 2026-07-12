# AI-Carmine Codex + Ollama Bridge

Questo pacchetto applica ai file presenti nello ZIP una struttura di collegamento per usare Codex App/CLI/IDE con un modello Ollama locale e con i tool già presenti nel tuo stack AI-Carmine.

## Architettura

```text
Codex App / Codex CLI / IDE extension
│
├─ model_provider Responses API
│   └─ http://127.0.0.1:3581/v1
│      └─ aicarmine_codex_ollama_responses_bridge.py
│         └─ http://127.0.0.1:11434/v1/responses  (Ollama)
│
└─ MCP stdio tools
    └─ aicarmine_codex_mcp_server.py
       └─ http://127.0.0.1:3572/vulkan/agent
          └─ aicarmine_vulkan_tool_broker.py
             ├─ repo_capabilities / repo_status / repo_search / repo_read
             ├─ repo_apply_patch / repo_write_file / repo_validate / repo_command
             ├─ vulkan_helper
             ├─ job state dashboard /jobs
             └─ memory/context/state-packet helpers via useful_tools
```

## Cosa riusa dal tuo ZIP

- `aicarmine_vulkan_tool_broker.py`: è già il broker operativo centrale su `3572`. Contiene dispatcher repo, job state, comandi validati, helper composito e routing verso Ollama planner/task.
- `aicarmine_vulkan_bridge_server.py`: resta utile per OpenWebUI/OpenAPI su `3571`, ma per Codex è meglio usare MCP.
- `aicarmine-executor-server.py` e `aicarmine-run-safe-command.ps1`: restano il livello di esecuzione sicura, se integrato dal broker.
- `useful_tools/memory/...`: contiene SQLite memory, state packet e report. Il nuovo MCP server espone `aicarmine_memory_report` e `aicarmine_memory_state_packet`.
- `useful_tools/context/...` e `pointers/...`: vengono inclusi nel bundle per essere disponibili nel path Python e per future estensioni MCP.

## File aggiunti

- `codex_ollama_bridge/aicarmine_codex_mcp_server.py`
- `codex_ollama_bridge/aicarmine_codex_ollama_responses_bridge.py`
- `codex_ollama_bridge/codex.aicarmine-ollama.config.toml`
- `codex_ollama_bridge/start-codex-ollama-bridge.ps1`

## Setup rapido Windows

Da PowerShell:

```powershell
cd <cartella-estratta>\codex_ollama_bridge
.\start-codex-ollama-bridge.ps1 -InstallFiles
```

Lo script:

1. verifica Ollama su `127.0.0.1:11434`;
2. avvisa se il modello `qwen3-coder:30b` non è presente;
3. copia gli adapter in `%USERPROFILE%\AI\services` se usi `-InstallFiles`;
4. avvia il broker `3572` se non è già attivo;
5. avvia il bridge provider `3581`;
6. genera uno snippet in `%USERPROFILE%\.codex\aicarmine-ollama.config.toml`.

Poi unisci quello snippet al file:

```powershell
notepad $env:USERPROFILE\.codex\config.toml
```

Infine:

```powershell
codex
# oppure
codex app
```

## Requisiti

- Ollama avviato su `http://127.0.0.1:11434`.
- Modello locale già scaricato, per esempio:

```powershell
ollama pull qwen3-coder:30b
```

- Codex CLI/App installato.
- Python con `fastapi` e `uvicorn`, già coerente con il tuo stack esistente.

## Contesto e operatività

La continuità di contesto viene gestita su due livelli:

1. **Codex**: mantiene la conversazione e compatta la history secondo `model_context_window` e `model_auto_compact_token_limit`.
2. **AI-Carmine MCP**: espone memory SQLite, state packet, job state e tool repo. Quando serve contesto persistente, chiedi esplicitamente a Codex di usare `aicarmine_memory_state_packet` o `aicarmine_memory_report`.

Il bridge `3581` può emulare `previous_response_id` solo per chiamate **non streaming** se `AICARMINE_CODEX_BRIDGE_STATEFUL=1`. Per Codex in streaming è preferibile usare Ollama con `/v1/responses` nativo.

## Limiti tecnici importanti

- Codex non va collegato simulando solo i comandi shell `ollama ...`. La via pulita è: `model_provider` per inferenza + MCP per tool/context.
- Ollama supporta solo parte dell’API OpenAI. In particolare `/v1/responses` esiste dalle versioni Ollama recenti e la parte stateful `previous_response_id`/`conversation` non è equivalente a OpenAI.
- Le funzioni cloud proprietarie di Codex Web o alcune funzionalità dell’app che richiedono account/sessione OpenAI non vengono “replicate” da Ollama. Il modello locale copre l’inferenza locale; i tool vengono estesi via MCP.
- Per contesto grande devi creare un modello Ollama con `PARAMETER num_ctx ...` in un `Modelfile`; non basta impostarlo nella richiesta API.

## Test manuali

Controlla Ollama:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/version
Invoke-RestMethod http://127.0.0.1:11434/v1/models
```

Controlla il bridge:

```powershell
Invoke-RestMethod http://127.0.0.1:3581/health
Invoke-RestMethod http://127.0.0.1:3581/v1/models
```

Controlla il broker:

```powershell
Invoke-RestMethod http://127.0.0.1:3572/health
Invoke-RestMethod http://127.0.0.1:3572/jobs.json
```

Esempio chiamata Responses:

```powershell
$body = @{ model = "qwen3-coder:30b"; input = "Rispondi OK"; stream = $false } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:3581/v1/responses -ContentType "application/json" -Body $body
```

## Strategia operativa consigliata

Per lavorare su codice con Codex locale:

1. lascia Ollama attivo;
2. lascia aperto `start-codex-ollama-bridge.ps1`;
3. apri Codex nella repo;
4. chiedi prima un audit con `aicarmine_repo_status`, `aicarmine_repo_search`, `aicarmine_repo_read`;
5. usa patch/write/command solo dopo verifica e approvazione.
