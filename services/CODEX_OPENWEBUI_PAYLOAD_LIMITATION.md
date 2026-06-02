# Codex/OpenWebUI Payload Limitation

## Sintomo

Un payload JSON restituito dal tool pubblico OpenWebUI `vulkan_helper` su 3571 puo essere accettato e lavorato da OpenWebUI, ma non essere gestibile in modo affidabile da Codex nella chat.

Nel caso osservato, Codex non e riuscito a mostrare correttamente in chat il payload completo del tool result 3571. I tentativi di stampa hanno prodotto output parziale, formattazione alterata o finestre spezzate che non corrispondevano alla resa utile del tool result in OpenWebUI.

## Evidenza

Payload osservato:

- tool pubblico: `vulkan_helper`
- endpoint: `POST http://127.0.0.1:3571/vulkan_helper`
- job: `job-d056b7be`
- status: `completed`
- JSON compatto prodotto dal result 3571: circa `359349` caratteri
- JSON pretty prodotto per ispezione: circa `386711` caratteri

Il payload contiene campi strutturati rilevanti per il modello OpenWebUI, tra cui:

- `payload_index_for_30b`
- `priority_evidence_for_30b`
- `tool_context_for_30b`
- `answer_for_30b`
- `content`

La dimensione e la struttura annidata del JSON hanno superato la capacita pratica di Codex di stamparlo, leggerlo e mantenerlo coerente nella conversazione.

## Causa

Il problema non e che OpenWebUI non possa ricevere o lavorare quel JSON.

Il problema e che Codex, in questa superficie di lavoro, ha limiti interni di gestione dell'output conversazionale e del contesto. Quando un payload e molto grande, annidato e contiene lunghi campi testuali, Codex puo:

- vedere solo finestre parziali;
- alterare la forma utile del payload durante la stampa;
- perdere continuita tra parti successive;
- confondere riepiloghi diagnostici con il result reale;
- non riuscire a verificare integralmente cosa OpenWebUI vede.

## Regola Operativa

Codex non deve dichiarare di comprendere il progetto, il tool result o il comportamento del sistema se non ha letto e verificato l'output completo rilevante.

Se Codex non riesce a leggere, stampare o mantenere nel contesto un payload che OpenWebUI invece lavora, deve dichiarare esplicitamente il limite:

> Codex non puo confermare comprensione completa del progetto o del risultato perche non ha processato integralmente il payload prodotto dal tool.

## Implicazione

Un output gestibile da OpenWebUI non e automaticamente gestibile da Codex.

Quindi Codex non deve:

- sostituire il payload completo con un riepilogo;
- assumere che un campo diagnostico rappresenti il result completo;
- proporre patch basate su finestre parziali;
- sostenere che il protocollo sia corretto senza verificare il result pubblico completo;
- trattare path locali o preview come equivalenti al payload inline visto da OpenWebUI.

## Comportamento Richiesto

Quando il payload e troppo grande per essere gestito integralmente da Codex:

1. dichiarare il limite;
2. indicare quale payload non e stato letto integralmente;
3. distinguere il result pubblico del tool dai riepiloghi diagnostici;
4. non inferire comprensione del progetto;
5. non proporre modifiche al protocollo senza evidenza completa;
6. usare solo evidenza realmente letta e verificata.

## Conclusione

Codex deve trattare i payload OpenWebUI molto grandi come una fonte che puo superare le sue capacita interne. Se non riesce a leggere l'output completo, non deve comportarsi come se lo avesse compreso.
