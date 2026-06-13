<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_START -->
Regole operative non negoziabili:
1. Il contratto non va modificato se non richiesto da Carmine esplicitamente.
2. Il prodotto finale puo' essere arricchito come gia' viene fatto; non cambiare logica senza richiesta esplicita.
3. Non devi presupporre nulla: non e' il tuo compito.
<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_END -->
# Contratto corretto: Agentic Loop interno con validator-only gate

## Cosa NON deve succedere

Il controller 3572 non deve trasformare una richiesta in uno script deterministico. Non deve decidere lui `repo_list_files -> repo_read -> final` al posto del planner. Non deve finalizzare automaticamente solo perché un tool read-only ha prodotto un risultato. Non deve tornare a OpenWebUI con soli link a job, `final_path` o `job_url` come unico contesto operativo.

Il bridge 3571 non deve esporre a OpenWebUI il protocollo interno di continuazione. In un risultato terminale non devono comparire `continuation_surface`, `call_protocol`, `call_examples`, diagnostica transport, raw events o path locali come contenuto utile. Il 30B esterno vede solo la risposta 3571, quindi i risultati reali dei tool riusciti devono essere trasportati inline nel JSON.

## Flusso corretto

```text
OpenWebUI / 30B
  -> 3571 bridge pubblico /vulkan_helper
  -> 3572 broker /vulkan/agent
  -> 3572 crea il job e avvia agent_job_worker
  -> 11434 planner 30B sceglie il prossimo step
  -> 3572 validator-only gate controlla la decisione
      -> se tool valido: 3572 dispatch_tool(...) esegue il tool interno
      -> se emissione invalida/sporca: eventuale repair 11435, poi nuova validazione
      -> se contratto tool/validator fallisce: controller_guard e nuovo turno planner
      -> se final valido: finalize_agentic_job(..., status="completed")
      -> se invalido non riparabile: controller_guard / blocked / max_steps
  -> 3572 ritorna lo stato terminale compatto a 3571
  -> 3571 wrappa il terminal result per OpenWebUI
  -> OpenWebUI riceve content + tool_context_for_30b JSON strutturato
```

## Regola centrale

Il planner decide. Il controller valida. Il controller non sostituisce il planner con uno step hard-coded.

`done_reason` di Ollama chiude un turno modello, non il job 3572. Il job si
chiude solo quando la logica 3572 arriva a uno stato terminale (`completed`,
`max_steps_reached`, `blocked_needs_attention`, `failed`, ecc.). Il caso
`completed` richiede un `action=final` del planner accettato dal validator.

## Planner native tool calling

Quando `AICARMINE_AGENTIC_PLANNER_NATIVE_TOOLS=true` e
`AICARMINE_AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS=true`, il trasporto dei tool del
planner verso 11434 e' native tool calling Ollama. In questa modalita':

- una decisione tool valida deve arrivare come `message.tool_calls` nativo, con
  `native_tool_call=true` dopo la normalizzazione interna;
- JSON testuale con `{"action":"tool", ...}` non e' un tool call valido e deve
  essere rifiutato prima del dispatch con una violazione tipizzata, per esempio
  `planner_text_tool_call_disallowed_in_native_mode`;
- `final`, `block` e stati terminali equivalenti non sono dispatch di tool:
  possono restare decisioni testuali JSON oppure testo terminale naturale
  wrapped dal controller come `final_answer` prima del validator;
- il campo `tools` del payload Ollama e' il manifest operativo dei tool interni
  disponibili al planner; i vincoli del manifest devono restare coerenti con il
  validator;
- eventuali batch native sono ammessi solo per tool read-only/cacheable, entro
  `AICARMINE_AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY`, e ogni sub-call
  passa lo stesso validator prima del dispatch;
- il repair 11435 non deve convertire un'emissione testuale `action=tool` in un
  tool dispatch nascosto quando native mode richiede `message.tool_calls`;
- la history native in `messages` e' solo contesto di lavoro del planner, puo'
  essere finestrata/budgetata e non sostituisce la history JSON persistente del
  job.

Regola anti-regressione: se una chiamata tool entra nel dispatcher senza
provenienza native quando native mode e' richiesta, il protocollo planner e'
rotto. Se invece un `final`/`block` JSON testuale o una prosa terminale wrapped
come `final_answer` viene rifiutata solo perche' non e' un tool call nativo, il
gate e' troppo stretto.

## Preseed iniziale dinamico

Per richieste generiche di analisi repository, il controller può raccogliere
evidenza iniziale read-only prima del primo turno planner. Questo preseed non è
un fallback, non è un piano nascosto e non autorizza auto-final.

Sequenza ammessa:

```text
repo_tree "."
  -> repo_read di doc/config realmente emersi dalla root surface
  -> repo_list_files di aree utili realmente presenti e non low-signal
  -> repo_read di file concreti emersi da quelle aree
  -> primo planner_decision
```

Ogni step iniziale deve restare marcato come `controller_preseed=true`, con
artifact interno e `preseed_reason`. I path preferiti sono solo ranking: se il lab
worktree cambia o un file non esiste, il controller registra la mancata
selezione in `initial_orientation_surface.skipped_candidates` e non inventa
contenuto.

Il risultato terminale espone `initial_orientation_surface` dentro
`tool_context_for_30b`, così OpenWebUI/30B riceve struttura, doc letti, aree
listate e file concreti senza dipendere solo da `job_url` o path locali.

## Validator-only gate

Il validator controlla la proposta del planner prima del dispatch.

Controlli principali:

- path inesistenti in `repo_read`, `repo_apply_patch`, `repo_write_file`;
- `repo_read` su basename inventati non presenti in evidenza precedente;
- `repo_list_files` con `limit` inferiore al numero richiesto dall'utente;
- `repo_list_files` o `repo_read` fuori dallo scope richiesto, per esempio richiesta su `ai_carmine`/`ia_carmine` ma path `.` o `.codex`;
- ripetizione dello stesso tool con gli stessi argomenti senza progresso;
- `final` prima di aver letto realmente i file richiesti;
- `repo_read ok=True` con zero file letti realmente.

Per `final`, una lettura concreta non è un semplice path in history. Conta solo
un `repo_read ok=True` con contenuto reale verificato:

- il contenuto è presente come `content` nel risultato dello stesso tool; oppure
- il risultato compatto punta al JSON prodotto dallo stesso `repo_read` riuscito,
  e quel JSON ricaricato contiene `content` non vuoto per il file.

`content_preview`, path, conteggi, `line_count` o artifact path locali non
bastano per soddisfare il gate. Il contratto terminale deve esporre
`verified_content_read_count`, `verified_content_reads` e
`missing_full_content_reads` per rendere visibile la differenza fra file
"dichiarati letti" e file realmente trasportabili a OpenWebUI.

Quando una decisione è invalida, il controller non esegue il tool e non sceglie uno step alternativo. Inserisce in history un `controller_guard` con:

```json
{
  "tool": "controller_guard",
  "guard_type": "planner_decision_validator",
  "violations": [...],
  "evidence_contract": {...},
  "rejected_decision": {...}
}
```

Poi richiama il planner interno. OpenWebUI non viene coinvolta tra uno step e l'altro.

## Code product / diff report-only lane

Per goal che chiedono `diff`, `differenziale`, `unified diff`, `code diff`,
`refactoring concreto`, `proposta patch` o `code product`, il planner non puo'
finalizzare con sola prosa.

Contratto obbligatorio:

- il target deve essere letto prima con `repo_read`;
- il planner deve chiamare `repo_propose_code_edit`;
- `repo_propose_code_edit` e' report-only: non scrive sorgenti e non applica
  patch;
- il payload valido e' inline e contiene `kind=code_edit_proposal`,
  `target_file`, `edit_kind`, `rationale`, `validation_commands`, `errors`,
  `warnings`, `source_writes_performed=false`,
  `patch_application_performed=false` e `manual_review_required=true`;
- se `edit_kind=unified_diff`, `unified_diff` deve essere completo e deve
  contenere marker `---`, `+++` e `@@`;
- se `edit_kind=structured_edit`, `structured_operations` deve contenere le
  operazioni complete;
- se `edit_kind=no_op`, serve una `rationale` esplicita e non deve esserci
  contenuto patch;
- `artifact` JSON locale e' copia di audit dello stesso payload, non sostituto
  del payload inline.

Violazioni tipizzate:

- goal code-product senza `repo_propose_code_edit ok=true`:
  `missing_code_product_candidate`;
- payload con solo preview, summary o artifact path:
  `code_product_payload_not_complete`;
- diff senza marker o non parsabile quando richiesto:
  `invalid_code_product_candidate`;
- target non letto prima con `repo_read`:
  `code_product_target_not_read`.

Queste violazioni sono semantiche del validator/tool contract. Non devono
essere mascherate da repair GPU0/11435: il controller registra il guard e il
planner deve emettere un nuovo JSON valido. I goal apply/edit/fix/write restano
separati: li serve `repo_apply_patch` dopo `repo_read` dell'`old_text` esatto e
successiva validazione.

Per goal code-product, il contratto passato al planner deve essere coerente con
il validator: finche' manca una proposta valida, `final_allowed=false`,
`planner_may_choose_final=false` e `required_next_progress` deve chiedere
`repo_propose_code_edit`. Non e' ammesso un payload che dichiari
`final_allowed=true` mentre il validator rifiuterebbe il final con
`missing_code_product_candidate`.

## Evidence contract passato al planner

Ogni richiesta al planner contiene `evidence_contract`, che include:

```json
{
  "must_stay_bound_to_goal": true,
  "must_use_prior_evidence": true,
  "planner_may_decide_next_tool": true,
  "controller_may_validate_but_not_substitute_tool": true,
  "goal_requests_python_file_review": true,
  "requested_file_count": 50,
  "target_scope": {
    "mentioned": ["ai_carmine"],
    "required_path": "ia_carmine",
    "existing_candidates": ["ia_carmine"]
  },
  "known_paths_from_repo_list_files": [...],
  "repo_list_files_evidence": [...],
  "repo_read_evidence": {
    "successful_paths": [...],
    "failed_paths": [...],
    "steps": [...]
  },
  "verified_content_read_count": 10,
  "verified_content_reads": [
    {
      "path": "AGENTS.md",
      "line_count": 120,
      "truncated": false,
      "content_chars": 17143,
      "source": "repo_read_tool_result"
    }
  ],
  "missing_full_content_reads": [],
  "required_next_progress": "...",
  "forbidden_patterns": [...]
}
```

## Prompt pack pre-turno

Ogni richiesta al planner contiene un prompt pack costruito dal controller prima
della chiamata a 11434. Il pack separa dati necessari e dati opzionali:

- `required_working_set`: finestre reali e consumabili dei file/diff/risultati
  richiesti dal prossimo passo. Non puo' essere sostituito da soli metadata.
  Ogni finestra deve avere testo reale, coordinate, dimensione completa e hash.
- `optional_context`: history digest, memoria, RAG/chunk, turn memory e
  manifest strumenti. Questa parte puo' essere ridotta a finestre SQLite reali
  o, come ultima misura, omessa per budget; non puo' sostituire il working set
  richiesto.
- `prompt_budget_report`: conteggio reale del prompt serializzato
  (`system_prompt_chars`, `total_user_payload_chars`, `total_prompt_chars`,
  `char_budget`, `over_budget`, sezioni).

`intrinsic_context` resta dentro `optional_context`; non e' una tool call, non
entra in `PLANNER_INTERNAL_TOOLS` e non prova da solo il gate di finalizzazione.

Le letture `planner_scratchpad_read` con `mode=prompt_context_window` devono
restare tracciabili nella history compatta. Il compact payload deve preservare
testo reale bounded, `document_id`, `section`, `window_start`, `window_end`,
`full_chars`, `window_chars`, `complete`, `has_more_before`,
`has_more_after`, `sha256` e `window_sha256`. Se una history contiene una
finestra prompt senza questi campi, il validator deve bloccare con
`prompt_context_window_tracking_metadata_missing`; se viene richiesta di nuovo
una finestra gia' consumata, deve bloccare con
`prompt_context_window_already_consumed`.

La native tool surface di ogni turno deve essere coerente con
`required_next_progress`. Se il contratto richiede un passo specifico, ad
esempio `planner_scratchpad_write` per `code_product_build_state`,
`planner_scratchpad_read` per una continuation reale, `repo_propose_code_edit`
con payload completo, un typed block o un final, la surface non deve esporre
tool contraddittori solo perche' esistono nel registry. Una native tool call non
presente nella surface del turno resta invalida
(`native_tool_not_in_turn_surface`).

Gli adapter deterministici (`repo_fd_files`, `repo_rg_search`, `repo_jq_query`,
`repo_ast_grep_*`, `repo_tree_sitter_parse`, `repo_unidiff_validate`,
`repo_git_apply_check`, `repo_ruff_check`, `repo_pyright_check`,
`repo_pytest_run`, `repo_shellcheck`, `repo_ctags_symbols`,
`repo_semgrep_scan`, `repo_hyperfine_benchmark`) seguono la stessa regola:
sono tool interni 3572 esposti solo quando utili alla classe del goal o a un
`required_next_progress` specifico. Non entrano nella superficie pubblica 3571 e
non sostituiscono `repo_read`, diff completi o payload ricostruiti per
OpenWebUI.

Schema minimo:

```json
{
  "schema": "planner_intrinsic_context.v1",
  "goal_classification": {},
  "retrieved_memory": {},
  "retrieved_rag_chunks": {},
  "repo_map_summary": {},
  "failure_patterns": [],
  "tool_purpose_manifest": [],
  "budget_report": {
    "num_ctx_requested": 12288,
    "num_ctx_cap": 12288,
    "num_ctx_effective": 12288,
    "prompt_char_budget": 48000,
    "prompt_compact_threshold_chars": 24000,
    "generation_headroom_char_budget": 40000,
    "generation_headroom_reserve_chars": 8000
  }
}
```

Regole:

- `AICARMINE_AGENTIC_PLANNER_NUM_CTX` e' il valore richiesto; il valore
  operativo e' cappato da `AICARMINE_AGENTIC_PLANNER_NUM_CTX_CAP` per evitare
  spill CPU/RAM. Health/eventi espongono requested/cap/effective.
- `AICARMINE_AGENTIC_PLANNER_PROMPT_CHAR_BUDGET` governa il prompt pack. Il
  controller misura il prompt reale, incluso system prompt e report stesso.
- `AICARMINE_AGENTIC_PLANNER_PROMPT_COMPACT_RATIO`, default `0.5`, e' la soglia
  di compattazione: se il prompt misurato supera il 50% del budget disponibile,
  il controller salva sezioni grandi in SQLite job-local e passa al planner
  solo finestre piccole reali.
- La soglia di compattazione e' soft. Non e' il limite hard di headroom. Il
  blocco `planner_prompt_no_generation_headroom` scatta solo quando, dopo
  windowing/omissione opzionale, il prompt supera ancora il budget hard di
  generazione (`prompt_char_budget` meno la riserva di generazione).
- file, diff, repo tree, history e risultati grandi vengono rappresentati come
  finestre `planner_prompt_context_window.v1` con testo, `document_id`,
  offset, `has_more_before`, `has_more_after`, dimensione completa e hash. Non
  si passa `*_present=true`, conteggi o path locali come sostituto della
  sostanza.
- se una finestra ha `has_more_after=true`, il planner puo' leggere
  ricorsivamente la finestra successiva tramite `planner_scratchpad_read` con
  `kind=prompt_context_window`, `document_id`, `offset=window_end` e
  `max_chars`, ma per `repo_read` questo e' contesto adiacente opzionale salvo
  continuation esplicita del controller.
- se anche dopo finestre SQLite piccole e omissione del solo contesto opzionale
  il prompt resta fuori budget, il controller blocca in modo tipizzato invece
  di inviare un prompt troncato.
- se il controller emette `required_next_tool_call` /
  `prompt_context_continuation_required` per una finestra necessaria, il planner
  deve proseguire con `planner_scratchpad_read(kind=prompt_context_window, ...)`.
  Qualunque altra decisione viene rifiutata con
  `prompt_context_continuation_required`. Questa e' una violazione semantica del
  controller e non deve essere inviata al repair GPU0/11435.
- `rag.sqlite` e' letto solo come SQLite/FTS5 read-only substrate quando
  configurato/presente;
- DB o schema mancanti producono gap tipizzati, non contenuto inventato;
- se `RAG_RERANKING_ENGINE=external`, il reranker esterno puo' riordinare i
  chunk gia' recuperati; endpoint giu' produce
  `retrieved_rag_chunks.rerank.status=unavailable`, non una surface tool e non
  un risultato finto;
- il percorso RAG/rerank intrinseco usa il pool FTS default `80`, input
  reranker default `12`, document cap `2500` caratteri e timeout default
  `30.0` secondi; `candidate_count` e `input_count` non sono sinonimi;
- memoria/RAG/chunk non diventano nuove surface tool;
- solo dopo questo contesto il planner puo' chiamare
  `runtime_sqlite_memory_search/write` o `planner_scratchpad_*`, e solo per un
  gap selettivo esplicito.
- `planner_scratchpad_write` con `kind=answer_chunk` puo' salvare sezioni
  complete di risposta nel composer SQLite job-local. Il broker/wrapper puo'
  ricomporle nello structured context come `answer_for_30b`; questo non rende
  `answer_for_30b` un top-level pubblico 3571 e non e' un sostituto di
  `repo_read` o `repo_propose_code_edit`.
- Questa compattazione vale solo per il prompt del planner verso 11434.
  `tool_context_for_30b` verso OpenWebUI continua a trasportare i payload reali
  dei tool riusciti secondo il flusso pubblico esistente.

## IA Live Control View 3572

3572 puo' esporre una vista operatore read-only:

- `/jobs/{job_id}/ia-view`
- `/jobs/{job_id}/ia-view.json`

Questa vista non e' superficie pubblica 3571, non e' tool planner e non cambia
il contratto OpenWebUI. Serve a controllare cosa vede l'IA: prompt payload
salvato per 11434, working set, intrinsic context, evidence contract, decisione
planner, compact tool result reinviato alla history, raw tool result reidratato,
validator guard e `tool_context_for_30b` terminale. Deve mostrare violazioni
preview-only, metadata-only o artifact-only invece di nasconderle.

## OpenWebUI non riceve solo un sommario

Il terminal result 3571 verso OpenWebUI è minimale in top-level e completo nel
campo di contesto:

```json
{
  "ok": true,
  "service": "vulkan_agent",
  "mode": "agent_job_final_waited_compact",
  "required_top_level_keys": [
    "ok",
    "service",
    "mode",
    "required_top_level_keys",
    "payload_index_for_30b",
    "priority_evidence_for_30b",
    "openwebui_usage",
    "tool_context_for_30b"
  ],
  "payload_index_for_30b": {
    "internal_job_status": {
      "completed": true,
      "status": "completed",
      "source": "internal_3572_job_status"
    },
    "concrete_results": []
  },
  "priority_evidence_for_30b": {
    "schema": "openwebui.priority_evidence_for_30b.v1",
    "items": [
      {
        "kind": "code_edit_proposal",
        "target_file": "ia_carmine/...",
        "edit_kind": "unified_diff",
        "payload_is_complete": true,
        "unified_diff": "diff completo inline..."
      }
    ]
  },
  "openwebui_usage": {
    "payload_index_field": "payload_index_for_30b",
    "priority_evidence_field": "priority_evidence_for_30b.items",
    "full_tool_evidence_field": "tool_context_for_30b.artifacts[*].artifact"
  },
  "tool_context_for_30b": "{\n  \"artifacts\": [...],\n  \"limits\": [...]\n}"
}
```

`tool_context_for_30b` è una stringa JSON pretty-printed e parseabile. Non è un
oggetto annidato monolinea e non è un sommario. Contiene payload reali inline e
non riferimenti locali:

- `artifacts[*].artifact`: risultato reale del tool interno riuscito,
  ricostruito dal broker/wrapper/composer quando il raw result vive in JSON o
  SQLite locali;
- `evidence_view_for_30b`: finestre/contenuti reali dei file letti;
- `answer_for_30b`, `next_action_for_30b` o `composed_answer.text`: campi
  interni allo structured context, non top-level 3571 pubblici;
- limiti dichiarati dai tool riusciti, per esempio `truncated=true`.

`priority_evidence_for_30b` e' una vista prioritaria navigabile per OpenWebUI.
Non sostituisce `tool_context_for_30b` e non puo' contenere preview, path locali
o sommari come payload primario. I casi ammessi sono:

- `code_edit_proposal`: diff completo in `unified_diff` oppure operazioni
  complete in `structured_operations`;
- `repo_file_full_content`: file completo in `content`;
- `repo_analysis_summary`: summary del planner piu' mappa compatta delle
  evidenze gia' presenti nel contesto completo.

Nel payload pubblico non devono comparire path locali, SQLite `document_id`,
`db`, `workspace`, `tool-results/*.json`, `reads/*.json` o
`C:\Users\...` come contenuto utile. Se un JSON locale viene usato dal broker,
deve essere solo una copia di audit interna e il suo contenuto deve essere
espanso inline prima di arrivare a OpenWebUI:

```json
{
  "producer_step": 0,
  "tool": "repo_read",
  "arguments": {"paths": ["AGENTS.md"]},
  "ok": true,
  "artifact": {
    "kind": "repo_read",
    "repo_path": "AGENTS.md",
    "line_count": 120,
    "truncated": false,
    "preview_only": false,
    "content": "testo reale letto dal file..."
  }
}
```

Regole per i tool riusciti:

- `repo_read`: `artifact.content` contiene il testo reale del file letto; `repo_path` è solo metadata logico del repo;
- `repo_tree`: `artifact.entries` contiene le entry realmente esplorate;
- `repo_list_files`: `artifact.paths`/`artifact.files` contiene i path realmente listati;
- `repo_propose_code_edit`: `artifact.kind` e' `code_edit_proposal`, il diff
  completo resta in `artifact.unified_diff`, le operazioni complete restano in
  `artifact.structured_operations`, le evidenze AST restano in
  `artifact.ast_evidence`, `source_writes_performed=false`,
  `patch_application_performed=false` e `manual_review_required=true`;
- `repo_command` e tool terminali: `artifact.returncode`, `artifact.stdout`, `artifact.stderr`, tail se prodotti.

Il bridge 3571 può caricare un JSON locale solo per espandere il risultato dello
stesso tool riuscito che lo ha prodotto. Il path locale non entra nel payload
OpenWebUI. Non usare `final_path`, `reads/*.json`, `tool-results/*.json` o
`C:\Users\...` come contenuto primario: OpenWebUI non può aprirli.

La stessa regola vale per tutti gli stati terminali: `completed`,
`max_steps_reached`, `blocked_needs_attention`, `failed`, `cancelled`.

La shape pubblica 3571 deve restare la stessa anche quando `job_ok=false`.
Campi primari come `payload_index_for_30b`, `priority_evidence_for_30b`,
`openwebui_usage`, `tool_context_for_30b` e `result` non devono sparire solo
perche' il job e' bloccato, fallito, arrivato a max step o cancellato. Se il
payload terminale/final JSON contiene un `result` completo, quello e' la fonte
primaria da riportare a OpenWebUI; il digest compatto
`{ "preview": ... }` e' solo fallback quando non esiste un `result` completo.

Nel payload pubblico `result.history` non e' raw audit history: e' una ledger
bounded `agentic_terminal_public_history_ledger.v1`. Deve mostrare step,
azione, tool, motivo, target/result facts e payload code-product completi se
presenti, ma non deve reinserire raw `evidence_contract`, cache key, artifact
path locali o diagnostica transport pesante. I payload reali completi restano
in `tool_context_for_30b`, `priority_evidence_for_30b` e
`payload_index_for_30b`.

`job_ok=false` e lo stato terminale sono il warning, non un motivo per
sostituire il payload con una risposta ridotta.

## Caso discriminante: richiesta 50 file

Richiesta:

```text
Leggi i primi 50 file Python in ai_carmine e descrivi a cosa servono e come possono essere migliorati
```

Se il planner propone:

```json
{"tool":"repo_list_files","arguments":{"path":".","suffix":".py","limit":30}}
```

il validator rifiuta:

```text
repo_list_files_limit_too_small: requested=50 got=30
repo_list_files_outside_requested_scope: expected_path=ia_carmine got=.
```

Se il planner propone:

```json
{"tool":"repo_read","arguments":{"paths":["cli.py","runner.py"]}}
```

il validator rifiuta:

```text
repo_read_non_existing_paths: cli.py, runner.py
repo_read_paths_not_from_prior_list: cli.py, runner.py
repo_read_outside_requested_scope: cli.py, runner.py
```

Se il planner propone `final` dopo aver letto solo 30 file ma la richiesta ne chiedeva 50 e l'evidenza ne mostra almeno 50, il validator rifiuta:

```text
final_before_requested_file_count_read: required=50 successful=30
```

## Verifica minima

```powershell
python -m compileall .\aicarmine_broker .\aicarmine_vulkan_bridge_server.py
```

Poi rilanciare il broker 3572 e il bridge 3571, perché i processi Python vecchi possono mantenere moduli già importati.
