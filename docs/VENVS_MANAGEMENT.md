# Venv Management Guide

Questo documento descrive il sistema di gestione delle virtual environments (venv) del progetto AI-Carmine. Ogni venv mantiene le proprie dipendenze isolate in base allo strumento/scopo per cui è stato creato.

## Panoramica

Il progetto utilizza **5 venv principali**, ciascuno ottimizzato per uno specifico insieme di tool:

| Nome | Scopo | Tool Principali | Python Path |
|------|-------|-----------------|--------------|
| **labtools** | Broker interno, planner, validator | `repo_*`, `planner_*`, `validator_*` | `venvs/labtools/Scripts/python.exe` |
| **codeinterpreter** | Jupyter execution, code analysis | `jupyter_execute`, `code_interpreter` | `venvs/codeinterpreter/Scripts/python.exe` |
| **executor** | Command execution, safe runner | `terminal_run_command_wait`, `repo_command` | `venvs/executor/Scripts/python.exe` |
| **openwebui** | UI dashboard, public API surface | `vulkan_helper`, `openwebui` | `venvs/openwebui/Scripts/python.exe` |
| **openvino** | CPU inference, reranking | `rerank`, `embedding`, `npu` | `venvs/openvino/Scripts/python.exe` |

## Attivazione Dinamica

Per attivare dinamicamente il venv corretto in base allo strumento chiamato, usa lo script PowerShell:

```powershell
.\activate-venv.ps1 -tool <tool_name>
.\activate-venv.ps1 -auto    # Auto-detection from current process
```

### Esempi d'uso

```powershell
# Attiva labtools per broker operations
.\activate-venv.ps1 -tool broker

# Attiva codeinterpreter per analisi codice
.\activate-venv.ps1 -tool codeinterpreter

# Auto-detection basata sul processo corrente
.\activate-venv.ps1 -auto
```

## Mappatura Tool -> Venv

La mappatura completa si trova in [.venvmapping.env](.venvmapping.env):

```ini
# Broker tools -> labtools
repo_read = labtools
repo_search = labtools
repo_tree = labtools
repo_list_files = labtools
repo_apply_patch = labtools
planner_* = labtools
validator_* = labtools

# Code interpreter -> codeinterpreter
jupyter_execute = codeinterpreter
code_interpreter = codeinterpreter

# Executor -> executor
terminal_run_command_wait = executor
repo_command = executor

# OpenWebUI -> openwebui
vulkan_helper = openwebui
openwebui = openwebui

# Inference -> openvino
rerank = openvino
embedding = openvino
npu = openvino
```

## Gestione Dipendenze

Ogni venv mantiene le proprie dipendenze. Usa il corrispondente pip executable:

```powershell
# Installa nel venv corretto
& venvs/labtools/Scripts/pip.exe install <package>
& venvs/codeinterpreter/Scripts/pip.exe install <package>
& venvs/executor/Scripts/pip.exe install <package>
& venvs/openwebui/Scripts/pip.exe install <package>
& venvs/openvino/Scripts/pip.exe install <package>
```

### Pacchetto aicarmine-services

Il pacchetto `aicarmine-services` è installato come editable in tutti i venv tramite `pyproject.toml`:

```toml
[project]
name = "aicarmine-services"
version = "2026.06.01"
dependencies = [
    "fastapi>=0.100.0",
    "uvicorn>=0.22.0",
    "pydantic>=2.0.0",
    ...
]
```

Vedi [services/pyproject.toml](../services/pyproject.toml) per la lista completa delle dipendenze.

**Nota:** Il file `services/pyproject.toml` include anche le configurazioni ruff:
- `line-length = 120`
- `ignore = ["F405", "F811"]` per tollerare star imports e ridefinizioni da wrapper pattern

## Verifica Ambiente

Per verificare quale venv è attivo:

```powershell
& <VENV>/Scripts/python.exe -c "import sys; print(sys.executable)"
```

Oppure usa lo script di attivazione:

```powershell
.\activate-venv.ps1 -auto
```

Output atteso:

```
========================================
Active Venv: labtools
Python: C:\Users\carmi\venvs\labtools\Scripts\python.exe
========================================
```

## Creazione Nuovo Venv

Per aggiungere una nuova venv:

1. Crea la directory `venvs/<nome_venv>`
2. Avvia python -m venv
3. Installa pip: `python -m pip install --upgrade pip`
4. Aggiorna [.venvmapping.env](.venvmapping.env) con i nuovi percorsi
5. Aggiungi gli alias tool nella mappa di `activate-venv.ps1`

## Script di Attivazione

Lo script `activate-venv.ps1` supporta tre modalità:

1. **By Tool**: `-tool <tool_name>` - seleziona venv basato sul tool
2. **By Scope**: `-scope <scope_name>` - seleziona venv basato sullo scopo
3. **Auto**: `-auto` - rileva automaticamente dal processo corrente

### Logica Auto-Detection

Lo script rileva automaticamente il venv corretto esaminando l'esecutibile Python corrente:

- `*codeinterpreter*` → codeinterpreter
- `*executor*` → executor  
- `*openwebui*` → openwebui
- Default → labtools

## File Configurativi

| File | Scopo |
|------|-------|
| `.venvmapping.env` | Mappatura completa venv-to-tool |
| `activate-venv.ps1` | Script PowerShell per attivazione dinamica |
| `services/pyproject.toml` | Definizione pacchetti essenziali condivisi |
| `venvs/*/requirements.txt` | Dipendenze specifiche per venv (opzionale) |

## Best Practices

1. **Non modificare manualmente** i file `.pth` in `site-packages`. Usa sempre `pip install -e .` o `pip install <package>`.

2. **Verifica prima di installare**: controlla che il package sia necessario per lo strumento specifico.

3. **Isolamento**: mantieni le dipendenze separate tra venv diversi. Non condividere pacchetti tra venv non correlati.

4. **Documentazione**: aggiorna [.venvmapping.env](.venvmapping.env) quando crei nuovi tool o scopi.

5. **Cleanup**: rimuovi venv non più usati dopo aver migrato i loro tool ad altri venv.

## Troubleshooting

### Problema: ModuleNotFoundError: No module named 'services'

**Soluzione:** Assicurati che `aicarmine-services` sia installato nel venv corrente:

```powershell
& venvs/labtools/Scripts/pip.exe list | Select-String "aicarmine-services"
```

Se non presente, installalo:

```powershell
& venvs/labtools/Scripts/pip.exe install -e ../services
```

### Problema: Package già installato ma import fallisce

**Soluzione:** Il package potrebbe essere installato in un venv diverso. Attiva il venv corretto prima di usare il tool.

### Problema: PYTHONPATH non impostato correttamente

**Soluzione:** Esegui `.\activate-venv.ps1 -auto` prima di lanciare Python. Questo imposta `PYTHONPATH` al percorso del venv attivo.

### Problema: AttributeError: module 'aicarmine_broker.config.compatibility' has no attribute 'FINAL_QUALITY_ROUTE_TOOLS'

**Causa:** Il simbolo `FINAL_QUALITY_ROUTE_TOOLS` era elencato in `__all__` ma non importato dalla sorgente.

**Soluzione:** La correzione è stata applicata in `services/aicarmine_broker/config/compatibility.py`:
```python
from ..application.evidence.final_quality import _ALLOWED_FINAL_QUALITY_ROUTE_TOOLS as FINAL_QUALITY_ROUTE_TOOLS
```
Se l'errore persiste, riavvia il broker process dopo aver aggiornato il file.

## Vedi Anche

- [README.md](../README.md) - Sezione su venv
- [.venvmapping.env](.venvmapping.env) - Mappatura dettagliata
- [activate-venv.ps1](activate-venv.ps1) - Script di attivazione
- [services/pyproject.toml](../services/pyproject.toml) - Dipendenze condivise
- [REFACTORING_STATUS_CURRENT.md](./REFACTORING_STATUS_CURRENT.md) - Stato attuale refactoring