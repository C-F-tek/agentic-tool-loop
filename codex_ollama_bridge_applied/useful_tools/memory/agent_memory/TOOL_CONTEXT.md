# ia_carmine/memory/agent_memory context

## Role

`ia_carmine/memory/agent_memory` owns policy and access logic for memory used by IA-Carmine runs. It must keep a hard separation between runtime scratch memory and persistent project memory.

## Memory classes

```text
operational memory -> run-scoped scratch state, writable by runtime, not Git-trackable
persistent memory  -> historical/project memory, read-only by default, explicit write required
```

Typical paths:

```text
output/ai_runtime_memory/operational_context.sqlite
indexAI/agent_memory/agent_memory.sqlite
```

## Responsibilities

- Evaluate memory routing policy.
- Provide SQLite-backed runtime memory access.
- Build memory inventory artifacts for startup context.
- Search operational/persistent facts when requested through brokered tools.
- Prevent silent writes to persistent memory.

## Canonical command surface

Use through `ia_carmine` dispatcher:

```powershell
python -m ia_carmine.cli runtime_sqlite_memory ...
python -m ia_carmine.cli agent_runtime_sqlite_memory ...
python -m ia_carmine.cli agent_memory_routing_policy ...
python -m ia_carmine.cli build_agent_memory_inventory ...
python -m ia_carmine.cli review_agent_memory ...
```

## Guardrails

- Do not commit SQLite databases.
- Do not treat chat memory as project memory.
- Do not write persistent memory unless explicit confirmation is present.
- Report whether a write happened using structured guardrails.
- Keep FTS/search results as evidence, not as automatic patch targets.

## Extension notes

Add new memory features only if they preserve operational/persistent separation. Prefer policy + report artifacts over direct source mutation.
