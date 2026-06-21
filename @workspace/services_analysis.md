# Analisi del Codice - Implicazioni dal job_comparison_report.md (Aggiornata)

## Executive Summary

Analisi approfondita del codice sorgente nei file `services/aicarmine_broker/` escludendo la cartella `@workspace`, identificando le implicazioni dei blocchi terminali osservati nei job legacy e shadow, inclusi **owner laterali** e **flow secondari** che potrebbero riattivare i problemi.

---

## 1. Pattern Identificati dalle Ricerche MCP

### 1.1 Violazioni Terminal Block (`validator.py`)

**File**: `services/aicarmine_broker/application/planner/validator.py`

**Linee critiche identificate**:

```python
# Linea 104-124: _next_final_rewrite_latch()
def _next_final_rewrite_latch(
    current: str,
    *,
    reject_count: int,
    has_gap_route: bool,
) -> str:
    """Determina lo stato successivo del rewrite latch."""
    current = str(current or "").strip().lower()
    
    # Se già in terminal block, rimane così
    if current == "terminal_block_required":
        return current
    
    # one retry is allowed; on the second final-quality reject, block deterministically.
    if reject_count >= 2:
        return "terminal_block_required"
    
    if current == "required_gap_only":
        if has_gap_route:
            return "required_gap_only"
        return "terminal_block_required"
    
    # first rejection starts rewrite branch and keeps retry path concrete.
    return "rewrite_required"
```

**Implicazione**: Il blocco diventa deterministico dopo **2 reiezioni**. Questo è il meccanismo che ha causato i blocchi in entrambi i jobs.

---

### 1.2 Escalation del Final Rewrite Retry Count (`validator.py`)

**File**: `services/aicarmine_broker/application/planner/validator.py`

**Linee 127-168**:

```python
def _escalate_final_rewrite_retry_count(
    contract: dict[str, Any],
    *,
    has_gap_route: bool,
) -> dict[str, Any]:
    """Escalates the final quality rejection counter and transitions to terminal block."""
    contract = contract if isinstance(contract, dict) else {}
    current_latch = str(contract.get("final_rewrite_latch") or "").strip().lower()
    
    if not current_latch:
        return contract
    
    if current_latch not in {"rewrite_required", "required_gap_only", "terminal_block_required"}:
        return contract
    
    if contract.get("planner_cuda_rewrite_required") is not True:
        return contract
    
    if current_latch == "terminal_block_required":
        contract["planner_may_choose_block"] = True
        return contract
    
    reject_count = int(contract.get("planner_final_quality_reject_count") or 0) + 1
    contract["planner_final_quality_reject_count"] = reject_count
    
    next_latch = _next_final_rewrite_latch(
        current_latch,
        reject_count=reject_count,
        has_gap_route=has_gap_route,
    )
    contract["final_rewrite_latch"] = next_latch
    contract["planner_may_choose_block"] = next_latch == "terminal_block_required"
    
    # Quando latch diventa terminal_block_required:
    final_contract = contract.get("finalization_contract") or {}
    if next_latch == "terminal_block_required":
        final_contract["planner_may_choose_block"] = True
        final_contract["final_allowed"] = False      # <-- CRITICO
        final_contract["planner_may_choose_final"] = False  # <-- CRITICO
        final_contract["reason"] = "planner_cuda_rewrite_required_repeated_retry_block_required"
    
    return contract
```

**Implicazione**: 
- `final_allowed=False` blocca l'emissione di final
- `planner_may_choose_final=False` impedisce al planner di scegliere final
- Questo porta inevitabilmente al blocco terminale

---

### 1.3 Tool Surface Policy Enforcement (`turn_surface_policy.py`)

**File**: `services/aicarmine_broker/application/tool_surface/turn_surface_policy.py`

**Linee 97-282**:

```python
# Linea 97-99: Gestione rewrite_latch_tools
rewrite_latch_tools = self._rewrite_latch_tools(contract)
if rewrite_latch_tools is not None:
    return self._ordered(set(rewrite_latch_tools))

# Linea 191-206: Gestione final_rewrite_latch
rewrite_latch = self._final_rewrite_latch(contract)
if rewrite_latch:
    required = self._get_required_tool_call_for_latch(rewrite_latch)
    if required:
        reason = safe_text(required.get("reason") or progress or "final_rewrite_latch", limit=900)
        action_id = "final_rewrite_latch_required_tool:" + required_tool
        source = safe_text(required.get("source") or "final_rewrite_latch", limit=160)
        
        return {
            "action_id": action_id,
            "source": source,
            "reason": "final_rewrite_latch_required_tool",
            "final_rewrite_latch": rewrite_latch,
            ...
        }
    
    if rewrite_latch == "terminal_block_required":
        final_contract["reason"] = "final_rewrite_latch_terminal_block_required"
        ...
```

**Implicazione**: La policy della tool surface blocca tutti gli strumenti quando `rewrite_latch == "terminal_block_required"`.

---

### 1.4 Missing Workflow/Entry Point Issue (`final_quality.py`)

**File**: `services/aicarmine_broker/application/evidence/final_quality.py`

**Linee 772-785**:

```python
# Generazione violazione missing_core_candidate_paths
violations.append(f"repo_analysis_final_missing_core_candidate_paths:{core_hits}/{min(2, len(core_paths))}")

# Generazione violazione missing_workflow_or_entrypoint
violations.append("repo_analysis_final_missing_workflow_or_entrypoint")
```

**Implicazione**: Questi errori si verificano quando il planner cita file o workflow non letti. È una causa principale dei blocchi.

---

### 1.5 Terminal Block Activation (`validator.py`)

**File**: `services/aicarmine_broker/application/planner/validator.py`

**Linee 1413-1435**:

```python
# Attivazione terminal block
if (final_rewrite_latch == "terminal_block_required" and planner_may_choose_block) or planner_forced_terminal_block:
    violations.append("terminal_block_required_final_disallowed")
    
    contract["final_rewrite_latch"] = "terminal_block_required"
    
    final_contract["reason"] = planner_forced_terminal_block_reason or "terminal_block_required_final_disallowed"
else:
    final_contract["reason"] = "terminal_block_required_final_disallowed"
```

**Implicazione**: Il terminal block viene attivato quando:
1. `final_rewrite_latch == "terminal_block_required"` E `planner_may_choose_block=True`
2. OPPURE `planner_forced_terminal_block=True`

---

## 2. Owner Laterali e Flow Secondari Identificati

### 2.1 Controller Guard Mechanism (`controller/guards.py`)

**File**: `services/aicarmine_broker/application/controller/guards.py`

**Funzione chiave**: `controller_guard_rejection_signature()` (linee 71-91)

```python
def controller_guard_rejection_signature(validation: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Genera firma di rifiuto per controller guard."""
    violations = validation.get("violations") if isinstance(validation.get("violations"), list) else []
    tool = normalize_tool_name(str(decision.get("tool") or ""))
    rejected = {
        k: decision.get(k)
        for k in ("action", "tool", "arguments")
        if decision.get(k) not in (None, "", [], {})
    }
    if tool in SUPPORT_SUBTURN_TOOLS:
        args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
        rejected = {
            "action": str(decision.get("action") or "tool"),
            "tool": tool,
        }
        stable_args = _stable_support_subturn_arguments(tool, args)
        if stable_args:
            rejected["arguments"] = stable_args
    return {
        "violations": [str(v) for v in violations],
        "rejected_decision": rejected,
    }
```

**Flow secondario identificato**:
1. Validator rileva violazioni → aggiunge a `validation["violations"]`
2. Controller chiama `controller_guard_rejection_signature(validation, decision)`
3. Firma generata viene confrontata con firme precedenti
4. Se stessa firma ripetuta → escalation verso terminal block
5. Conto firme ripetute incrementa → trigger additional guards

**Owner laterale**: Il controller guard tiene traccia delle reiezioni e può attivare ulteriori meccanismi di blocco indipendentemente dal validator.

---

### 2.2 Surface Lock Reason (`builder.py`, `turn.py`)

**File**: `services/aicarmine_broker/application/evidence/builder.py` (linea 2250)

```python
contract["surface_lock_reason"] = "planner_cuda_rewrite_required_history_overlay"
```

**File**: `services/aicarmine_broker/application/planner/turn.py` (linea 959)

```python
"surface_lock_reason": (...)
```

**Implicazione**: Lo `surface_lock_reason` indica perché la tool surface è bloccata. Questo è un owner laterale che persiste anche dopo che le violazioni originali sono state risolte.

**Flow secondario**:
1. Violazione iniziale (es. `missing_core_candidate_paths`)
2. Validator imposta `planner_cuda_rewrite_required=True`
3. Builder imposta `surface_lock_reason="planner_cuda_rewrite_required_history_overlay"`
4. Anche se le violazioni vengono risolte, lo surface lock persiste
5. Il blocco termina solo quando `final_rewrite_latch="inactive"`

---

### 2.3 Evidence Overlay Contract (`builder.py`)

**File**: `services/aicarmine_broker/application/evidence/builder.py` (linee 2239-2332)

```python
overlay_latch = str(latest_evidence_contract_overlay.get("final_rewrite_latch") or "").strip()
if overlay_latch:
    contract["final_rewrite_latch"] = overlay_latch

overlay_cuda_required = latest_evidence_contract_overlay.get("planner_cuda_rewrite_required") is True
if overlay_cuda_required:
    contract["planner_cuda_rewrite_required"] = overlay_cuda_required
    contract["surface_lock_reason"] = "planner_cuda_rewrite_required_history_overlay"

overlay_reject_count = latest_evidence_contract_overlay.get("planner_final_quality_reject_count") or 0
if overlay_reject_count >= 2:
    contract["final_rewrite_latch"] = "terminal_block_required"
```

**Implicazione**: L'evidence overlay applica modifiche persistenti al contratto anche senza nuove violazioni. Questo è un flow secondario che mantiene attivo il blocco.

---

### 2.4 Lane Transitions Impliciti

Non ho trovato pattern espliciti per `lane_transition`, ma ho identificato implicitamente:

**Flow di transizione lane**:
1. `legacy` → `planner_cuda_rewrite_required` (quando `planner_cuda_rewrite_required=True`)
2. `planner_cuda_rewrite_required` → `terminal_judge` (quando `terminal_block_required`)
3. `terminal_judge` → blocked (quando `final_allowed=False`)

**Owner laterale**: Le transizioni di lane avvengono attraverso cambiamenti nel contratto, non attraverso funzioni esplicite. Questo rende difficile debuggare il percorso del blocco.

---

### 2.5 Memory Reset Patterns

Ho cercato pattern di reset memory ma non ne ho trovati espliciti. Tuttavia, ho identificato:

**Implicit memory reset**:
- Validazione finale con successo → `_clear_final_terminal_block_state()` (validator.py linea 171-274)
- Resetta `final_rewrite_latch="inactive"`
- Resetta `planner_may_choose_block=False`
- Resetta `planner_may_choose_final=True`

**Implicazione**: L'unico modo per uscire dal terminal block è fornire una risposta finale valida. Non esiste un reset manuale dello stato.

---

### 2.6 State Persistence Issues

**Problema identificato**: Lo stato del contratto persiste tra i turn fino alla validazione finale.

**Evidenza**:
- `contract["final_rewrite_latch"]` persiste finché non viene resettato
- `contract["planner_cuda_rewrite_required"]` rimane True finché non resettato
- `contract["surface_lock_reason"]` persiste come storico

**Flow secondario problematico**:
1. Violazione iniziale → flag impostato
2. Flag persiste anche dopo risoluzione violazione
3. Nuovo job riutilizza flag persistenti
4. Blocco immediato anche senza nuove violazioni

---

## 3. Cause Radice dei Blocchi

### 3.1 Causa Primaria: Terminal Block Lane Activation

**Meccanismo**:
1. Primo rifiuto → `rewrite_required` (permette retry)
2. Secondo rifiuto → `terminal_block_required` (blocco deterministico)
3. Terzo+ rifiuto → Blocco forzato

**Evidenza dai job**:
- LEGACY: 4 finali rifiutati → Blocco
- SHADOW: 4 finali rifiutati → Blocco

### 3.2 Causa Secondaria: Missing Workflow/Entry Point

**Problema**: Il planner cita file senza averli letti prima.

**Violazioni comuni**:
- `missing_core_candidate_paths`
- `missing_workflow_or_entrypoint`

### 3.3 Causa Terziaria: Tool Surface Mismatch

**Problema**: Tool chiamati non nella tool surface corrente.

**Violazioni comuni**:
- `tool_not_in_turn_surface`
- `native_tool_not_in_turn_surface`

### 3.4 Causa Quaternaria: Controller Guard Rejection Loop

**Meccanismo**:
1. Validator genera violazioni
2. Controller crea firma di rifiuto
3. Firma confrontata con storiche
4. Se ripetuta → incremento conto
5. Conto alto → activation additional guards

**Evidenza**: `controller_guard_rejection_signature_count()` conta firme ripetute

### 3.5 Causa Quintaria: Surface Lock Persistence

**Problema**: Lo surface lock reason persiste anche dopo risoluzione violazioni.

**Evidenza**: `surface_lock_reason="planner_cuda_rewrite_required_history_overlay"`

---

## 4. Implicazioni per Modifiche al Codice

### 4.1 Implicazione 1: Early Detection del Terminal Block Risk

**Problema attuale**: Il blocco avviene solo dopo 2 reiezioni.

**Soluzione proposta**: Monitorare `planner_final_quality_reject_count` e alertare quando `>= 1`.

**File da modificare**: `validator.py`

**Modifica suggerita**: Aggiungere logging quando `reject_count >= 1`:

```python
# Dopo linea 144 in validator.py
reject_count = int(contract.get("planner_final_quality_reject_count") or 0) + 1
contract["planner_final_quality_reject_count"] = reject_count

# NUOVO: Logging early warning
if reject_count >= 1:
    import logging
    logging.warning(
        f"Terminal block risk detected: reject_count={reject_count}. "
        f"Ensure entry points are verified before finalizing."
    )
```

### 4.2 Implicazione 2: Verificare Entry Point Prima di Finalizzare

**Problema attuale**: Il planner cita file senza averli letti.

**Soluzione proposta**: Leggere `agent_entry.py` e `app.py` prima di emettere final.

**File da modificare**: `final_quality.py`

**Modifica suggerita**: Aggiungere check entry point nel contratto:

```python
# Prima delle linee 772-785 in final_quality.py
entry_points = [
    "services/aicarmine_broker/agent_entry.py",
    "services/aicarmine_broker/app.py",
]

for ep in entry_points:
    if ep not in evidence_contract.get("read_file_paths", []):
        violations.append(f"missing_entry_point:{ep}")
```

### 4.3 Implicazione 3: Clear Surface Lock After Resolution

**Problema attuale**: Lo surface lock persiste anche dopo risoluzione violazioni.

**Soluzione proposta**: Clear surface lock quando tutte le violazioni sono risolte.

**File da modificare**: `builder.py`

**Modifica suggerita**: Aggiungere clear surface lock logic:

```python
# In builder.py, dopo gestione overlay
def _clear_surface_lock_if_safe(contract, validation):
    """Clear surface lock se tutte le violazioni sono risolte."""
    violations = validation.get("violations") or []
    if not violations:
        # Nessuna violazione → safe to clear lock
        if contract.get("surface_lock_reason"):
            contract["surface_lock_reason"] = None
        if contract.get("final_rewrite_latch") == "terminal_block_required":
            contract["final_rewrite_latch"] = "inactive"
```

### 4.4 Implicazione 4: Reset RAG dopo Riavvio Broker

**Problema attuale**: Dopo riavvio broker, cache RAG potrebbe essere stale.

**Soluzione proposta**: Resetta cache RAG dopo riavvio broker.

**File da modificare**: `env_loader.py`, `models.py`

**Modifica suggerita**: Aggiungere flag per reset RAG:

```python
# In env_loader.py
def load_environment():
    # ... existing code ...
    
    # NUOVO: Reset RAG se broker riavviato
    if AICARMINE_BROKER_RESTARTED:
        reset_rag_cache()
        log.info("RAG cache reset after broker restart")
```

### 4.5 Implicazione 5: Documentare Contratti Finalization

**Problema attuale**: Non è chiaro quali file devono essere letti.

**Soluzione proposta**: Documentare contratti di finalization.

**File da creare**: `services/aicarmine_broker/docs/FINALIZATION_CONTRACT.md`

**Contenuto proposto**:
```markdown
# Contratto di Finalization

## Requisiti Obbligatori

1. **Entry Points**: Leggere almeno uno di:
   - `services/aicarmine_broker/agent_entry.py`
   - `services/aicarmine_broker/app.py`

2. **Core Files**: Leggere almeno 2 di:
   - `services/aicarmine_broker/application/planner/loop.py`
   - `services/aicarmine_broker/application/planner/validator.py`
   - ...

3. **Tool Surface**: Tutti i tool usati devono essere nella current turn surface.

## Violazioni Accettabili

- `missing_core_candidate_paths` → Solo se < 2 hits
- `missing_workflow_or_entrypoint` → Sempre critico
- `tool_not_in_turn_surface` → Critico post-rejection

## Stati Rewrite Latch

- `inactive` → Nessun problema
- `rewrite_required` → Permette retry
- `required_gap_only` → Richiede gap route
- `terminal_block_required` → BLOCCO FORZATO
```

### 4.6 Implicazione 6: Monitorare Controller Guard Count

**Problema attuale**: Il controller guard count non viene monitorato.

**Soluzione proposta**: Alertare quando `controller_guard_count` supera threshold.

**File da modificare**: `planner.py`, `loop.py`

**Modifica suggerita**: Aggiungere monitoring controller guard:

```python
# In loop.py, durante validation
guard_count = controller_guard_count(history, kind="rejection_signature")
if guard_count >= 2:
    logging.error(f"High controller guard count: {guard_count}")
    # Consider escalation o reset
```

---

## 5. Piano di Implementazione

### Fase 1: Early Warning System (Priorità Alta)

**Obiettivo**: Alertare quando `reject_count >= 1`

**File da modificare**:
- `validator.py` (aggiungere logging)
- `turn_surface_policy.py` (aggiornare messaggi)

**Stima tempo**: 2 ore

### Fase 2: Entry Point Verification (Priorità Alta)

**Obiettivo**: Verificare entry point prima di finalizzare

**File da modificare**:
- `final_quality.py` (aggiungere check)
- `builder.py` (priorità file)

**Stima tempo**: 3 ore

### Fase 3: Surface Lock Management (Priorità Alta)

**Obiettivo**: Clear surface lock quando violazioni risolte

**File da modificare**:
- `builder.py` (aggiungere _clear_surface_lock_if_safe)
- `validator.py` (_clear_final_terminal_block_state enhancement)

**Stima tempo**: 2 ore

### Fase 4: Controller Guard Monitoring (Priorità Media)

**Obiettivo**: Monitorare controller guard count

**File da modificare**:
- `planner.py` (aggiungere monitoring)
- `loop.py` (aggiungere alerting)

**Stima tempo**: 2 ore

### Fase 5: RAG Cache Management (Priorità Media)

**Obiettivo**: Gestire stato RAG dopo riavvio broker

**File da modificare**:
- `env_loader.py` (aggiungere flag)
- `models.py` (aggiungere state)

**Stima tempo**: 2 ore

### Fase 6: Documentation (Priorità Bassa)

**Obiettivo**: Documentare contratti di finalization

**File da creare**:
- `FINALIZATION_CONTRACT.md`

**Stima tempo**: 1 ora

---

## 6. Conclusioni

Le modifiche proposte mirano a:

1. **Prevenire blocchi precoci**: Early warning system
2. **Verificare evidenze**: Entry point verification
3. **Gestire surface lock**: Clear lock quando violazioni risolte
4. **Monitorare controller guard**: Alert su high rejection count
5. **Gestire stato RAG**: Cache management dopo riavvio
6. **Documentare contratti**: Chiarezza sui requisiti

Queste modifiche sono basate sulle evidenze osservate nei job legacy e shadow, con focus sulla prevenzione piuttosto che sul recovery.

**Owner laterali identificati**:
- Controller guard rejection loop
- Surface lock persistence
- Evidence overlay implicit modifications
- Lane transitions impliciti
- State persistence issues

**Flow secondari problematici**:
- Persistenza flag anche dopo risoluzione
- Overlay applicazioni senza trigger esplicito
- Transizioni lane implicite attraverso contratto changes

---

*Analisi completata con ricerche MCP su services/aicarmine_broker/*