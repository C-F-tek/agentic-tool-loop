# Macro runtime test: loop payload completo

Questa directory contiene test operator-only per il runtime completo
OpenWebUI-facing:

```text
OpenWebUI/30B -> 3571 vulkan_helper -> 3572 broker -> prompt pack ->
11434 planner -> 3572 validator/tool loop -> 3572 final serializer ->
3571 public materializer -> OpenWebUI payload
```

Non viene raccolta dal gate standard `python -m pytest`, perche' il root
`pytest.ini` limita `testpaths` a `tests services`.

Avvio:

```powershell
.\macro_runtine_test\run_loop_payload_completo.ps1
```

Il lancio senza argomenti deve sempre testare tutta la matrice tool scoperta
dal runtime. Il runner rimuove esplicitamente eventuali variabili di filtro
rimaste nella sessione PowerShell (`LOOP_PAYLOAD_ONLY_TOOL`,
`LOOP_PAYLOAD_MAX_TOOLS`, `LOOP_PAYLOAD_SEED`) quando i parametri corrispondenti
non sono passati. Per limitare volontariamente la matrice usare:

```powershell
.\macro_runtine_test\run_loop_payload_completo.ps1 -OnlyTool repo_read
.\macro_runtine_test\run_loop_payload_completo.ps1 -MaxTools 3
```

Prerequisiti:

- OpenWebUI gia' attivo su `http://127.0.0.1:8080`;
- bridge 3571 gia' attivo;
- broker 3572 gia' attivo;
- dopo modifiche a `services/vulkan_bridge` o `services/aicarmine_broker`, i
  servizi 3571/3572 devono essere riavviati prima di lanciare il macro;
- `AICARMINE_LAB_REPO` del runtime e' il lab repo dedicato anche per i tool
  di scrittura.

Il test scopre dinamicamente i tool planner-internal dal runtime e dal registry
locale. Se un nuovo tool viene aggiunto senza un case macro, il test fallisce
con `missing_macro_case_for_tool`.

Definizione di copertura macro:

- `controller_preseed` a `step=0` non copre un tool target;
- la copertura di un tool target vale solo se il job history contiene, dopo una
  turn planner (`step > 0`), una decisione tool, un tool result o un guard
  tipizzato riferito a quel tool;
- la presenza del nome del tool nel payload finale o nei preseed non e'
  sufficiente;
- il macro deve provare il passaggio runtime completo: 3571 pubblico, job 3572,
  prompt pack, native schema 11434, validator/controller, tool result o guard
  tipizzato, serializer 3572 OpenWebUI-audience, payload pubblico 3571.

A fine run il macro invia unload esplicito ai modelli Ollama usati dal runtime
vivo, ricavati dal `/health` 3572 (`planner_url/planner_model` e
`ollama_task_url/ollama_task_model`). Il report contiene `ollama_unload`; se lo
scarico fallisce e non esiste gia' un failure principale, il test fallisce.

Per ogni tool coperto il macro crea un job nuovo con id `job-macro-...`.
Il `seed` rende riproducibile il sampling dei file, ma il `run_id` viene
materializzato a ogni lancio con timestamp ad alta risoluzione e GUID: i
`job_id` non devono essere riusati tra due lanci del runner. Il macro invoca
solo il tool pubblico 3571 `/vulkan_helper`, poi legge il serializer finale
3572 con `action=result` e `audience=openwebui` sullo stesso `job_id`. I due
payload devono essere lo stesso oggetto JSON dopo il parse: se 3571 aggiunge,
rimuove o cambia campi rispetto al serializer 3572 OpenWebUI-audience, il macro
fallisce. Il report salva:

- payload richiesta 3571;
- payload pubblico materializzato da 3571;
- payload serializer finale 3572 OpenWebUI-audience;
- `job.json`, `final.json`, eventi, planner prompt e planner stream del job.

Il test fallisce se non vede il prompt pack normale, native tool schema,
eventi planner/validator/tool, serializer finale, payload pubblico
materializzato e identita' tra payload serializer 3572 e payload pubblico 3571.
Non e' un test di endpoint singolo: e' un audit operator-only del loop
agentico completo gia' avviato.

Se il payload 3572 richiesto con `action=result` e `audience=openwebui`
contiene ancora `final_path`, `events_path` o
`final_path_verification.final_path`, il macro fallisce con
`3572 action=result did not honor audience=openwebui`. In quel caso il processo
3572 vivo non sta usando il serializer OpenWebUI-audience aggiornato o non e'
stato riavviato dopo le modifiche al broker.

Il payload macro non invia `function=<tool interno>` come scorciatoia. Ogni
richiesta passa dal tool pubblico `vulkan_helper`; il tool interno da coprire e'
solo un target di audit dentro la richiesta e il contesto strutturato. Il macro
controlla `job.json` e fallisce se il job non risulta creato con
`public_tool_name=vulkan_helper` o se gli argomenti originali contengono chiavi
che trasformano il case in dispatch diretto.

I target concreti dei case, inclusi path repo-relative esatti, non vengono
scritti nel testo libero `request`, perche' il controller 3572 interpreta un
path esistente nel goal come richiesta file esplicita e puo' eseguire un
`controller_preseed_file_surface` prima del planner. Il runner li invia invece
in `original_args.context`; il broker li porta nel prompt come
`explicit_request_context` e l'evidence contract li rende
`validator_admissible_repo_read_paths` quando esistono nel lab repo. Il macro
fallisce se il primo payload planner non contiene `explicit_request_context`,
se il native schema non contiene il tool target, o se `repo_read` viene coperto
da preseed invece che da una decisione planner/validator.
