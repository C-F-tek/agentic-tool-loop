# OVMS Reranker Server — Guida Completa

## Panoramica

Questo documento descrive come avviare il server **OpenVINO Model Serving (OVMS)** che ospita il modello di reranking `BAAI/bge-reranker-v2-m3`. Il server espone un'API HTTP REST sulla porta **3550** ed è utilizzato dal pipeline agentic per il reranking dei risultati di ricerca semantica (RAG).

---

## Architettura

```
┌──────────────────────────────────────────────────────────────┐
│              OVMS Reranker Server                            │
│              Porta: 3550                                     │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  BAAI/bge-reranker-v2-m3                              │ │
│  │  target_device: "CPU"                                  │ │
│  │  batch_size: 1                                         │ │
│  │  NUM_STREAMS: "AUTO"                                   │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  REST API: http://127.0.0.1:3550                            │
│  Model endpoint: /v2/models/BAAI%2Fbge-reranker-v2-m3       │
└──────────────────────────────────────────────────────────────┘
```

---

## Percorsi File (Ambiente Utente sanit)

| Elemento | Percorso |
|----------|----------|
| **ovms.exe** | `C:\Users\sanit\agentic-tool-loop\ovms-runtime\ovms\ovms.exe` |
| **setupvars.ps1** | `C:\Users\sanit\agentic-tool-loop\ovms-runtime\ovms\setupvars.ps1` |
| **config.json** | `C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-rerank\config.json` |
| **graph.pbtxt** | `C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-rerank\BAAI\bge-reranker-v2-m3\graph.pbtxt` |

> **Nota:** Il file `ovms-reranker-npu.ps1` assume un percorso errato (`bin\ovms.exe`). Nel tuo ambiente, `ovms.exe` si trova nella root di `ovms-runtime/ovms`, non in `bin/`.

---

## Comando di Avvio

### Comando Minimo (Senza Setupvars)

```powershell
& "C:\Users\sanit\agentic-tool-loop\ovms-runtime\ovms\ovms.exe" `
  --rest_port 3550 `
  --rest_bind_address 127.0.0.1 `
  --config_path "C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-rerank\config.json"
```

Questo è il comando più semplice e diretto per avviare il server OVMS con il modello reranker.

---

## Spiegazione Dettagliata dei Parametri

### `--rest_port 3550`

Specifica la porta HTTP su cui OVMS ascolta le richieste REST API. La porta **3550** è riservata al provider OpenVINO per il reranking semantico. Tutte le chiamate all'API del modello (caricamento, inferenza, health check) avvengono su questa porta.

### `--rest_bind_address 127.0.0.1`

Limita l'ascolto solo all'interfaccia localhost. Questo garantisce che il server sia accessibile solo dalla macchina locale, non da rete esterna. È una misura di sicurezza standard per i servizi di inference locali.

### `--config_path "..."`

Percorso assoluto al file `config.json` che contiene la configurazione completa del modello servito. OVMS legge questo file all'avvio e carica il modello specificato.

---

## Configurazione Modello (config.json)

Il file `config.json` definisce come OVMS deve servire il modello:

```json
{
    "model_config_list": [
        {
            "config": {
                "name": "BAAI/bge-reranker-v2-m3",
                "base_path": "C:\\Users\\sanit\\agentic-tool-loop\\services\\launch\\models-ovms-rerank\\BAAI\\bge-reranker-v2-m3",
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
| `name` | `"BAAI/bge-reranker-v2-m3"` | Nome identificativo del modello nell'API OVMS. Usato negli endpoint `/v2/models/...`. |
| `base_path` | percorso assoluto | Directory contenente i weights del modello (file ONNX/OpenVINO IR). |
| `target_device` | `"CPU"` | Dispositivo di destinazione per l'inferenza. "CPU" indica che il modello verrà eseguito sul processore. |
| `plugin_config.PERFORMANCE_HINT` | `"LATENCY"` | Hint di prestazioni OpenVINO: "LATENCY" ottimizza per bassa latenza, "THROUGHPUT" per alto throughput. |
| `plugin_config.NUM_STREAMS` | `"AUTO"` | Numero di stream di inferenza automaticamente adattati alla capacità hardware. |
| `batch_size` | `1` | Dimensione massima del batch per le richieste di reranking. |

---

## Struttura Graph (graph.pbtxt)

Il file `graph.pbtxt` definisce il grafico Mediapipe per il calcolo del reranking:

```protobuf
input_stream: "REQUEST_PAYLOAD:input"
output_stream: "RESPONSE_PAYLOAD:output"
node {
  name: "RerankExecutor"
  input_side_packet: "RERANK_NODE_RESOURCES:rerank_servable"
  calculator: "RerankCalculatorOV"
  input_stream: "REQUEST_PAYLOAD:input"
  output_stream: "RESPONSE_PAYLOAD:output"
  node_options: {
    [type.googleapis.com / mediapipe.RerankCalculatorOVOptions]: {
      models_path: "./",
      plugin_config: '{"NUM_STREAMS": "1" }',
      target_device: "CPU"
    }
  }
}
```

### Elementi Graph

| Elemento | Valore | Descrizione |
|----------|--------|-------------|
| `calculator` | `"RerankCalculatorOV"` | Calcolatore custom OVMS per il reranking, specifico del modello BAAI. |
| `name` | `"RerankExecutor"` | Nome del nodo nel grafico di elaborazione. |
| `input_stream` | `"REQUEST_PAYLOAD:input"` | Stream di input dove arrivano le richieste di reranking (query + documenti). |
| `output_stream` | `"RESPONSE_PAYLOAD:output"` | Stream di output dove arrivano i risultati rerankati (score ordinati). |
| `models_path` | `"./"` | Percorso relativo ai weights del modello rispetto alla directory config. |
| `target_device` | `"CPU"` | Dispositivo target dichiarato nel grafico Mediapipe. Deve corrispondere a `config.json`. |

---

## Endpoint API OVMS

### Health Check Modello

```powershell
# Verifica se il modello è caricato e pronto
Invoke-WebRequest -Uri "http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready" -TimeoutSec 10
```

Risposta **200 OK** = modello caricato correttamente.  
Risposta diversa = errore nel caricamento o modello non pronto.

### Status Modello

```powershell
# Ottieni informazioni sul modello servito
Invoke-RestMethod -Uri "http://127.0.0.1:3550/api/v1/model" -TimeoutSec 10
```

### Inferenza Reranking

La chiamata di inferenza avviene tramite l'endpoint REST standard OVMS (formato specifico del reranker):

```powershell
$body = @{
    query = "domanda da rerankare"
    documents = @(
        @{text = "documento 1"},
        @{text = "documento 2"}
    )
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://127.0.0.1:3550/v3/rerank" `
  -Method Post `
  -Body $body `
  -ContentType "application/json" `
  -TimeoutSec 30
```

---

## Struttura Directory

```
agentic-tool-loop/
├── ovms-runtime/
│   └── ovms/
│       ├── ovms.exe                    # Executable principale OVMS
│       ├── setupvars.ps1               # Script inizializzazione variabili OpenVINO
│       ├── openvino.dll                # Core OpenVINO runtime
│       ├── openvino_intel_cpu_plugin.dll  # Plugin CPU per inferenza
│       └── ... (altri DLL OpenVINO)
│
└── services/
    └── launch/
        └── models-ovms-rerank/
            ├── config.json             # Configurazione modello OVMS
            └── BAAI/
                └── bge-reranker-v2-m3/
                    ├── graph.pbtxt     # Grafico Mediapipe per reranking
                    └── ... (weights ONNX/OpenVINO IR)
```

---

## Dipendenze Runtime

OVMS richiede le seguenti DLL OpenVINO nel suo directory:

| DLL | Descrizione |
|-----|-------------|
| `openvino.dll` | Core runtime OpenVINO |
| `openvino_intel_cpu_plugin.dll` | Plugin CPU per inferenza su processore Intel/AMD |
| `openvino_ir_frontend.dll` | Frontend per formato OpenVINO IR |
| `openvino_onnx_frontend.dll` | Frontend per modelli ONNX |
| `tbb12.dll` | Intel Threading Building Blocks |
| `libcurl-x64.dll` | Libreria HTTP/FTP |
| `opencv_world4130.dll` | OpenCV per preprocessing immagini |

---

## Troubleshooting

### Errore "File non trovato"

Se ricevi un errore che `ovms.exe` non è trovato, verifica il percorso esatto:

```powershell
# Verifica esistenza file
Test-Path "C:\Users\sanit\agentic-tool-loop\ovms-runtime\ovms\ovms.exe"
```

Il file si trova in `ovms/ovms.exe`, **non** in `ovms/bin/ovms.exe`.

### Errore "Autore non attendibile" PowerShell

PowerShell blocca l'esecuzione di script da autori non attenditi. Rispondi con `S` (Esegui sempre) o `V` (Esegui una volta):

```powershell
# Soluzione: imposta ExecutionPolicy per questo session
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Oppure firma lo script come attendibile nel tuo sistema.

### Errore "target_device mismatch"

Se il `target_device` in `graph.pbtxt` non corrisponde a `config.json`, OVMS può fallire nel caricamento. Verifica che entrambi dichiarino `"CPU"` o il dispositivo corretto.

### Porta già occupata

Se la porta 3550 è già in uso, identifica il processo:

```powershell
# Trova PID sulla porta 3550
Get-NetTCPConnection -LocalPort 3550 | Select-Object OwningProcess,State

# Trova nome processo dal PID
Get-Process -Id <PID>
```

---

## Relazione con il Sistema Agentic Loop

Il server OVMS reranker è un componente chiave del pipeline RAG (Retrieval-Augmented Generation):

1. **Query user** → viene convertita in embedding
2. **Ricerca semantica** → recupera documenti candidati dal database/index
3. **OVMS reranker** (porta 3550) → riordina i documenti per rilevanza
4. **Risultati rerankati** → passati al LLM per generazione risposta

L'endpoint `/v3/rerank` di OVMS è chiamato dal modulo RAG per il reranking finale dei risultati di ricerca.

---

## Riepilogo Rapido

```powershell
# Comando completo per copiare-incollare
& "C:\Users\sanit\agentic-tool-loop\ovms-runtime\ovms\ovms.exe" `
  --rest_port 3550 `
  --rest_bind_address 127.0.0.1 `
  --config_path "C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-rerank\config.json"
```

| Elemento | Valore |
|----------|--------|
| Executable | `ovms-runtime/ovms/ovms.exe` |
| Porta REST | `3550` |
| Bind Address | `127.0.0.1` |
| Config | `services/launch/models-ovms-rerank/config.json` |
| Modello | `BAAI/bge-reranker-v2-m3` |
| Device | `CPU` |
| Batch Size | `1` |
| Endpoint Ready | `http://127.0.0.1:3550/v2/models/BAAI%2Fbge-reranker-v2-m3/ready` |