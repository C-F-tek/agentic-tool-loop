# AICarmine Documentation Index

## Come usare questa documentazione

Questa è la **porta d'ingresso** alla documentazione del progetto AICarmine.  
Leggere prima questo file per avere una visione d'insieme, poi espandere le sezioni di interesse.

---

## 1. Architettura del Sistema

### 1.1 Broker Core
- [Broker Module Guide](aicarmine_broker/MODULE_REFERENCE.md) - Riferimento completo del broker
- [Evidence Module Guide](aicarmine_broker/application/evidence/EVIDENCE_MODULE_GUIDE.md) - Evidence collection, contract rules, patterns
- [Planner Module Guide](aicarmine_broker/application/planner/PLANNER_MODULE_GUIDE.md) - Planner loop control, turn management, validation rejection handling

### 1.2 Codex Bridge (MCP Servers)
- [MCP Servers Guide](codex_bridge/MCP_SERVERS_GUIDE.md) - Inventory completo di tutti i MCP servers e protocolli
- [Intelligent Search](codex_bridge/intelligent_search.py) - RAG pipeline con embedding, candidate selection, reranking

### 1.3 Runtime Services
- [NPU Phi Service Guide](npu_phi_service/NPU_PHI_SERVICE_GUIDE.md) - OpenVINO/Phi-3.5 sidecar su porta 3551
- [Model Export Guide](model_export/MODEL_EXPORT_GUIDE.md) - CLI export per OpenVINO, ONNX, GGUF

### 1.4 Agentic Loop Data Query
- [Agentic Loop README](agentic_loop_logc_app/README.md) - RAG data query agent architecture

---

## 2. Quick Reference per Componente

| Componente | File Principale | Porta/Protocollo | Scopo |
| --- | --- | --- | --- |
| Broker | `aicarmine_broker/application/controller/memory.py` | 3571/3572 | Agentic loop principale |
| Evidence | `application/evidence/builder.py` | - | Raccolta evidenze runtime |
| Planner | `application/planner/loop.py` | Ollama:11434 | Loop decisionale |
| MCP Servers | `codex_bridge/mcp_server.py` | stdio | Esposizione tool surface a Cline |
| NPU Phi | `npu_phi_service/app.py` | 3551 | Inference OpenVINO/Phi-3.5 |
| Model Export | `model_export/cli.py` | CLI standalone | Conversione formati modello |
| RAG Data Query | `agentic_loop_logc_app/main.py` | Auto-assegnato | Query database via RAG |

---

## 3. Flusso Operativo Principale

```
Cline → MCP Server (codex_bridge) → Broker (3571/3572) → Planner (Ollama) → Evidence → Tool Surface → Result
```

### 3.1 Evidence Contract
- Le evidenze devono essere **real output** (non solo metadata)
- Builder pattern: `application/evidence/builder.py`
- Final quality judgment: `application/evidence/final_quality.py`

### 3.2 Planner Loop
- Turn management: `application/planner/turn.py`
- Validation rejection handling: `application/planner/validation_rejections.py`
- Lane catalog: `application/planner/lane_catalog.py`

---

## 4. Servizi di Supporto

### 4.1 OVMS (OpenVINO Model Server)
- Reranking: porta 3550 (BAAI/bge-reranker-v2-m3)
- Embedding: porta 3551 (sentence-transformers/all-MiniLM-L6-v2)
- Script di lancio: `services/launch/ovms-reranker-npu.ps1`

### 4.2 Model Export
- CLI-oriented, non parte del loop agentic
- Lazy compatibility layer: `exporters.py` importa da `cli.py` on-demand
- Output: model directories + serving config files

---

## 5. Troubleshooting Rapido

### Problema: Porta 3571/3572 occupata
```powershell
# Verifica processo su porta 3571/3572
netstat -ano | findstr ":357"
Get-Process -Id <PID> -ErrorAction SilentlyContinue
```

### Problema: NPU Phi sidecar non risponde
```powershell
# Doctor mode read-only
python -m npu_phi_service --doctor --pretty

# Verifica processo su porta 3551
netstat -ano | findstr ":3551"
```

### Problema: Export modello fallito
```powershell
# Verifica venv corretto
python -c "import sys; print(sys.executable)"

# Syntax check su model_export
python -c "import services.model_export.exporters"
```

---

## 6. Safety Boundaries

### Non modificare senza autorizzazione esplicita:
- Broker agentic loop (3571/3572)
- Evidence contract patterns
- Planner turn management
- MCP tool surface routing

### Use diagnostic evidence instead of assumptions:
- Doctor output (`--doctor --pretty`)
- Process ownership verification
- Port ownership verification
- Real sidecar responses

---

## 7. Espandi per Componente

Per approfondire ogni componente, seguire i link nella sezione 1.  
Tutte le guide seguono il formato: **overview → architecture → operational rules → troubleshooting**.