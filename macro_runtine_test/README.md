# Macro runtime test: loop payload completo

Questa directory contiene un test operator-only del runtime completo
OpenWebUI-facing:

```text
OpenWebUI/30B -> 3571 vulkan_helper -> 3572 broker -> prompt pack ->
11434 planner -> 3572 validator/controller/tool loop -> 3572 final serializer ->
3571 public materializer -> OpenWebUI payload
```

Non viene raccolto dal gate standard `python -m pytest`, perche' il root
`pytest.ini` limita `testpaths` a `tests services`.

Il macro test non e' un catalogo di tool e non simula il runtime a pezzi. Usa
una richiesta operatore reale inviata al tool pubblico 3571 `/vulkan_helper`,
poi verifica sullo stesso `job_id` gli artifact prodotti dal runtime.

## Avvio

```powershell
.\macro_runtine_test\run_loop_payload_completo.ps1 -Request "analizza la repo e descrivi dettagliatamente ogni script presente nel core"
```

Con audit opzionale di un tool atteso:

```powershell
.\macro_runtine_test\run_loop_payload_completo.ps1 `
  -Request "leggi il file README.md e riporta il contenuto rilevante inline" `
  -ExpectTool repo_read
```

`-ExpectTool` non viene passato come dispatch interno e non forza il planner.
Serve solo al replay runtime per verificare, dopo il job, che quel tool sia
stato scelto, bloccato con guard tipizzato o reso indisponibile in modo
tipizzato dalla catena reale.

## Prerequisiti

- OpenWebUI gia' attivo su `http://127.0.0.1:8080`;
- bridge 3571 gia' attivo;
- broker 3572 gia' attivo;
- dopo modifiche a `services/vulkan_bridge` o `services/aicarmine_broker`, i
  servizi 3571/3572 devono essere riavviati prima di lanciare il macro;
- `AICARMINE_LAB_REPO` del runtime e' il lab repo dedicato anche per i tool di
  scrittura.

## Cosa verifica

Il macro fallisce se non vede, dagli artifact reali del job:

- creazione job tramite `public_tool_name=vulkan_helper`;
- prompt pack normale;
- native tool schema verso 11434;
- eventi lifecycle/planner/validator/tool richiesti;
- tool result o guard tipizzato quando il planner li produce;
- `compact_agent_terminal_response(..., audience="openwebui")` da 3572;
- payload pubblico 3571 uguale al serializer 3572 OpenWebUI-audience;
- payload pubblico materializzato e indicizzato;
- nessun path locale pubblico fuori da `operator_diagnostics`.

Il report salva:

- richiesta 3571;
- payload pubblico 3571;
- payload serializer finale 3572 OpenWebUI-audience;
- `job.json`;
- `final.json`;
- `events.ndjson`;
- primo planner payload;
- planner stream;
- `loop_replay_report.v1`.

## Regole

- Il macro non invia `function=<tool interno>`.
- Il macro non invia `target_internal_tool`.
- Il macro non chiama dispatcher o tool interni.
- Il macro non calcola una propria coverage.
- La verifica del flow usa il componente runtime
  `aicarmine_broker.application.replay.loop_replay`.
- La verifica della superficie pubblica usa i componenti runtime di payload
  materialization/lint.
- Se manca contenuto inline o manca un evento richiesto, il macro fallisce:
  non sostituisce il problema con preview, path locali o campi omessi.

Questo test serve a validare il sistema vivo, non singoli componenti isolati.
