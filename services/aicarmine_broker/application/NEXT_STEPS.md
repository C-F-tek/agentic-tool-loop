# Next Steps - Concrete Action Plan

## Stato attuale

La struttura `application/` è stata creata con codice semplificato e logging chiaro. I test hanno passato con successo.

### File completati:

- `services/aicarmine_broker/application/__init__.py` - Main module
- `services/aicarmine_broker/application/dispatcher.py` - 51 lines, RegistryToolDispatcher
- `services/aicarmine_broker/application/planner/__init__.py` - Submodule
- `services/aicarmine_broker/application/planner/validator.py` - 126 lines
- `services/aicarmine_broker/application/evidence/__init__.py` - Submodule
- `services/aicarmine_broker/application/evidence/builder.py` - 166 lines
- `services/aicarmine_broker/application/shared/__init__.py` - Submodule
- `services/aicarmine_broker/application/shared/diagnostics.py` - Diagnostics helpers
- `services/aicarmine_broker/application/shared/payload_metadata.py` - Metadata helpers
- `services/aicarmine_broker/application/shared/evidence_contract_summary.py` - Contract summaries
- `services/aicarmine_broker/application/shared/history_queries.py` - History queries
- `services/aicarmine_broker/application/shared/history_ledger.py` - History ledger
- `services/aicarmine_broker/application/shared/path_tokens.py` - Path tokens
- `services/aicarmine_broker/application/controller/__init__.py` - Submodule
- `services/aicarmine_broker/application/controller/guards.py` - Guard functions
- `services/aicarmine_broker/application/controller/memory.py` - Memory functions
- `services/aicarmine_broker/application/controller/preseed.py` - Preseed functions
- `services/aicarmine_broker/application/controller/diagnostics.py` - Diagnostics
- `services/aicarmine_broker/application/job/__init__.py` - Submodule
- `services/aicarmine_broker/application/job/lifecycle.py` - Lifecycle management
- `services/aicarmine_broker/application/job/worker.py` - Worker management
- `services/aicarmine_broker/application/job/action_router.py` - Action routing
- `services/aicarmine_broker/application/job/terminal_response.py` - Terminal response
- `services/aicarmine_broker/application/test_ab_flow.py` - Test script (all passed)
- `services/aicarmine_broker/application/AB_FLOW_COMPARISON.md` - Documentation

---

## Concrete Next Steps

### 1. Creare stub modules per i submodules mancanti

I seguenti submodules originali mancano in `application/`:

- `application/public_payload/` - 5 file originali
- `application/job/response_values.py` - 1 file originale
- `application/job/status_response.py` - 1 file originale
- `application/job/wait_response.py` - 1 file originale
- `application/planner/decision_normalizer.py` - 1 file originale
- `application/planner/system_prompt.py` - 1 file originale
- `application/planner/loop.py` - 1 file originale
- `application/planner/turn.py` - 1 file originale
- `application/planner/validation_rejections.py` - 1 file originale
- `application/planner/status.py` - 1 file originale
- `application/prompt/` - 10+ file originali
- `application/code_product/` - 3 file originali
- `application/evidence/` - 8 file originali
- `application/tool_surface/` - 6 file originali
- `application/runtime_debug/` - 1 file originale
- `application/npu_phi/` - 1 file originale
- `application/controller/orientation_lane.py` - 1 file originale
- `application/controller/rag_preseed.py` - 1 file originale

**Azione:** Creare stub modules per ogni submodule mancante con la stessa interfaccia API.

### 2. Aggiornare app.py e altri broker files

I seguenti broker files importano da `application/`:

- `services/aicarmine_broker/app.py` - 76 imports
- `services/aicarmine_broker/agent_entry.py` - 4 imports
- `services/aicarmine_broker/job_store.py` - 5 imports
- `services/aicarmine_broker/planner.py` - 40+ imports
- `services/aicarmine_broker/tool_dispatch.py` - 1 import
- `services/aicarmine_broker/public_wrapper.py` - 1 import

**Azione:** Aggiornare gli imports per puntare ai nuovi stub modules.

### 3. Testare con pytest

- [ ] Creare `services/aicarmine_broker/application/tests/`
- [ ] Scrivere test unitari per ogni modulo
- [ ] Eseguire pytest per verificare che tutto funzioni
- [ ] Confrontare i risultati con i test originali

### 4. Integrazione con il broker esistente

- [ ] Verificare che `application/` sia importabile dal broker
- [ ] Testare l'integrazione con il planner esistente
- [ ] Verificare che i tool calls funzionino correttamente

### 5. Migrazione graduale

- [ ] Abilitare `application/` come opzione nel broker
- [ ] Testare in produzione con un subset di job
- [ ] Monitorare le performance e gli errori
- [ ] Migrare completamente a `application/` se tutto funziona

---

## Checklist per la prossima chat

- [ ] Creare stub modules per i submodules mancanti
- [ ] Aggiornare gli imports in app.py e altri broker files
- [ ] Testare con pytest
- [ ] Integrare con il broker
- [ ] Migrare gradualmente
- [ ] Rimuovere i vecchi moduli