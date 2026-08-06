# Installazione Manuale OVMS Reranker

## 1. Download OVMS (OpenVINO Model Server)

### Download corretto

- **URL:** https://github.com/openvinotoolkit/open_model_server/releases/tag/v2026.2.1
- **Versione:** OpenVINO Model Server 2026.2.1 (rilevata dal tuo download)
- **Cosa cercare:** Cerca nella pagina releases il file ZIP per Windows (`ovms-win` o `windows`)

### Estrazione

Estrai lo ZIP in:
```
C:\Users\sanit\agentic-tool-loop\services\launch\ovms-runtime\bin\ovms.exe
```

### Struttura attesa:
```
services/launch/ovms-runtime/
└── bin/
    └── ovms.exe          # Executable OVMS (da estrarre dallo ZIP scaricato)
```

## 2. Download Modello BAAI/bge-reranker-v2-m3

### Installa le dipendenze:
```powershell
pip install optimum[openvino] huggingface_hub
```

### Download del modello:
```powershell
huggingface-cli download BAAI/bge-reranker-v2-m3 --local-dir C:\Users\sanit\agentic-tool-loop\models-ovms-rerank\models\bge-reranker-v2-m3
```

### Conversione OpenVINO IR:
```powershell
optimum-cli export openvino `
  --model BAAI/bge-reranker-v2-m3 `
  --task text-classification `
  --weight-format int8 `
  C:\Users\sanit\agentic-tool-loop\models-ovms-rerank\models\bge-reranker-v2-m3
```

## 3. Configurazione

### Crea config.json:
```json
{
  "model_config_list": [{
    "name": "bge-reranker-v2-m3",
    "base_path": "models\\bge-reranker-v2-m3",
    "target_device": "GPU.0",
    "plugin_config": {
      "PRECISION_HITS_FOR_HALF_PRECISION_MERGE": "YES"
    },
    "file_system_layout": "ROOT"
  }]
}
```

### Posiziona config.json in:
```
C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-rerank\config.json
```

## 4. Avvio OVMS Reranker

### Comando di avvio:
```powershell
$ovmsExe = "C:\Users\sanit\agentic-tool-loop\services\launch\ovms-runtime\bin\ovms.exe"
$configPath = "C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-rerank\config.json"

Start-Process -FilePath $ovmsExe -ArgumentList "--rest_port 3550", "--rest_bind_address 127.0.0.1", "--config_path $configPath" -WorkingDirectory "C:\Users\sanit\agentic-tool-loop\services\launch\ovms-runtime"

# Verifica
netstat -ano | findstr "3550"
```

## 5. Verifica Finale

### Test del reranker:
```powershell
curl http://127.0.0.1:3550/v1/inference_type/reranking -Method POST -Body '{"model":"bge-reranker-v2-m3","query":"test","documents":["doc1","doc2"]}'
```

## Note

- La versione 2026.2.1 è stata rilasciata il 19 giugno 2025
- Il modello deve essere convertito in formato OpenVINO IR per funzionare con OVMS
- La porta 3550 deve essere libera per il reranker OVMS