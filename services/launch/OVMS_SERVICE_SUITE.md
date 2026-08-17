# OVMS Service Suite - Complete Guide

## Overview

This document covers the complete OVMS (OpenVINO Model Server) service suite for the AICarmine stack.

## Current Services

| Servizio | Porta | Modello | Formato | Stato |
|----------|-------|---------|---------|-------|
| Reranker | 3550 | BAAI/bge-reranker-v2-m3 | OpenVINO IR ✓ | Pronto |
| Embedding | 3551 | BAAI/bge-small-en-v1.5 | OpenVINO IR ✗ | Errore mediapipe |

## Models Needed After Embedding Works

### 1. Embedding Service (Port 3551)

**Model:** `BAAI/bge-small-en-v1.5` or `sentence-transformers/all-MiniLM-L6-v2`

**Procedure:**
```powershell
# Installare optimum-cli
pip install optimum[openvino] huggingface_hub

# Convertire a OpenVINO IR (senza dipendenze mediapipe)
optimum-cli export openvino `
  --model sentence-transformers/all-MiniLM-L6-v2 `
  --library transformers `
  --weight-format fp16 `
  C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\BAAI\all-MiniLM-L6-v2

# Creare config.json per il nuovo modello
# Avviare OVMS embedding
& "C:\Users\sanit\agentic-tool-loop\ovms-runtime\ovms\ovms.exe" `
  --rest_port 3551 `
  --rest_bind_address 127.0.0.1 `
  --config_path <path-to-config.json>
```

### 2. Classification Service (Port 3552)

**Model:** `distilbert-base-uncased-finetune-sst-2` o `BAAI/bge-reranker-v2-m3` per classification

**Procedure:**
```powershell
# Convertire modello di classificazione
optimum-cli export openvino `
  --model distilbert-base-uncased-finetune-sst-2 `
  --library transformers `
  --weight-format fp16 `
  C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-class\distilbert-sst2

# Creare config.json e avviare OVMS classification
```

### 3. Translation Service (Port 3553)

**Model:** `Helsinki-NLP/opus-mt-it-en` o `Helsinki-NLP/opus-mt-en-it`

**Procedure:**
```powershell
# Convertire modello di traduzione
optimum-cli export openvino `
  --model Helsinki-NLP/opus-mt-it-en `
  --library transformers `
  --weight-format fp16 `
  C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-trans\opus-mt-it-en

# Creare config.json e avviare OVMS translation
```

### 4. NER Service (Port 3554)

**Model:** `dslim/bert-base-NER`

**Procedure:**
```powershell
# Convertire modello NER
optimum-cli export openvino `
  --model dslim/bert-base-NER `
  --library transformers `
  --weight-format fp16 `
  C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-ner\dslim-bert-base-NER

# Creare config.json e avviare OVMS NER
```

### 5. Summarization Service (Port 3555)

**Model:** `facebook/pegasus-xnli` o `t5-small`

**Procedure:**
```powershell
# Convertire modello di summarization
optimum-cli export openvino `
  --model facebook/pegasus-xnli `
  --library transformers `
  --weight-format fp16 `
  C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-sum\pegasus-xnli

# Creare config.json e avviare OVMS summarization
```

### 6. Text Generation Service (Port 3556)

**Model:** `gpt2` o `t5-small`

**Procedure:**
```powershell
# Convertire modello di text generation
optimum-cli export openvino `
  --model gpt2 `
  --library transformers `
  --weight-format fp16 `
  C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-gen\gpt2

# Creare config.json e avviare OVMS text generation
```

## Common Commands

### Installare optimum-cli
```powershell
pip install optimum[openvino] huggingface_hub
```

### Convertire Modello a OpenVINO IR
```powershell
optimum-cli export openvino `
  --model <model-name> `
  --library transformers `
  --weight-format fp16 `
  <output-directory>
```

### Avviare OVMS
```powershell
& "C:\Users\sanit\agentic-tool-loop\ovms-runtime\ovms\ovms.exe" `
  --rest_port <port> `
  --rest_bind_address 127.0.0.1 `
  --config_path <path-to-config.json>
```

### Verificare Modello
```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:<port>/v2/models/<model-name>/ready" -TimeoutSec 10
```

## Notes

- Use `--library transformers` instead of `sentence_transformers` to avoid mediapipe dependencies
- Use `--weight-format fp16` for faster inference
- Always verify the converted model before using it in production