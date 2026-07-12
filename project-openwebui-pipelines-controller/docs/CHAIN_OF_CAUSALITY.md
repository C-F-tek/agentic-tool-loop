# Catena causale della conversione

## Sintomo

La conversione precedente rendeva la Pipeline un forwarder statico.

## Evidenza

Il progetto originale espone `vulkan_bridge/app.py`, che pubblica endpoint OpenWebUI-facing come `/vulkan_helper`, `/helper_for_all`, `/repo_status`, `/repo_search`, `/repo_read`, `/repo_command`.

La funzione `_build_agent_payload()` costruisce il payload per il backend 3572 e dichiara nel contratto:

```text
30B/OpenWebUI -> 3571 public tool ... -> 3572 broker -> 3572 starts the planner loop;
Vulkan/11435 is a repair/helper lane only when needed
```

## Causa

Il componente corretto da preservare e' il bridge 3571, non il helper come logica interna statica e non il broker 3572 chiamato direttamente.

## Fix minimo

Creare una Pipe OpenWebUI che:

1. chiama il modello OpenWebUI per produrre un piano JSON;
2. invia gli step al bridge pubblico `3571/vulkan_helper`;
3. lascia al bridge/broker la pianificazione interna dinamica;
4. richiama il modello OpenWebUI per generare la risposta finale dalle evidenze.

## Verifica

- `py_compile` passa.
- La Pipeline contiene chiamate a `/api/chat/completions` per planner e synth.
- La Pipeline contiene una sola URL operativa esterna configurabile: `VULKAN_BRIDGE_URL` verso `3571/vulkan_helper`.
- Non ci sono chiamate dirette hardcoded a `3572/vulkan/agent`.
