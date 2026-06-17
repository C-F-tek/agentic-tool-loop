# Analisi e risoluzione dei problemi di congruenza nelle richieste all'IA nel job-3f4635af

Questo documento descrive l'analisi approfondita del job `job-3f4635af` che è stato bloccato a causa di problemi di congruenza tra le richieste dell'IA e le risposte del controller. Il job aveva come obiettivo "Analizza il progetto e trova re-factoring potenziali da fare" ed è stato bloccato al step 20 con lo stato `blocked_needs_attention`.

### Problemi Identificati

1. **Violazione del contratto di finalizzazione**: Il planner ha emesso una risposta `final` senza aver completato le letture richieste dal contratto di evidenza
2. **Affermazioni speculative**: Il planner ha fatto affermazioni su duplicazioni di codice senza aver letto i file candidati
3. **Ignoramento delle route degli strumenti pendenti**: Il planner non ha seguito le indicazioni del controller per leggere i file candidati
4. **Mancata verifica delle affermazioni**: Il planner menziona file senza averli letti completamente

### Cause Radice

- Il planner decide di finalizzare prima che il controller abbia validato il contratto
- Il controller rifiuta la final con `planner_cuda_rewrite_required`
- Il loop entra in uno stato di blocco perché il planner non esegue le letture candidate richieste

## [Types]

### EvidenceContractSummary

```python
@dataclass
class EvidenceContractSummary:
    schema: str = "planner_evidence_contract_storage_summary.v1"
    full_contract_not_duplicated_here: bool = True
    evidence_contract_chars: int = 0
    evidence_contract_sha256: str = ""
    coverage_satisfied: bool = False
    minimum_read_coverage: MinimumReadCoverage
    candidate_next_actions: list[Action]
    finalization_contract: FinalizationContract
```

### FinalizationContract

```python
@dataclass
class FinalizationContract:
    final_allowed: bool = False
    reason: str = ""
    planner_may_choose_final: bool = False
    coverage_satisfied: bool = False
    minimum_read_coverage: MinimumReadCoverage
    code_product_required: bool = False
    planner_forced_terminal_block: bool = False
    planner_may_choose_block: bool = False
```

### MinimumReadCoverage

```python
@dataclass
class MinimumReadCoverage:
    required: bool = True
    coverage_satisfied: bool = False
    target_kind: str = "repo_owner_core"
    required_count: int = 2
    covered_count: int = 0
    missing_owner_paths: list[str]
    covered_owner_paths: list[str]
    candidate_owner_paths: list[str]
```

## [Files]

### New Files to be Created

- `implementation_plan.md` - Questo documento di pianificazione

### Existing Files to be Modified

- Nessuno - L'analisi è completa e i problemi sono stati identificati

### Files to be Deleted or Moved

- Nessuno

### Configuration File Updates

- Nessuno - I problemi sono di logica del loop, non di configurazione

## [Functions]

### New Functions

- Nessuna - L'analisi è basata su letture esistenti

### Modified Functions

- Nessuna - L'analisi è basata su letture esistenti

### Removed Functions

- Nessuna - L'analisi è basata su letture esistenti

## [Classes]

### New Classes

- Nessuna - L'analisi è basata su letture esistenti

### Modified Classes

- Nessuna - L'analisi è basata su letture esistenti

### Removed Classes

- Nessuna - L'analisi è basata su letture esistenti

## [Dependencies]

### New Packages

- Nessuno - L'analisi è basata su letture esistenti

### Version Changes

- Nessuno - L'analisi è basata su letture esistenti

### Integration Requirements

- Nessuno - L'analisi è basata su letture esistenti

## [Testing]

### Test File Requirements

- Nessuno - L'analisi è basata su letture esistenti

### Existing Test Modifications

- Nessuno - L'analisi è basata su letture esistenti

### Validation Strategies

- Analisi degli eventi del job tramite `aicarmine_job_artifact_events`
- Lettura del final.json tramite `aicarmine_job_artifact_final`
- Verifica dello stato del job tramite `aicarmine_job_artifact_list_jobs`

## [Implementation Order]

1. **Analisi degli eventi del job**: Lettura completa di `events.ndjson` per tracciare il flusso del loop
2. **Analisi del final.json**: Lettura del file finale per identificare le violazioni del contratto
3. **Identificazione delle violazioni**: Mappatura delle violazioni del contratto di finalizzazione
4. **Documentazione dei problemi**: Creazione di questo documento di pianificazione
5. **Raccomandazioni**: Fornire raccomandazioni per risolvere i problemi di congruenza

---

## Dettagli dei Problemi di Congruenza

### Problema 1: Violazione del Contratto di Finalizzazione

**Sintomo**: Il planner emette `action=final` ma il controller rifiuta con `planner_cuda_rewrite_required`

**Evidenza**:

- Evento step=6: `planner_decision_rejected` con `guard_type=planner_cuda_rewrite_required`
- Violazione: `final_not_allowed_by_evidence_contract:Need root/ranked orientation + baseline markdown/config reads + one meaningful non-infra/code area/read set + 43/10 verified concrete readable reads + semantic owner target coverage 7/2 for analysis/action-plan finalization`

**Causa**: Il planner decide di finalizzare senza aver completato le letture richieste dal contratto

### Problema 2: Affermazioni Speculative

**Sintomo**: Il planner fa affermazioni su duplicazioni di codice senza aver letto i file candidati

**Evidenza**:

- Violazione: `speculative_claims_without_verification`
- Violazione: `repo_analysis_final_mentions_unverified_paths:application/planner/validator.py,application/evidence/final_quality.py,application/planner/loop.py,application/controller/memory.py`

**Causa**: Il planner fa affermazioni su file che non ha letto completamente o che non sono stati verificati

### Problema 3: Ignoramento delle Route degli Strumenti Pendenti

**Sintomo**: Il planner non segue le indicazioni del controller per leggere i file candidati

**Evidenza**:

- Violazione: `ignores_pending_tool_routes`
- `required_next_tool_call` indica di leggere `pack_builder.py`, `text_windows.py`, `tool_contract.py`

**Causa**: Il planner ignora le indicazioni del controller e continua con altre letture non prioritarie

### Problema 4: Mancata Verifica delle Affermazioni

**Sintomo**: Il planner menziona file senza averli letti completamente

**Evidenza**:

- Violazione: `shallow_analysis_of_large_files`
- Il planner menziona duplicazioni tra file che non ha confrontato

**Causa**: Il planner fa affermazioni basate su letture parziali o incomplete

## Raccomandazioni

1. **Rispettare il contratto di finalizzazione**: Il planner deve completare tutte le letture richieste prima di emettere una final answer
2. **Verificare le affermazioni**: Prima di fare affermazioni su duplicazioni, leggere e confrontare i file candidati
3. **Seguire le route degli strumenti pendenti**: Il planner deve seguire le indicazioni del controller per leggere i file candidati
4. **Completare le letture candidate**: Leggere i file indicati in `candidate_next_actions` prima di finalizzare
5. **Documentare le letture**: Tenere traccia di quali file sono stati letti e quali affermazioni sono state verificate

## Stato Attuale del Job

- **Job ID**: job-3f4635af
- **Stato**: blocked_needs_attention
- **Step corrente**: 20
- **Goal**: Analizza il progetto e trova re-factoring potenziali da fare
- **Ultimo evento**: planner_decision_rejected con `planner_cuda_rewrite_required:final`

## File Modificati

Nessun file è stato modificato. L'analisi è stata effettuata tramite letture esistenti degli eventi del job.
