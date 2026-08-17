# OVMS Embedding Service — Guida alla Conversione del Modello

## Problema: Il modello embedding non è in formato OpenVINO IR

### Reranker (Port 3550) — COMPLETATO ✓

I file nel directory sono in **OpenVINO IR** formato:
```
openvino_model.xml     1250458    ← OpenVINO IR XML
openvino_model.bin     570230359  ← OpenVINO IR Binary (570MB)
openvino_tokenizer.xml  29833      ← Tokenizer OpenVINO IR
openvino_tokenizer.bin   5581510  ← Tokenizer OpenVINO IR binary
```

### Embedding (Port 3551) — IN ATTESA

I file nel directory sono in **ONNX** formato:
```
model.onnx           108502     ← ONNX text description
model.onnx.data      133454848  ← ONNX weights (133MB)
pytorch_model.bin    133508397 ← PyTorch weights
```

**OVMS non può leggere il formato ONNX** — serve convertire in OpenVINO IR.

---

## Procedura di Conversione

### Passo 1: Scaricare il modello da Hugging Face (usare hf)

```powershell
# Scaricare il modello (usa hf invece di huggingface-cli)
hf download BAAI/bge-small-en-v1.5 --local-dir C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\BAAI\bge-small-en-v1.5
```

### Passo 2: Convertire da ONNX a OpenVINO IR

```powershell
# Installare il tool mo (Model Optimizer)
pip install --upgrade openvino

# Convertire model.onnx a OpenVINO IR
cd C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\BAAI\bge-small-en-v1.5

mo --input_model=model.onnx --output_dir=. --model_name=bge-embedding
```

Questo crea:
```
bge-embedding.xml    ← OpenVINO IR XML
bge-embedding.bin    ← OpenVINO IR Binary (pesi)
```

### Passo 3: Convertire il tokenizer

```powershell
# Convertire il tokenizer da JSON a OpenVINO IR
mo --input_model=tokenizer.json --output_dir=. --model_name=tokenizer
```

### Passo 4: Rinominare i file convertiti

```powershell
# Rinominare i file convertiti per corrispondere al formato del reranker
Rename-Item -Path "bge-embedding.xml" -NewName "openvino_model.xml"
Rename-Item -Path "bge-embedding.bin" -NewName "openvino_model.bin"
Rename-Item -Path "tokenizer.xml" -NewName "openvino_tokenizer.xml"
Rename-Item -Path "tokenizer.bin" -NewName "openvino_tokenizer.bin"
```

### Passo 5: Verificare i file convertiti

```powershell
# Verificare che i file OpenVINO IR esistano
Get-ChildItem C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\BAAI\bge-small-en-v1.5 -Filter "*.xml"
```

### Passo 6: Avviare OVMS embedding

```powershell
& "C:\Users\sanit\agentic-tool-loop\ovms-runtime\ovms\ovms.exe" `
  --rest_port 3551 `
  --rest_bind_address 127.0.0.1 `
  --config_path "C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\config.json"
```

### Passo 7: Verificare il modello

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:3551/v2/models/BAAI%2Fbge-small-en-v1.5/ready" -TimeoutSec 10
```

---

## Alternative: Download Pre-Converted Model

### Opzione A: Scaricare da Hugging Face (formato OpenVINO IR)

```powershell
# Scaricare il modello già convertito
hf download C-F/bge-small-en-v1.5-openvino --local-dir C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\BAAI\bge-small-en-v1.5
```

### Opzione B: Usare un modello pre-convertito da OpenVINO IR

```powershell
# Scaricare il modello già convertito
hf download C-F/bge-small-en-v1.5-openvino --local-dir C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\BAAI\bge-small-en-v1.5
```

---

## Riepilogo

| Elemento | Reranker (Port 3550) | Embedding (Port 3551) |
|----------|---------------------|----------------------|
| Formato | OpenVINO IR ✓ | ONNX ✗ |
| XML file | openvino_model.xml | (da convertire) |
| BIN file | openvino_model.bin | (da convertire) |
| Tokenizer | openvino_tokenizer.xml | (da convertire) |
| Dimensione | 570MB | 133MB |

**La conversione è necessaria perché OVMS richiede il formato OpenVINO IR (.xml + .bin), non ONNX.**