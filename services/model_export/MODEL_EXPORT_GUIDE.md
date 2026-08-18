# Model Export - Complete Guide

## Overview

`services\model_export` contains CLI-oriented model export implementation for converting and exporting models across different formats (OpenVINO, ONNX, GGUF, etc.). It is **not part of the 3571/3572 agentic loop**, but launcher/OpenVINO configuration can share the same machine-wide environment.

## Architecture

### Runtime Boundary

- **Type**: CLI-oriented export tool
- **Integration**: Not part of main agentic loop; operates as a standalone export pipeline
- **Environment**: Uses separate venvs from runtime services (`venvs/openvino`, `venvs/labtools`)
- **Output**: Generates model directories and serving config files

### Component Map

| File | Owner | Description |
| --- | --- | --- |
| `__init__.py` | Package marker | Defines package namespace for export implementation |
| `cli.py` | Main CLI | Defines arguments, exporters for text generation, embeddings, rerank, TTS, STT, image generation, tokenizer export and serving config updates. Owns most implementation detail. |
| `config.py` | Compatibility surface | Config/parser helpers that still live in cli.py. Maintains stable imports for legacy callers. |
| `exporters.py` | Lazy compatibility layer | Exports historical exporter function names; imports actual functions from cli.py on demand to avoid import-time dependency cost. |

## Operational Rules

### 1. Export Dependencies Isolation

- OpenVINO/Python dependencies may differ from `venvs/labtools` and `venvs/openwebui`
- Do not solve service runtime import bugs by changing model export env unless evidence points there
- Keep export dependencies and runtime service venvs separate

### 2. Output Path Management

- Export output paths can modify model directories and serving config files
- Verify target path before executing to avoid unintended side effects
- Generated configs may affect OpenVINO serving endpoints; review changes carefully

### 3. Lazy Compatibility Pattern

- `exporters.py` imports from `cli.py` on demand (lazy loading)
- Historical function names are preserved for backward compatibility
- New code should import from `cli.py`; legacy callers use `exporters.py` wrapper

## Safe Edit Checklist

1. Identify the exact exporter branch used by the requested model family
2. Verify parser arguments and generated paths before modifying output logic
3. Keep lazy compatibility exports intact (`exporters.py`)
4. Run syntax checks on `services\model_export` after edits

### Pre-Export Verification

```powershell
# Check available exporters
python services/model_export/cli.py --help

# Verify target model path
Test-Path "path\to\model"

# Review serving config impact
Get-Content "serving_config_path" | Select-String -Pattern "^model"
```

## Troubleshooting

### Common Issues

1. **Dependency Conflict**: If export fails due to missing OpenVINO packages, verify the correct venv is activated:
   ```powershell
   # Check current Python environment
   python -c "import sys; print(sys.executable)"
   
   # Verify OpenVINO installation
   pip show openvino
   ```

2. **Output Path Collision**: If export overwrites unintended files, verify the target directory:
   ```powershell
   # Check what will be overwritten
   Get-ChildItem "target_path" -Recurse | Select-Object -First 10
   ```

3. **Legacy Import Failure**: If `exporters.py` imports fail, ensure cli.py is syntactically valid:
   ```powershell
   python -c "import services.model_export.exporters"
   ```

### Diagnostic Flow

```
Export failure → Verify exporter branch → Check parser args → Validate output paths → Review serving config impact
```

## Safety Boundaries

### What Model Export Does NOT Do

- Is not part of the 3571/3572 agentic loop
- Does not modify runtime service venvs
- Does not execute model inference (only exports)
- Does not affect live broker/planner operations

### What You Should NOT Do

- Do not treat model export as a runtime debugging tool
- Do not use export CLI to fix service import errors
- Do not modify serving configs without verifying target paths first
- Do not assume export output affects running services until explicitly verified