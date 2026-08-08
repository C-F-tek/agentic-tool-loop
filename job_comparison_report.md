# Report Analisi Comparativa Job-6295f3c5 vs Job-b30008e0

## Sintesi Esecutiva

Sono stati analizzati due job AI-Carmine con lo stesso goal: **"Analizza il progetto e trova re-factoring potenziali da fare"**

### Job Targettizzati
| Job ID | Tipo | Stato Finale |
|--------|------|--------------|
| `job-6295f3c5` | Legacy | Bloccato (validator rejection) |
| `job-b30008e0` | Shadow | Bloccato (terminal block) |

---

## Problemi Comuni Identificati

### 1. **Reiezione da Parte del Validator**

Entrambi i job hanno subito reiezioni multiple dal validator finale:

#### Violazioni Rilevate in Entrambi i Job:
- `final_not_allowed_by_evidence_contract` - Final non permesso dal contratto di evidenza
- `evidence_consumed_but_final_too_short` - Evidenza consumata ma final troppo breve
- `repo_analysis_final_missing_concrete_paths` - Mancanza di path concreti verificati
- `speculative_claims_from_shallow_reads` - Affermazioni speculative da letture superficiali
- `unbounded_coverage_limitation` - Limiti di copertura illimitati
- `missing_evidence_depth` - Profondità di evidenza mancante

### 2. **Emissione di Final Senza Verifica Completa**

Entrambi i job hanno emesso finali basati su evidenze incomplete:

#### File Non Verificati Citati nei Finali:
- `.clinerules/hooks/PostToolUse.ps1`
- `.clinerules/hooks/PreCompact.ps1`
- `.clinerules/hooks/PreToolUse.ps1`
- `.clinerules/hooks/TaskStart.ps1`
- `.clinerules/hooks/UserPromptSubmit.ps1`
- File in `codex_ollama_bridge_applied/`

### 3. **Copertura Limitata**

#### Copertura Core Letta:
- **Job-6295f3c5**: 15/18 file core
- **Job-b30008e0**: 7/18 file core (inizialmente), poi 18/18 dopo letture aggiuntive

#### File Core Analizzati in Entrambi:
1. `services/aicarmine_broker/application/planner/loop.py` (3444 linee)
2. `services/aicarmine_broker/application/planner/validator.py` (2223 linee)
3. `services/aicarmine_broker/application/tool_surface/candidate_actions.py` (642 linee)
4. `services/aicarmine_broker/application/evidence/final_quality.py` (1256 linee)
5. `services/aicarmine_broker/application/controller/rag_preseed.py` (2034 linee)
6. `services/aicarmine_broker/application/evidence/builder.py` (2407 linee)
7. `services/aicarmine_broker/application/tool_surface/turn_surface_policy.py` (1048 linee)
8. `services/aicarmine_broker/planner.py` (6068 linee)
9. `services/aicarmine_broker/tools/repo_semantic_search.py` (462 linee)

### 4. **Affermazioni Speculative**

Entrambi i job hanno fatto affermazioni non verificate:

#### Esempi di Affermazioni Problematiche:
- Duplicazione di funzioni `_dict_field`, `_list_field` tra moduli
- Pattern matching duplicati in `final_quality.py`
- Logica di coverage duplicata tra `final_quality.py` e `builder.py`
- Frozenset duplicate (`POST_WRITE_VALIDATION_TOOLS`, `POST_WRITE_TOOL_NAMES`)

### 5. **Mancanza di Entry Point Documentato**

Nessuno dei due job ha documentato correttamente:
- L'entry point del workflow agentic
- Il diagramma concettuale del loop
- La catena di dipendenze tra moduli

---

## Raccomandazioni Corrette

### Per Evitare Questi Problemi:

1. **Verificare Tutti i File Hooks Prima del Final**
   ```powershell
   # Leggere almeno un file hook prima di emettere final
   repo_read ".clinerules/hooks/PostToolUse.ps1"
   ```

2. **Citare Solo Evidenza Verificata**
   - Usare solo nomi di funzioni/variabili esatte dai file letti
   - Evitare affermazioni speculative su file non esaminati

3. **Documentare Entry Point e Workflow**
   - Creare diagramma concettuale del loop agentic
   - Documentare entry point e flussi di controllo

4. **Limitare le Affermazioni ai File Letti**
   - Non citare file non ancora esaminati
   - Specificare chiaramente limiti di copertura

5. **Seguire Richieste del Validator**
   - Rispettare `required_next_progress`
   - Leggere file richiesti prima di finalizzare

---

## Conclusioni

I due job mostrano pattern identici di comportamento problematico:
- Emissione di finali prematuri
- Affermazioni non verificate
- Mancanza di documentazione completa del workflow
- Ignorare richieste del validator

Questi problemi derivano dalla natura speculativa delle analisi effettuate senza verifica completa dell'evidenza disponibile nel repository.