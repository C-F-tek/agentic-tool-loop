<!-- CODEX_OPENWEBUI_PAYLOAD_LIMITATION_START -->
# Limite operativo Codex su payload OpenWebUI

Un payload JSON restituito dal tool pubblico OpenWebUI `vulkan_helper` su 3571
puo essere accettato e lavorato da OpenWebUI ma non essere gestibile in modo
affidabile da Codex nella chat.

Regola obbligatoria:

- Codex non deve dichiarare di comprendere il progetto, il tool result o il
  comportamento del sistema se non ha letto e verificato l'output completo
  rilevante.
- Se Codex non riesce a leggere, stampare o mantenere nel contesto un payload
  che OpenWebUI invece lavora, deve dichiarare esplicitamente il limite.
- Codex deve distinguere sempre il result pubblico del tool da riepiloghi
  diagnostici, finestre parziali, path locali, preview o output spezzati.
- Codex non deve proporre patch, cambiare protocollo o sostenere che il
  protocollo sia corretto quando la conclusione dipende da un payload non letto
  integralmente.
- Se l'output OpenWebUI supera i limiti interni di Codex, la conclusione
  corretta e': Codex non puo confermare comprensione completa del progetto o
  del risultato perche non ha processato integralmente il payload prodotto dal
  tool.

Documento esteso: `services/CODEX_OPENWEBUI_PAYLOAD_LIMITATION.md`.
<!-- CODEX_OPENWEBUI_PAYLOAD_LIMITATION_END -->

<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_START -->
Regole operative non negoziabili:
1. Il contratto non va modificato se non richiesto da Carmine esplicitamente.
2. Il prodotto finale puo' essere arricchito come gia' viene fatto; non cambiare logica senza richiesta esplicita.
3. Non devi presupporre nulla: non e' il tuo compito.
<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_END -->
# AGENTS.md - Operational Notes For This Workspace

## Metodo obbligatorio

Per problemi su servizi, launcher, tool loop, OpenWebUI o log:

1. Separa sintomo, ipotesi, evidenza, causa e fix.
2. Non usare fallback o workaround per nascondere il problema.
3. Prima di proporre patch verifica chi legge, chi scrive, quale processo gira,
   quale file viene caricato e quale comando produce il sintomo.
4. Se un comportamento ricompare, sospetta prima processo vecchio, cache,
   rigenerazione, profilo sbagliato, PATH o venv errata.
5. Ogni ipotesi deve avere un test discriminante.
6. Una soluzione e valida solo con catena: sintomo -> prova -> causa confermata
   -> fix minimo -> verifica.

## Contratto agentic loop

Prima di modificare `services/aicarmine_broker/planner.py`,
`services/vulkan_bridge/app.py` o il launcher dei servizi, leggere:

- `services/VALIDATOR_ONLY_AGENTIC_LOOP_CONTRACT.md`
- `services/END_TO_END_AGENTIC_FLOW.md`
- `services/SERVICES_MODULE_TECHNICAL_REFERENCE.md`
- Per dettagli modulo per modulo, seguire i link `MODULE_REFERENCE.md`
  indicati nella reference centrale.
- Per una scheda tecnica di ogni singolo file sotto `services`, leggere
  `services/MODULE_TECHNICAL_DESCRIPTIONS.md`.

Punti non negoziabili del contratto corrente:

- 3571 espone a OpenWebUI solo il tool pubblico `vulkan_helper`.
- 3572 esegue il loop interno; il planner decide, il controller valida.
- Il controller non deve sostituire il planner con sequenze hard-coded o
  auto-final nascosti.
- `final` puo passare solo con evidenza verificata: un `repo_read ok=True`
  deve avere contenuto reale (`content`) ricaricabile dallo stesso tool result.
- `content_preview`, path, conteggi o artifact path locali non soddisfano il
  gate di finalizzazione.
- OpenWebUI non puo aprire file locali sotto `C:\Users\...`; quindi 3571 deve
  trasportare i risultati reali dei tool riusciti dentro `tool_context_for_30b`.
- Nel payload pubblico `artifact` significa risultato reale del tool, non path
  locale.
- Stati terminali come `completed`, `max_steps_reached`,
  `blocked_needs_attention` e `failed` devono usare la stessa regola di
  trasporto: `content` compatto e `tool_context_for_30b` JSON pretty-printed
  con soli tool riusciti.
- I path dei tool repo sono relativi al root runtime `AICARMINE_LAB_REPO`, non
  alla cwd della shell Codex. Prima di diagnosticare un rigetto come
  `repo_read_path_not_from_prior_file_evidence`, verificare
  `planner-prompts/step-*-planner-payload.json -> user_payload.lab_repo` e la
  coerenza con `OPEN_TERMINAL_CWD` / `AICARMINE_OPEN_TERMINAL_WORKDIR`.

## Cosa non fare

- Non cambiare modello, ctx, max step, venv o launcher mentre si sta correggendo
  il protocollo 3571/3572, salvo evidenza diretta che il difetto stia li.
- Non reintrodurre `continuation_surface`, `call_protocol`, `call_examples`,
  raw events o diagnostica transport nella superficie OpenWebUI.
- Non usare `final_path`, `reads/*.json`, `tool-results/*.json` o altri path
  locali come sostituto del risultato inline.
