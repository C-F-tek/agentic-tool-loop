# Analisi MCP Server Connessi - Pro, Contro e Proposte di Miglioramento

## Riepilogo

**25 MCP server** sono connessi alla sessione Cline, organizzati in **7 famiglie** con prefisso `aicarmine_`.

---

## 1. aicarmine-codex-app

**Descrizione**: Server principale con strumenti per bridge, editoria, memoria, validazione e operazioni repository.

### Strumenti principali
- `aicarmine_bridge_health`: Health check senza HTTP call
- `terminal_list_files` / `terminal_search_files`: File listing/search via terminal dispatcher
- `planner_scratchpad_write` / `runtime_sqlite_memory_write`: Memoria scratchpad
- `aicarmine_repo_*`: 20+ strumenti per repository (tree, read, search, apply_patch, validation, ecc.)
- `aicarmine_memory_*`: Operazioni su memoria persistente (search, get, upsert, mark_stale, supersede)

### Pro
- ✅ Superficie strumenti più completa (20+ tool)
- ✅ Copre l'intero ciclo di vita: discovery → analisi → modifica → validazione
- ✅ Strumenti specializzati per validazione (ruff, pyright, pytest, shellcheck, semgrep)
- ✅ Memoria persistente con audit trail
- ✅ Supporto per probe reviewati (contract testing)

### Contro
- ❌ Troppe ridondanze (es. 3 tool per search: `repo_search`, `repo_rg_search`, `repo_fd_files`)
- ❌ Alcuni tool hanno nomi troppo lunghi e complessi
- ❌ Nessuna documentazione inline sui tool
- ❌ `apply_patch` è l'unico tool write esposto ma non ha dry-run obbligatorio

### Proposte di miglioramento
1. **Unificare i tool di search** in un unico `aicarmine_repo_search` con parametro `mode` (rg/fd/ast_grep)
2. **Aggiungere documentazione inline** nei tool description
3. **Rinominare i tool** con prefisso verbale più chiaro: `read_file`, `write_file`, `search_code`, ecc.
4. **Aggiungere rate limiting** sui tool write

---

## 2. aicarmine-repo-state

**Descrizione**: Stato deterministico del repository (status, capabilities).

### Strumenti
- `aicarmine_repo_state_health`
- `aicarmine_repo_state_status`
- `aicarmine_repo_state_capabilities`

### Pro
- ✅ Minimalista e focalizzato
- ✅ Deterministico, nessuna side-effect
- ✅ Separazione netta dalla famiglia principale

### Contro
- ❌ Funzionalità sovrapposte con `aicarmine-codex-app` (stesso status/capabilities)
- ❌ Server separato aggiunge complessità di gestione

### Proposte di miglioramento
1. **Unificare** con `aicarmine-codex-app` in un unico server `aicarmine-repo`
2. **Oppure** mantenere separato ma con responsabilità chiara: solo stato "fresco" senza cache

---

## 3. aicarmine-repo-search-det

**Descrizione**: Ricerca deterministica nel repository (fd, ripgrep, ast-grep, tree-sitter, ctags).

### Strumenti
- `aicarmine_repo_search_fd`: File discovery
- `aicarmine_repo_search_rg`: Search con output JSON
- `aicarmine_repo_search_jq`: Query JSON
- `aicarmine_repo_search_ast_grep`: Search AST
- `aicarmine_repo_search_ast_grep_dry_run`: Rewrite dry-run
- `aicarmine_repo_search_tree_sitter_parse`: Parsing AST
- `aicarmine_repo_search_ctags`: Symbol extraction

### Pro
- ✅ 7 tool specializzati per ricerca semantica/sintattica
- ✅ Supporto AST per modifiche code-aware
- ✅ Output strutturato (JSON)
- ✅ Timeout configurabile per ogni tool

### Contro
- ❌ Troppe specializzazioni (7 tool per search)
- ❌ `jq` query tool non chiaro se è per file o testo
- ❌ Nessuna aggregazione in un unico tool con dispatch

### Proposte di miglioramento
1. **Creare un unico `aicarmine_repo_search`** con dispatch automatico basato su `strategy` (fd/rg/ast/tree_sitter/ctags)
2. **Aggiungere `aicarmine_repo_search_multi`** per combinare più strategie
3. **Mantenere i tool individuali** solo per debugging

---

## 4. aicarmine-rag / aicarmine-reag

**Descrizione**: Retrieval Augmented Generation con indicizzazione SQLite/FTS5 e reranking BGE.

### Strumenti
- `aicarmine_rag_context`: Search + reranking
- `aicarmine_rag_index_status`: Stato indicizzazione
- `aicarmine_rag_reindex`: Aggiornamento indice (delta/full)

### Pro
- ✅ FTS5 per ricerca semantica veloce
- ✅ Reranking BGE per qualità risultati
- ✅ Supporto delta/full reindex
- ✅ Chunking configurabile

### Contro
- ❌ Doppia istanza (aicarmine-rag e aicarmine_reag)
- ❌ Nessuna pulizia automatica degli indici obsoleti
- ❌ Nessun feedback loop per migliorare la qualità

### Proposte di miglioramento
1. **Unificare** le due istanze in un unico server
2. **Aggiungere `aicarmine_rag_quality_score`** per monitorare la qualità dei risultati
3. **Aggiungere `aicarmine_rag_cleanup`** per rimuovere chunk obsoleti

---

## 5. aicarmine-repo-validate

**Descrizione**: Validazione repository con profili reviewati.

### Strumenti
- `aicarmine_repo_validate_health`
- `aicarmine_repo_validate_diffcheck`
- `aicarmine_repo_validate_ruff`
- `aicarmine_repo_validate_pyright`
- `aicarmine_repo_validate_pytest`
- `aicarmine_repo_validate_shellcheck`
- `aicarmine_repo_validate_semgrep`
- `aicarmine_repo_validate_probe_profiles`
- `aicarmine_repo_validate_probe_run`

### Pro
- ✅ Validazione completa (lint, type check, test, security)
- ✅ Profili reviewati per testing contrattuale
- ✅ Output JSON per integrazione
- ✅ Timeout configurabile

### Contro
- ❌ Troppe operazioni separate (7 tool per validazione)
- ❌ `pytest` richiede esplicita autorizzazione anche per read-only
- ❌ Nessun caching dei risultati di validazione

### Proposte di miglioramento
1. **Creare `aicarmine_repo_validate_all`** che esegue tutti i validatori in parallelo
2. **Aggiungere caching** dei risultati per evitare ri-esecuzione
3. **Separare** i tool di validazione in un server dedicato

---

## 6. aicarmine-git-readonly

**Descrizione**: Operazioni Git solo lettura.

### Strumenti
- `aicarmine_git_readonly_health`
- `aicarmine_git_readonly_log`: Commit history
- `aicarmine_git_readonly_show`: Commit detail
- `aicarmine_git_readonly_diff`: Diff worktree/revisions
- `aicarmine_git_readonly_blame`: Line blame
- `aicarmine_git_readonly_branch_compare`: Branch comparison

### Pro
- ✅ Solo lettura (sicuro)
- ✅ Output strutturato
- ✅ Supporto blame e diff
- ✅ Timeout configurabile

### Contro
- ❌ Funzionalità sovrapposte con `aicarmine-codex-app` git tools
- ❌ Nessuna integrazione con git hooks

### Proposte di miglioramento
1. **Unificare** con `aicarmine-codex-app`
2. **Aggiungere `aicarmine_git_readonly_stash_list`** per vedere gli stash
3. **Aggiungere `aicarmine_git_readonly_tag_list`** per i tag

---

## 7. aicarmine-sqlite-readonly

**Descrizione**: Query SQLite solo lettura su database allowlistati.

### Strumenti
- `aicarmine_sqlite_readonly_health`
- `aicarmine_sqlite_readonly_list_databases`
- `aicarmine_sqlite_readonly_schema`: Schema lettura
- `aicarmine_sqlite_readonly_query`: Query SELECT

### Pro
- ✅ Solo lettura (sicuro)
- ✅ Allowlist di database
- ✅ Query con row_limit e timeout
- ✅ Supporto colonne e SQL

### Contro
- ❌ Allowlist rigida limita la flessibilità
- ❌ Nessuna migrazione automatica dello schema
- ❌ Nessun backup dei database

### Proposte di miglioramento
1. **Aggiungere `aicarmine_sqlite_readonly_backup`** per backup puntuali
2. **Rendere l'allowlist** configurabile via parametro
3. **Aggiungere `aicarmine_sqlite_readonly_analyze`** per statistiche

---

## 8. aicarmine-job-artifact

**Descrizione**: Accesso agli artifact dei job agentic (log, eventi, payload).

### Strumenti
- `aicarmine_job_artifact_health`
- `aicarmine_job_artifact_list_jobs`: Lista job
- `aicarmine_job_artifact_summary`: Summary job
- `aicarmine_job_artifact_events`: Eventi job
- `aicarmine_job_artifact_final`: Result finale
- `aicarmine_job_artifact_tool_results`: Tool result artifacts
- `aicarmine_job_artifact_subturns`: Sub-turn events
- `aicarmine_job_artifact_planner_payload`: Planner payload
- `aicarmine_job_artifact_rejections`: Rejection events

### Pro
- ✅ Completo accesso agli artifact dei job
- ✅ Supporto sub-turn e planner
- ✅ Estrazione rejections per debugging
- ✅ Payload planner leggibile

### Contro
- ❌ 9 tool per artifact management
- ❌ Nessun cleanup automatico degli artifact vecchi
- ❌ Nessuna compressione degli artifact grandi

### Proposte di miglioramento
1. **Creare `aicarmine_job_artifact_cleanup`** per rimuovere job vecchi
2. **Aggiungere `aicarmine_job_artifact_export`** per esportare in formato portatile
3. **Aggiungere `aicarmine_job_artifact_analyze`** per analisi statistica

---

## 9. aicarmine-job-view

**Descrizione**: Rendering HTML delle viste dei job.

### Strumenti
- `aicarmine_job_view_health`
- `aicarmine_job_view_list_views`: Liste views disponibili
- `aicarmine_job_view_render`: Rendering view
- `aicarmine_job_view_render_section`: Section rendering
- `aicarmine_job_view_ia_payload`: IA live control payload
- `aicarmine_job_view_outline`: HTML outline
- `aicarmine_job_view_links`: Link extraction
- `aicarmine_job_view_validate_html`: HTML validation

### Pro
- ✅ Rendering locale senza HTTP broker
- ✅ Multiple view types (dashboard, events, planner, IA)
- ✅ Lazy section rendering
- ✅ HTML validation

### Contro
- ❌ 8 tool per job viewing
- ❌ Dipendenza da template HTML non versionati
- ❌ Nessun caching delle views renderizzate

### Proposte di miglioramento
1. **Unificare** `render` e `render_section` in un unico tool con parametro `section`
2. **Aggiungere `aicarmine_job_view_cache_clear`** per pulire la cache
3. **Versionare** i template HTML

---

## 10. aicarmine-project-memory

**Descrizione**: Memoria persistente progetto con SQLite.

### Strumenti
- `aicarmine_project_memory_health`
- `aicarmine_project_memory_search`: Search record
- `aicarmine_project_memory_get`: Get record
- `aicarmine_project_memory_upsert_verified`: Upsert con source evidence
- `aicarmine_project_memory_mark_stale`: Mark stale
- `aicarmine_project_memory_supersede`: Supersede record
- `aicarmine_project_memory_audit_sources`: Audit source

### Pro
- ✅ Memoria persistente con audit trail
- ✅ Source evidence per ogni record
- ✅ Supporto supersede e stale
- ✅ Tags e metadata

### Contro
- ❌ Nessuna sincronizzazione tra istanze
- ❌ Nessun lock concorrente
- ❌ Nessuna migrazione automatica dello schema

### Proposte di miglioramento
1. **Aggiungere `aicarmine_project_memory_sync`** per sincronizzazione tra istanze
2. **Aggiungere `aicarmine_project_memory_lock`** per concorrenza
3. **Aggiungere `aicarmine_project_memory_migrate`** per migrazioni

---

## 11. aicarmine-local-subagent

**Descrizione**: Subagent locale per esecuzione tasks in isolamento.

### Strumenti
- `aicarmine_local_subagent_health`
- `aicarmine_local_subagent_capabilities`: Capabilities description
- `aicarmine_local_subagent_run_readonly`: Esecuzione task readonly

### Pro
- ✅ Esecuzione tasks in isolamento
- ✅ Solo readonly di default
- ✅ Timeout e max_steps configurabili
- ✅ Return mode flessibile (wait/background/async)

### Contro
- ❌ Solo un tool funzionale (`run_readonly`)
- ❌ Nessuna comunicazione tra subagent
- ❌ Nessun risultato aggregato

### Proposte di miglioramento
1. **Aggiungere `aicarmine_local_subagent_run_parallel`** per esecuzione parallela
2. **Aggiungere `aicarmine_local_subagent_result`** per recuperare risultati async
3. **Aggiungere `aicarmine_local_subagent_cancel`** per cancellare task

---

## 12. aicarmine-agentic-loop-client

**Descrizione**: Client per agentic loop dedicato con broker.

### Strumenti
- `aicarmine_agentic_loop_health`
- `aicarmine_agentic_loop_capabilities`: Capabilities description
- `aicarmine_agentic_loop_ensure_reranker`: Avvio reranker
- `aicarmine_agentic_loop_ensure_broker`: Avvio broker
- `aicarmine_agentic_loop_run`: Esecuzione loop
- `aicarmine_agentic_loop_status`: Status job
- `aicarmine_agentic_loop_result`: Result job

### Pro
- ✅ Controllo completo del ciclo agentic
- ✅ Avvio automatico broker e reranker
- ✅ Status e result retrieval
- ✅ Multiple return modes

### Contro
- ❌ Dipendenza da broker esterno
- ❌ Nessun fallback se broker non disponibile
- ❌ Nessun timeout globale

### Proposte di miglioramento
1. **Aggiungere `aicarmine_agentic_loop_fallback`** per fallback locale
2. **Aggiungere `aicarmine_agentic_loop_timeout_set`** per timeout globale
3. **Aggiungere `aicarmine_agentic_loop_retry`** per retry automatico

---

## 13. aicarmine-repo-code

**Descrizione**: Editing codice con proposal e validation.

### Strumenti
- `aicarmine_repo_code_health`
- `aicarmine_repo_code_propose_edit`: Code edit proposal
- `aicarmine_repo_code_unidiff_validate`: Diff validation
- `aicarmine_repo_code_git_apply_check`: Apply check
- `aicarmine_repo_code_apply_patch`: Patch application

### Pro
- ✅ Workflow completo: proposal → validate → check → apply
- ✅ Supporto structured_edit e unified_diff
- ✅ AST anchor e ast-grep rule
- ✅ Apply check prima dell'applicazione

### Contro
- ❌ `apply_patch` richiede `allow_source_write=true` esplicito
- ❌ Nessuna undo delle modifiche
- ❌ Nessun merge conflict resolution

### Proposte di miglioramento
1. **Aggiungere `aicarmine_repo_code_undo`** per annullare modifiche
2. **Aggiungere `aicarmine_repo_code_merge_resolve`** per conflict resolution
3. **Aggiungere `aicarmine_repo_code_diff_summary`** per riassunto modifiche

---

## 14. aicarmine-codex-ops

**Descrizione**: Operazioni di sistema e inventory MCP.

### Strumenti
- `aicarmine_codex_ops_health`
- `aicarmine_mcp_inventory_health`: Health MCP servers
- `aicarmine_mcp_inventory_list_targets`: Lista target
- `aicarmine_mcp_inventory_probe`: Inventory probe
- `aicarmine_service_state_health`: Stato servizio
- `aicarmine_service_state_ports`: Ports listening
- `aicarmine_service_state_processes`: Processi
- `aicarmine_service_state_logs`: Log files
- `aicarmine_service_state_snapshot`: Snapshot completo

### Pro
- ✅ Monitoring completo del sistema
- ✅ Inventory MCP servers
- ✅ Snapshot di porte, processi e log
- ✅ Solo lettura

### Contro
- ❌ 9 tool per operazioni operative
- ❌ Nessuna azione correttiva automatica
- ❌ Nessun alerting

### Proposte di miglioramento
1. **Unificare** i tool di service state in uno solo con parametro `type`
2. **Aggiungere `aicarmine_service_state_restart`** per riavviare servizi
3. **Aggiungere `aicarmine_service_state_alert`** per alerting

---

## Riepilogo Statistico

| Famiglia | Tool Count | Read-Only | Write | Specializzazione |
|----------|------------|-----------|-------|------------------|
| aicarmine-codex-app | 20+ | Parziale | Patch | Repository completo |
| aicarmine-repo-state | 3 | Sì | No | Stato repository |
| aicarmine-repo-search-det | 7 | Sì | No | Ricerca avanzata |
| aicarmine-rag | 3 | Sì | No | RAG/Indicizzazione |
| aicarmine-repo-validate | 9 | Parziale | No | Validazione |
| aicarmine-git-readonly | 6 | Sì | No | Git operations |
| aicarmine-sqlite-readonly | 4 | Sì | No | SQLite queries |
| aicarmine-job-artifact | 9 | Sì | No | Job artifacts |
| aicarmine-job-view | 8 | Sì | No | Job rendering |
| aicarmine-project-memory | 7 | Parziale | Sì | Memoria persistente |
| aicarmine-local-subagent | 3 | Sì | No | Subagent execution |
| aicarmine-agentic-loop-client | 7 | Parziale | Sì | Agentic loop |
| aicarmine-repo-code | 5 | Parziale | Sì | Code editing |
| aicarmine-codex-ops | 9 | Sì | No | System ops |
| **TOTALE** | **100+** | **70%** | **30%** | **14 famiglie** |

---

## Raccomandazioni Generali

### Alta priorità
1. **Unificare i server ridondanti**: repo-state + repo-search + repo-validate → `aicarmine-repo`
2. **Standardizzare i nomi dei tool**: usare verbi consistenti (read, write, search, validate, apply)
3. **Aggiungere documentazione inline** nei tool description
4. **Creare un tool `aicarmine_system_health_all`** per health check globale

### Media priorità
5. **Aggiungere caching** per risultati di ricerca e validazione
6. **Implementare rate limiting** sui tool write
7. **Aggiungere undo/rollback** per tutte le operazioni di modifica
8. **Creare un dashboard di monitoring** integrato

### Bassa priorità
9. **Aggiungere supporto per webhook** per eventi asincroni
10. **Implementare backup automatico** per database e memoria
11. **Aggiungere crittografia** per dati sensibili in memoria
12. **Creare un tool di migrazione** per aggiornamenti schema