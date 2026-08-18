# Ollama Embedding Service — Guida Completa

## Panoramica

Questo documento descrive come configurare il servizio di embedding utilizzando **Ollama** sulla porta **11435**. Il servizio è utilizzato dal pipeline RAG per generare embedding densi dalle query e documenti.

---

## Architettura

```
┌──────────────────────────────────────────────────────────────┐
│              Ollama Embedding Server                         │
│              Porta: 11435                                    │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  nomic-embed-text                                     │ │
│  │  Dimensione: 768                                        │ │
│  │  Tipo: FP32                                           │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  REST API: http://127.0.0.1:11435                            │
│  Model endpoint: /api/embed                                  │
└──────────────────────────────────────────────────────────────┘
```

---

## Installazione Modello

### Passo 1: Verifica Installazione Ollama

```powershell
ollama list
```

### Passo 2: Pull del Modello nomic-embed-text

```powershell
ollama pull nomic-embed-text
```

**Dimensione modello:** ~274 MB

### Passo 3: Verifica Installazione

```powershell
ollama list
# Dovrebbe contenere: nomic-embed-text
```

---

## Configurazione Modello (nomic-embed-text)

| Elemento | Valore |
|----------|--------|
| **Modello** | `nomic-embed-text` |
| **Dimensione embedding** | 768 |
| **Tipo dati** | FP32 |
| **Port REST** | 11435 |
| **Bind Address** | 127.0.0.1 |
| **Endpoint API** | `/api/embed` |

---

## Flusso di Installazione: Ollama → nomic-embed-text

### Passo 1: Installazione Ollama (se non presente)

```powershell
# Verifica installazione
ollama --version
```

### Passo 2: Pull del Modello

```powershell
ollama pull nomic-embed-text
```

### Passo 3: Verifica File

```powershell
ollama list
# Dovrebbe contenere: nomic-embed-text
```

### Passo 4: Test Endpoint Embedding

```powershell
$body = @{
    model = "nomic-embed-text"
    input = "Questo è un documento di test per embedding"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:11435/api/embed" `
  -Method Post `
  -Body $body `
  -ContentType "application/json" `
  -TimeoutSec 30
```

---

## Endpoint API Ollama

### Health Check Modello

```powershell
$body = @{
    model = "nomic-embed-text"
    input = ""
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:11435/api/embed" `
  -Method Post `
  -Body $body `
  -ContentType "application/json" `
  -TimeoutSec 10
```

### Inferenza Embedding

```powershell
$body = @{
    model = "nomic-embed-text"
    input = "Questo è un documento di test per embedding"
} | ConvertTo-Json

$result = Invoke-RestMethod -Uri "http://127.0.0.1:11435/api/embed" `
  -Method Post `
  -Body $body `
  -ContentType "application/json" `
  -TimeoutSec 30

# Output: $result.embedding (array di 768 float)
```

---

## Riepilogo Rapido

```powershell
# Comando completo per copiare-incollare
ollama pull nomic-embed-text
```

| Elemento | Valore |
|----------|--------|
| **Modello** | `nomic-embed-text` |
| **Port REST** | 11435 |
| **Bind Address** | 127.0.0.1 |
| **Tipo dati** | FP32 |
| **Dimensione embedding** | 768 |
| **Endpoint API** | `http://127.0.0.1:11435/api/embed` |

---

## Relazione con il Sistema Agentic Loop

Il server Ollama embedding è un componente chiave del pipeline RAG (Retrieval-Augmented Generation):

1. **Query user** → viene convertita in embedding tramite Ollama (porta 11435)
2. **Ricerca semantica** → recupera documenti candidati dal database/index
3. **Ollama reranker** (porta 11434) → riordina i documenti per rilevanza
4. **Risultati rerankati** → passati al LLM per generazione risposta

L'endpoint `/api/embed` di Ollama è chiamato dal modulo RAG per la generazione degli embedding delle query.

---

## Riepilogo Architettura Ollama Suite

```
Port 11434: LLM Inference (Qwen2.5) ← Ollama main
Port 11435: Embedding (nomic-embed-text) ← Ollama embed endpoint