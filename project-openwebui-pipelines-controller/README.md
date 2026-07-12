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
