# Guida Completa all'Installazione del Reranker OVMS

Questa guida passo-passo configura il reranker OVMS (OpenVINO Model Server) per il modello BAAI/bge-reranker-v2-m3.

## Panoramica

Il reranker OVMS richiede:
1. **OpenVINO Model Server (OVMS)** - Il server modello
2. **Modello BAAI/bge-reranker-v2-m3** - Convertito per OVMS
3. **File di configurazione** - config.json e setupvars.ps1
4. **Variabili d'ambiente** - Path corretti

---

## Passo 1: Scaricare e Installare OpenVINO Model Server

### Opzione A: Scaricare OVMS Model Server (Consigliato)

```powershell
# 1. Creare la cartella OVMS
$ovmsRoot = "C:\Users\sanit\agentic-tool-loop\ovms-runtime"
New-Item -ItemType Directory -Force -Path $ovmsRoot | Out-Null
New-Item -ItemType Directory -Force -Path "$ovmsRoot\bin" | Out-Null

# 2. Scaricare OpenVINO Model Server
$ovmsUrl = "https://github.com/openvinotoolkit/open_model_server/releases/download/v2024.3.0/ovms-win-2024.3.0.zip"
$ovmsZip = "$env:TEMP\ovms.zip"
Invoke-WebRequest -Uri $ovmsUrl -OutFile $ovmsZip

# 3. Estrarre
Expand-Archive -Path $ovmsZip -DestinationPath "$ovmsRoot\bin" -Force

# 4. Verificare
Test-Path "$ovmsRoot\bin\ovms.exe"
```

### Opzione B: Usare Conda/Pip

```powershell
# Creare ambiente conda
conda create -n ovms python=3.10 -y
conda activate ovms

# Installare OVMS
pip install openvino-model-server

# Verificare
ovms --version
```

---

## Passo 2: Creare il File setupvars.ps1

```powershell
# Creare setupvars.ps1
$setupvarsPath = "C:\Users\sanit\agentic-tool-loop\ovms-runtime\setupvars.ps1"

@'
# OpenVINO Model Server Setup Variables
# This file initializes the OVMS environment

Write-Host "OpenVINO Model Server environment initialized"
Write-Host "OVMS Version: 2024.3.0"

# Set OpenVINO paths if needed
# $env:INTEL_OPENVINO_DIR = "C:\Program Files\Intel\OpenVINO"
# $env:LD_LIBRARY_PATH = "$env:INTEL_OPENVINO_DIR\runtime\lib\intel64;$env:LD_LIBRARY_PATH"
'@ | Set-Content -Path $setupvarsPath -Encoding UTF8

Write-Host "setupvars.ps1 creato in: $setupvarsPath"
Test-Path $setupvarsPath
```

---

## Passo 3: Scaricare e Convertire il Modello BAAI/bge-reranker-v2-m3

### 3.1: Installare gli strumenti di conversione

```powershell
# Installare HuggingFace Hub e Optimum
pip install huggingface_hub optimum[openvino]

# Verificare
python -c "import huggingface_hub; print('HuggingFace Hub:', huggingface_hub.__version__)"
```

### 3.2: Scaricare il modello

```powershell
# Creare cartella modelli
$modelsPath = "C:\Users\sanit\agentic-tool-loop\models-ovms-rerank\models\bge-reranker-v2-m3"
New-Item -ItemType Directory -Force -Path $modelsPath | Out-Null

# Scaricare il modello da HuggingFace
huggingface-cli download BAAI/bge-reranker-v2-m3 --local-dir $modelsPath --exclude "*.onnx" "*.pt" "*.safetensors"

# Verificare
Get-ChildItem $modelsPath -Name
```

### 3.3: Convertire il modello in OpenVINO IR (Intermediate Representation)

```powershell
# Convertire con optimum-cli
$modelsPath = "C:\Users\sanit\agentic-tool-loop\models-ovms-rerank\models\bge-reranker-v2-m3"

optimum-cli export openvino `
  --model BAAI/bge-reranker-v2-m3 `
  --task text-classification `
  --weight-format int8 `
  $modelsPath

# Verificare i file generati
Get-ChildItem $modelsPath -Recurse -Include "*.xml","*.bin" | Select-Object FullName
```

---

## Passo 4: Creare il File config.json

```powershell
# Creare config.json per OVMS
$configPath = "C:\Users\sanit\agentic-tool-loop\models-ovms-rerank\config.json"

$config = @{
    model_config_list = @(
        @{
            name = "bge-reranker-v2-m3"
            base_path = "models\bge-reranker-v2-m3"
            target_device = "GPU.0"
            plugin_config = @{
                PRECISION_HITS_FOR_HALF_PRECISION_MERGE = "YES"
            }
            file_system_layout = "ROOT"
        }
    )
} | ConvertTo-Json -Depth 5

$config | Set-Content -Path $configPath -Encoding UTF8

Write-Host "config.json creato in: $configPath"
Get-Content $configPath
```

### Struttura finale della cartella modelli:

```
models-ovms-rerank/
├── config.json              # Configurazione OVMS
└── models/
    └── bge-reranker-v2-m3/
        ├── config.json       # Config modello OpenVINO
        ├── bge-reranker-v2-m3.xml   # Graph OpenVINO
        ├── bge-reranker-v2-m3.bin   # Weights OpenVINO
        └── ... (altri file modello)
```

---

## Passo 5: Impostare le Variabili d'Ambiente

```powershell
# Impostare variabili d'ambiente per la sessione corrente
$env:OVMS_ROOT = "C:\Users\sanit\agentic-tool-loop\ovms-runtime"
$env:OVMS_EXE = "C:\Users\sanit\agentic-tool-loop\ovms-runtime\bin\ovms.exe"
$env:OVMS_SETUP = "C:\Users\sanit\agentic-tool-loop\ovms-runtime\setupvars.ps1"
$env:OVMS_RERANK_MODELS = "C:\Users\sanit\agentic-tool-loop\models-ovms-rerank"
$env:OPENVINO_PROVIDER_DEVICE = "GPU.0"

# Verificare
Write-Host "OVMS_ROOT: $env:OVMS_ROOT"
Write-Host "OVMS_EXE: $env:OVMS_EXE"
Write-Host "OVMS_SETUP: $env:OVMS_SETUP"
Write-Host "OVMS_RERANK_MODELS: $env:OVMS_RERANK_MODELS"
Write-Host "OPENVINO_PROVIDER_DEVICE: $env:OPENVINO_PROVIDER_DEVICE"

# Verificare che i file esistano
Write-Host "`nVerifica file:"
Write-Host "  ovms.exe: $(Test-Path $env:OVMS_EXE)"
Write-Host "  setupvars.ps1: $(Test-Path $env:OVMS_SETUP)"
Write-Host "  config.json: $(Test-Path "$env:OVMS_RERANK_MODELS\config.json")"
```

### Per rendere persistenti le variabili:

```powershell
# Impostare variabili utente (persistenti)
[Environment]::SetEnvironmentVariable("OVMS_ROOT", "C:\Users\sanit\agentic-tool-loop\ovms-runtime", "User")
[Environment]::SetEnvironmentVariable("OVMS_EXE", "C:\Users\sanit\agentic-tool-loop\ovms-runtime\bin\ovms.exe", "User")
[Environment]::SetEnvironmentVariable("OVMS_SETUP", "C:\Users\sanit\agentic-tool-loop\ovms-runtime\setupvars.ps1", "User")
[Environment]::SetEnvironmentVariable("OVMS_RERANK_MODELS", "C:\Users\sanit\agentic-tool-loop\models-ovms-rerank", "User")
[Environment]::SetEnvironmentVariable("OPENVINO_PROVIDER_DEVICE", "GPU.0", "User")

# Riavviare PowerShell per applicare
```

---

## Passo 6: Avviare il Reranker OVMS

### Opzione A: Usare lo script PowerShell

```powershell
# Dalla root del repository
cd C:\Users\sanit\agentic-tool-loop

# Impostare le variabili
$env:OVMS_ROOT = "C:\Users\sanit\agentic-tool-loop\ovms-runtime"
$env:OVMS_EXE = "C:\Users\sanit\agentic-tool-loop\ovms-runtime\bin\ovms.exe"
$env:OVMS_SETUP = "C:\Users\sanit\agentic-tool-loop\ovms-runtime\setupvars.ps1"
$env:OVMS_RERANK_MODELS = "C:\Users\sanit\agentic-tool-loop\models-ovms-rerank"
$env:OPENVINO_PROVIDER_DEVICE = "GPU.0"

# Avviare
& ".\services\ovms-reranker-npu.ps1"
```

### Opzione B: Avviare OVMS direttamente

```powershell
$env:OVMS_ROOT = "C:\Users\sanit\agentic-tool-loop\ovms-runtime"
$env:OVMS_RERANK_MODELS = "C:\Users\sanit\agentic-tool-loop\models-ovms-rerank"

& "$env:OVMS_ROOT\bin\ovms.exe" `
  --rest_port 3550 `
  --rest_bind_address 127.0.0.1 `
  --config_path "$env:OVMS_RERANK_MODELS\config.json"
```

---

## Passo 7: Verificare che il Reranker sia Attivo

```powershell
# Controllare la porta 3550
netstat -ano | findstr "3550"

# Test health endpoint
curl http://127.0.0.1:3550/v2/models/bge-reranker-v2-m3/ready

# Test functional endpoint
$body = @{
    query = "test query"
    documents = @("test document 1", "test document 2")
    top_k = 2
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:3550/v3/rerank" -Method Post -Body $body -ContentType "application/json"
```

---

## Risoluzione Problemi

### Errore: "OVMS setupvars non trovato"

**Soluzione**: Verificare che `setupvars.ps1` esista:
```powershell
Test-Path "C:\Users\sanit\agentic-tool-loop\ovms-runtime\setupvars.ps1"
```

### Errore: "OVMS exe non trovato"

**Soluzione**: Scaricare OVMS come descritto nel Passo 1.

### Errore: "config non trovato"

**Soluzione**: Creare config.json come descritto nel Passo 4.

### Errore: "target_device non configurato"

**Soluzione**: Verificare che config.json contenga `"target_device": "GPU.0"`.

### Errore GPU: "Cannot create Tensor on device GPU"

**Soluzione**: Provare con CPU:
```powershell
$env:OPENVINO_PROVIDER_DEVICE = "CPU"
# Aggiornare config.json con target_device: "CPU"
```

### Il modello non carica

**Soluzione**: Verificare la struttura della cartella:
```
models-ovms-rerank/
├── config.json
└── models/
    └── bge-reranker-v2-m3/
        ├── *.xml
        └── *.bin
```

---

## Riepilogo File da Creare

| File | Path | Descrizione |
|------|------|-------------|
| `setupvars.ps1` | `ovms-runtime\setupvars.ps1` | Script setup OVMS |
| `config.json` | `models-ovms-rerank\config.json` | Configurazione modelli OVMS |
| `ovms.exe` | `ovms-runtime\bin\ovms.exe` | Executable OVMS (da scaricare) |
| Modello IR | `models-ovms-rerank\models\bge-reranker-v2-m3\` | Modello OpenVINO (da convertire) |

## Comandi Rapidi di Verifica

```powershell
# Verifica completa
$checks = @(
    @{Name="OVMS EXE"; Path="C:\Users\sanit\agentic-tool-loop\ovms-runtime\bin\ovms.exe"},
    @{Name="Setupvars"; Path="C:\Users\sanit\agentic-tool-loop\ovms-runtime\setupvars.ps1"},
    @{Name="Config"; Path="C:\Users\sanit\agentic-tool-loop\models-ovms-rerank\config.json"},
    @{Name="Model XML"; Path="C:\Users\sanit\agentic-tool-loop\models-ovms-rerank\models\bge-reranker-v2-m3\bge-reranker-v2-m3.xml"}
)

foreach ($check in $checks) {
    $exists = Test-Path $check.Path
    Write-Host "$($check.Name): $(if($exists){'OK'}else{'MISSING'})"
}