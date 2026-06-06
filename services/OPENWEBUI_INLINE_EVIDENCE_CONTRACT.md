# OpenWebUI Inline Evidence Contract

## Regola Centrale

```text
Objects are not transport.
Paths are not evidence.
Artifacts are public evidence only after their real content/product is
materialized as inline JSON before the 3571 OpenWebUI boundary.
```

Versione operativa:

```text
Gli oggetti interni non attraversano il protocollo OpenWebUI.
I path locali non sono evidenza per OpenWebUI.
Ogni artifact passato a OpenWebUI deve essere una materializzazione JSON inline
reale del contenuto/prodotto del loop agentico.
```

Solo JSON inline materializzato è evidenza pubblica per il modello che riceve il
risultato di `vulkan_helper` su 3571. Oggetti Python, path locali, file job,
artifact path e riferimenti interni possono essere utili al runtime locale, ma
non sono contenuto leggibile da OpenWebUI.

## Evidenza Pubblica Valida

Sono evidenza pubblica:

- `content` inline;
- `content_chunks` inline con metadati di completezza;
- `unified_diff` inline;
- `structured_operations` inline;
- `old_text` e `new_text` inline;
- `stdout` e `stderr` inline;
- JSON parsato inline;
- `payload_index_for_30b` quando punta a campi realmente presenti e non vuoti.

## Non Sono Evidenza Pubblica

Non sono evidenza pubblica:

- `final_path`;
- `artifact_path`;
- `events_path`;
- `workspace`;
- `sqlite_path`;
- `document_id`;
- `planner_stream_path`;
- rappresentazioni testuali di oggetti Python;
- placeholder o marker come `local_path_omitted`;
- `content_preview` quando sostituisce il full content richiesto;
- un summary quando sostituisce il payload concreto.

Un marker di omissione non e' una materializzazione. Se compare in un job legacy
deve essere eliminato o trasformato in una ragione tipizzata di incompletezza;
non deve diventare evidenza pubblica.

## Superficie 3571

La superficie pubblica deve essere completa ma non ridondante:

1. `evidence_guide_for_30b` spiega come leggere il payload.
2. `payload_index_for_30b.concrete_results` punta ai risultati concreti.
3. `priority_evidence_for_30b.items[*]` contiene il payload inline primario.
4. `tool_context_for_30b.artifacts[*].artifact` è solo il mirror degli artifact
   materializzati, non un dump completo del job.

`answer_for_30b`, `message_for_30b`, `summary_for_30b` e `content` non devono
essere duplicati come alias top-level quando hanno lo stesso scopo di
`evidence_guide_for_30b`.

Il summary puo' orientare, ma non sostituire:

- `evidence_guide_for_30b` e' guida alla lettura;
- `payload_index_for_30b` deve puntare a campi inline esistenti;
- `priority_evidence_for_30b` deve contenere payload o prodotti concreti quando
  il job dichiara risultati;
- `tool_context_for_30b.artifacts[*].artifact` deve contenere JSON inline reale.

## Report Di Materializzazione

Ogni payload terminale pubblico deve esporre `materialization_report`, con schema
`public_evidence_materialization.v1`, per dichiarare:

- chi ha certificato la materializzazione del payload pubblico;
- se `tool_context_for_30b` è JSON object parseabile;
- quanti artifact sono stati materializzati inline;
- se `payload_index_for_30b` punta a campi presenti e non vuoti;
- che path locali e oggetti interni non sono trasporto pubblico.

L'owner primario è 3572:

- `services/aicarmine_broker/application/public_payload/evidence_materializer.py`
  materializza `priority_evidence_for_30b`, `payload_index_for_30b` e
  `materialization_report`;
- 3571 deve preservare questi campi quando
  `materialization_report.owner == "3572_broker"` e `ok == true`;
- 3571 puo' produrre un report owner `3571_bridge` solo come fallback
  diagnostico/emergency rehydration, dichiarando esplicitamente
  `bridge_emergency_rehydration_used`.
