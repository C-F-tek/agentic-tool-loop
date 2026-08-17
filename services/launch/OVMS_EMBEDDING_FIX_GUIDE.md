# Fix OVMS Embedding Mediapipe Error

## Problem

```
Could not find type "type.googleapis.com/mediapipe.EmbedCalculatorOVOptions"
Trying to parse mediapipe graph definition: BAAI/bge-small-en-v1.5 failed
Mediapipe: BAAI/bge-small-en-v1.5 state changed to: LOADING_PRECONDITION_FAILED
```

## Cause

`BAAI/bge-small-en-v1.5` is a sentence-transformers model that uses mediapipe calculator types not supported by OVMS.

## Solution

Use a different embedding model that doesn't have mediapipe dependencies:

### Option 1: Use `sentence-transformers/all-MiniLM-L6-v2` (Recommended)

```powershell
# Remove old model files
Remove-Item -Recurse -Force "C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\BAAI\bge-small-en-v1.5"

# Convert with --library transformers to avoid sentence-transformers mediapipe deps
optimum-cli export openvino `
  --model sentence-transformers/all-MiniLM-L6-v2 `
  --library transformers `
  --weight-format fp16 `
  C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\sentence-transformers\all-MiniLM-L6-v2

# Update config.json to use the new model name
```

### Option 2: Use `BAAI/bge-small-en-v1.5` with transformers library

```powershell
# Try converting with explicit transformers library
optimum-cli export openvino `
  --model BAAI/bge-small-en-v1.5 `
  --library transformers `
  --weight-format fp16 `
  C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\BAAI\bge-small-en-v1.5
```

### Option 3: Use a pre-converted model from Hugging Face

```powershell
# Download a pre-converted OpenVINO model that doesn't use mediapipe
hf download sentence-transformers/all-MiniLM-L6-v2-openvino-intel-dynamic-5 --local-dir C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\sentence-transformers\all-MiniLM-L6-v2
```

## Update Config

After converting, update `config.json`:

```json
{
    "model_config_list": [
        {
            "config": {
                "name": "sentence-transformers/all-MiniLM-L6-v2",
                "base_path": "C:\\Users\\sanit\\agentic-tool-loop\\services\\launch\\models-ovms-embed\\sentence-transformers\\all-MiniLM-L6-v2",
                "target_device": "CPU",
                "plugin_config": {
                    "PERFORMANCE_HINT": "LATENCY",
                    "NUM_STREAMS": "AUTO"
                },
                "batch_size": "32"
            }
        }
    ]
}
```

## Verify

```powershell
# Start OVMS embedding service
& "C:\Users\sanit\agentic-tool-loop\ovms-runtime\ovms\ovms.exe" `
  --rest_port 3551 `
  --rest_bind_address 127.0.0.1 `
  --config_path "C:\Users\sanit\agentic-tool-loop\services\launch\models-ovms-embed\config.json"

# Check if model is ready
Invoke-WebRequest -Uri "http://127.0.0.1:3551/v2/models/sentence-transformers%2Fall-MiniLM-L6-v2/ready" -TimeoutSec 10
```

## Notes

- Always use `--library transformers` instead of `sentence_transformers` to avoid mediapipe dependencies
- The `sentence-transformers/all-MiniLM-L6-v2` model is smaller and faster than BAAI/bge-small-en-v1.5
- Pre-converted OpenVINO models from Hugging Face are available and don't require conversion