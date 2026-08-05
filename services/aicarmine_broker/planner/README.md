# Planner Package

## Structure

```
services/aicarmine_broker/planner/
├── __init__.py          # Esporta tutte le classi pubbliche
├── config.py            # Configurazione del planner
├── prompt_builder.py    # Costruzione dei prompt e budget
├── validator.py         # Validazione delle decisioni
├── replan.py            # Specialisti di riparazione
├── finalizer.py         # Finalizzazione dei job
└── loop.py              # Orchestrazione del loop agentico

services/aicarmine_broker/planner.py  # Coordinatore facade (~56 righe)
```

## Modules

### config.py
Contiene `PlannerConfig` (dataclass frozen) e `get_planner_config()` per caricare la configurazione dal ambiente.

### prompt_builder.py
Contiene `PromptBuilder` per costruire il payload utente e report del budget.

### validator.py
Contiene `PlannerValidator` per validare le decisioni del planner contro l'evidenza.

### replan.py
Contiene `ReplanSpecialist` per operazioni di riparazione e replanning.

### finalizer.py
Contiene `Finalizer` per la finalizzazione dei job agentic.

### loop.py
Contiene `PlannerLoop` per l'orchestrazione del loop agentico multi-step.

## Public API

Le tre funzioni principali esportate da `services/aicarmine_broker/planner.py`:

- `run_agentic_planner_job(job_id)` → Esegue il loop agentico completo
- `planner_decision(job_id, state, step, history)` → Singola decisione del planner
- `finalize_agentic_job(job_id, state, status, final_summary, result)` → Finalizza un job

## Metrics

| Aspect | Before | After | Improvement |
|--------|--------|-------|-------------|
| Lines in planner.py | ~4000+ | 56 | -98.6% |
| Number of modules | 1 | 8 | +700% |
| Functions per module | ~100 | ~2-3 | -97% |
| Circular dependencies | Many | None | ✅ Fixed |
| Testability | Low | High | ✅ Improved |