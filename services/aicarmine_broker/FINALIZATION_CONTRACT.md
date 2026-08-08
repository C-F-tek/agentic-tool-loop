# Finalization Contract

Questo documento definisce i contratti richiesti per la finalizzazione di un run agentic loop. Deve essere rispettato prima di produrre action=final.

## Schema

```json
{
  "schema": "finalization_contract.v1",
  "required": true,
  "fields": {
    "coverage_satisfied": {"type": "boolean", "description": "Se la copertura minimum_read_coverage è soddisfatta"},
    "missing_owner_paths": {"type": "array", "items": {"type": "string"}, "description": "Percorsi proprietari mancanti da leggere"},
    "covered_owner_paths": {"type": "array", "items": {"type": "string"}, "description": "Percorsi proprietari già letti"},
    "candidate_owner_paths": {"type": "array", "items": {"type": "string"}, "description": "Percorsi candidati da considerare"},
    "entry_points": {"type": "object", "description": "Entry points definiti nel contratto a monte"}
  }
}
```

## Entry Points

Gli entry points **NON devono essere hardcoded** nel codice. Devono essere definiti nel contratto `evidence_contract.entry_points` o estratti da `minimum_read_coverage.covered_owner_paths`.


Questi percorsi vengono verificati contro `verified_content_reads` prima di essere considerati validi. Se mancano, viene generata una violazione `missing_entry_point`.

### Contratto a Monte

Gli entry points devono essere forniti dal contratto del progetto corrente. Non inventare entry points se non presenti nel contratto.

## Minimum Read Coverage

La copertura deve soddisfare questi requisiti:

- `coverage_satisfied=true`: almeno un file concreto nell'area core è stato letto
- `missing_owner_paths=[]`: tutti i percorsi proprietari sono stati coperti
- `covered_owner_paths`: lista dei percorsi effettivamente letti

## Cache RAG Esistente

Il progetto AI **già implementa** un sistema di cache RAG in `planner_core/cache.py`:

- `_tool_cache_key()`: Genera key hash per risultati tool read-only
- `_tool_cache_hit()`: Controlla hit nella history del job
- `_cached_tool_result()`: Restituisce risultato cached
- `CACHEABLE_READ_TOOLS`: Lista tool cacheabili (`repo_capabilities`, `repo_list_files`, ecc.)

Non creare nuovi file di cache RAG - usa l'esistente `planner_core/cache.py`.

## Violazioni

Le seguenti violazioni bloccano la finalizzazione:

- `final_without_minimum_read_coverage`: coverage non soddisfatta
- `missing_entry_point`: entry point richiesto non presente nei verified reads
- `repo_analysis_final_missing_concrete_paths`: insufficiente evidenza concreta
- `repo_analysis_final_speculative_claims_without_evidence`: affermazioni speculative senza evidenza

## Decision Rules

1. Verifica sempre `minimum_read_coverage.coverage_satisfied` prima di finalizzare
2. Usa `contract.get("entry_points")` invece di hardcoded paths
3. Cita solo percorsi presenti in `verified_content_reads`, `successful_repo_read_paths`, o `owner_candidates`
4. Non chiamare tool se non c'è un gap di evidenza nominato
5. Se `coverage_satisfied=false`, scegli `action=block` con `missing_owner_paths`

## Payload Shape

```json
{
  "decision": "accept | reject | continue_required",
  "ok": true,
  "violations": [],
  "required_next_progress": "...",
  "required_next_output_sections": [...],
  "required_next_missing_evidences": [...],
  "required_next_tool_call": null,
  "confidence": 0.95
}
```

## Note Operative

- Gli entry points sono definiti nel contratto, NON hardcoded
- La copertura richiede lettura di almeno un file nell'area core
- I percorsi mancanti devono essere specificati in `missing_owner_paths`
- Usa `planner_core/cache.py` per caching tool results (già implementato)
- Non creare duplicati di cache RAG
- Non usare `runtime_sqlite_memory_search` per scopi generici
