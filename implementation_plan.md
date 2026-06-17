# Implementation Plan

## [Overview]

Fixare tre difetti nella patch S3 di `judge_blocked_job()` in `services/aicarmine_broker/planner.py`: rendere non-bloccante la scrittura dell'artifact e dell'evento, scrivere un envelope dedicato invece di `result` intero, e implementare `terminal_judge_failed`.

## [Types]

Nessun nuovo tipo. Si usano i tipi esistenti:
- `dict[str, Any]` per report e artifact
- `str` per job_id, status, goal
- `list[dict[str, Any]]` per history e artifacts

Envelope per l'artifact:
```python
judge_artifact = {
    "schema": "terminal_judge_artifact.v1",
    "job_id": job_id,
    "root_path": str(root),
    "status": status,
    "report": judge_report,
}
```

## [Files]

- **Modificare**: `services/aicarmine_broker/planner.py`
  - Funzione `judge_blocked_job()` (linee 5476-5545)
  - Aggiungere try/except attorno a `write_json()` e `append_agent_event()`
  - Cambiare `write_json(judge_path, result)` in `write_json(judge_path, judge_artifact)`
  - Implementare `terminal_judge_failed` evento
  - Aggiungere `job_id` e `root_path` all'artifact envelope

- **Nessun nuovo file**: L'implementazione è inline nella funzione esistente.

## [Functions]

- **Modificare**: `judge_blocked_job()` (linee 5476-5545)
  - Aggiungere try/except per rendere non-bloccante
  - Cambiare la scrittura dell'artifact da `result` a `judge_artifact`
  - Implementare emissione di `terminal_judge_failed` evento

## [Classes]

Nessuna classe modificata.

## [Dependencies]

Nessuna dipendenza aggiuntiva. Si usano le funzioni importate esistenti:
- `write_json` da `.job_store`
- `append_agent_event` da `.job_store`

## [Testing]

Nessun test da creare (policy: no smoke tests). La verifica è fatta tramite:
- `aicarmine_repo_validate_diffcheck` per validare il unified diff
- Esecuzione manuale di un job che termina con `blocked_needs_attention` o `max_steps_reached`

## [Implementation Order]

1. Leggere la funzione `judge_blocked_job()` attuale per confermare il contesto
2. Modificare la funzione per:
   - Creare l'envelope `judge_artifact` invece di scrivere `result`
   - Aggiungere try/except attorno a `write_json()` e `append_agent_event()`
   - Implementare `terminal_judge_failed` evento
3. Validare il unified diff con `aicarmine_repo_code_unidiff_validate`
4. Verificare con `aicarmine_repo_code_git_apply_check`
5. Applicare il patch con `aicarmine_repo_code_apply_patch`
6. Verificare che il file modificato abbia la linea corretta