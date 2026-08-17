# OVMS Embedding Service — Guida Completa

## Panoramica

Questo documento descrive come configurare il server **OpenVINO Model Serving (OVMS)** per il servizio di embedding sulla porta **3551**. Il servizio è utilizzato dal pipeline RAG per generare embedding densi dalle query e documenti.

---

## Architettura

```
┌──────────────────────────────────────────────────────────────┐
│              OVMS Embedding Server                           │
│              Porta: 3551                                     │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  BAAI/bge-small-en-v1.5                               │ │
│  │  target_device: "CPU"                                  │ │
│  │  batch_size: 1                                         │ │
│  │  NUM_STREAMS: "AUTO"                                   │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  REST API: http://127.0.0.1:3551                            │
│  Model endpoint: /v2/models/BAAI%2Fbge-small-en-v1.5        │
└──────────────────────────────────────────────────────────────┘
```

---

## Percorsi File (Ambiente Utente sanit)

| Elemento | Percorso |
|----------|----------|
| **ovms.exe** | `C:\Users\sanit\agentic-tool-loop\ovms-runtime\ovms\ovms.exe` |
| **config.json** | `C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\config.json` |
| **graph.pbtxt** | `C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\BAAI\bge-small-en-v1.5\graph.pbtxt` |

---

## Comando di Avvio

### Comando Minimo (Senza Setupvars)

```powershell
& "C:\Users\sanit\agentic-tool-loop\ovms-runtime\ovms\ovms.exe" `
  --rest_port 3551 `
  --rest_bind_address 127.0.0.1 `
  --config_path "C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\config.json"
```

---

## Configurazione Modello (config.json)

```json
{
    "model_config_list": [
        {
            "config": {
                "name": "BAAI/bge-small-en-v1.5",
                "base_path": "C:\\Users\\sanit\\agentic-tool-loop\\services\\launch\\models-ovms-embed\\BAAI\\bge-small-en-v1.5",
                "target_device": "CPU",
                "plugin_config": {
                    "PERFORMANCE_HINT": "LATENCY",
                    "NUM_STREAMS": "AUTO"
                },
                "batch_size": 1
            }
        }
    ]
}
```

### Campi Configurazione

| Campo | Valore | Descrizione |
|-------|--------|-------------|
| `name` | `"BAAI/bge-small-en-v1.5"` | Nome identificativo del modello nell'API OVMS. Usato negli endpoint `/v2/models/...`. |
| `base_path` | percorso assoluto | Directory contenente i weights del modello (file ONNX/OpenVINO IR). |
| `target_device` | `"CPU"` | Dispositivo di destinazione per l'inferenza. "CPU" indica che il modello verrà eseguito sul processore. |
| `plugin_config.PERFORMANCE_HINT` | `"LATENCY"` | Hint di prestazioni OpenVINO: "LATENCY" ottimizza per bassa latenza, "THROUGHPUT" per alto throughput. |
| `plugin_config.NUM_STREAMS` | `"AUTO"` | Numero di stream di inferenza automaticamente adattati alla capacità hardware. |
| `batch_size` | `1` | Dimensione massima del batch per le richieste di embedding. |

---

## Flusso di Conversione: Hugging Face → OpenVINO IR → OVMS

### Passo 1: Download da Hugging Face

```powershell
huggingface-cli download BAAI/bge-small-en-v1.5 --local-dir C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\BAAI\bge-small-en-v1.5
```

### Passo 2: Conversione a ONNX

```powershell
optimum-cli export onnx --model "BAAI/bge-small-en-v1.5" --output C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\BAAI\bge-small-en-v1.5
```

### Passo 3: Conversione a OpenVINO IR

```powershell
mo --input_model C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\BAAI\bge-small-en-v1.5\model.onnx --output_dir C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\BAAI\bge-small-en-v1.5
```

### Passo 4: Verifica File

```powershell
ls C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\BAAI\bge-small-en-v1.5
# Dovrebbe contenere: bge-small-en-v1.5.xml, bge-small-en-v1.5.bin
```

### Passo 5: Avvio OVMS Embedding

```powershell
powershell -File services/launch/ovms-embed.ps1
```

---

## Endpoint API OVMS

### Health Check Modello

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:3551/v2/models/BAAI%2Fbge-small-en-v1.5/ready" -TimeoutSec 10
```

### Inferenza Embedding

```powershell
$body = @{
    texts = @(
        "Questo è un documento di test per embedding"
    )
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://127.0.0.1:3551/v2/models/BAAI%2Fbge-small-en-v1.5/infer" `
  -Method Post `
  -Body $body `
  -ContentType "application/json" `
  -TimeoutSec 30
```

---

## Riepilogo Rapido

```powershell
# Comando completo per copiare-incollare
& "C:\Users\sanit\agentic-tool-loop\ovms-runtime\ovms\ovms.exe" `
  --rest_port 3551 `
  --rest_bind-address 127.0.0.1 `
  --config_path "C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\config.json"
```

| Elemento | Valore |
|----------|--------|
| Executable | `ovms-runtime/ovms/ovms.exe` |
| Porta REST | `3551` |
| Bind Address | `127.0.0.1` |
| Config | `services/launch/models-ovms-embed/config.json` |
| Modello | `BAAI/bge-small-en-v1.5` |
| Device | `CPU` |
| Batch Size | `1` |
| Endpoint Ready | `http://127.0.0.1:3551/v2/models/BAAI%2Fbge-small-en-v1.5/ready` |

---

## Relazione con il Sistema Agentic Loop

Il server OVMS embedding è un componente chiave del pipeline RAG (Retrieval-Augmented Generation):

1. **Query user** → viene convertita in embedding tramite OVMS (porta 3551)
2. **Ricerca semantica** → recupera documenti candidati dal database/index
3. **OVMS reranker** (porta 3550) → riordina i documenti per rilevanza
4. **Risultati rerankati** → passati al LLM per generazione risposta

L'endpoint `/v2/models/BAAI%2Fbge-small-en-v1.5/infer` di OVMS è chiamato dal modulo RAG per la generazione degli embedding delle query.

---

## Riepilogo Architettura OVMS Suite

```
Port 3550: Reranker (BGE) ← RAG MCP Server ✓ COMPLETED
Port 3551: Embedding  (MiniLM/bge-small) ← Waiting for model export
Port 3552: LLM Inference (Qwen2.5/Phi-3) ← Pending
Port 3553: CV Model (YOLOv8/CLIP) ← Pending
Port 3560: Router/Load Balancer ← Pending
Port 3561: Cache Manager ← Pending
Port 3562: Export Pipeline ← Pending