# Analisi Dipendenze: dispatcher ↔ tool_dispatch

## Stato Attuale

### File: `application/tool_surface/dispatcher.py`
- Definisce `RegistryToolDispatcher`, `DispatchRequest`, `BaseTool`, `build_default_dispatcher()`
- Importa da `repo_tools`, `memory_tools`, `helper`, `tool_contract`
- **Nessuna dipendenza verso `tool_dispatch.py`**

### File: `tool_dispatch.py`
- Definisce `dispatch_tool()` e `dispatch_tool_call()`
- Importa da `application.tool_surface.dispatcher`: `DispatchRequest`, `build_default_dispatcher`
- **Nessuna dipendenza circolare reale** - è una dipendenza unidirezionale

## Verifica

```
dispatcher.py → repo_tools, memory_tools, helper, tool_contract
    ↓
tool_dispatch.py → application.tool_surface.dispatcher
    ↓
agent_entry.py → tool_dispatch, tool_selection
    ↓
planner/loop.py → tool_dispatch
```

**Nessun ciclo chiuso trovato.** La dipendenza è unidirezionale:
- `tool_dispatch.py` dipende da `dispatcher.py`
- `dispatcher.py` NON dipende da `tool_dispatch.py`

## Conclusione

**Non esistono dipendenze circolari reali tra dispatcher e tool_dispatch.**

La percezione di "dipendenza circolare" nell'analisi iniziale era errata. Il sistema usa un pattern **facade**:
- `dispatcher.py` = implementazione core (RegistryToolDispatcher)
- `tool_dispatch.py` = compatibilità layer (facade che espone `dispatch_tool`)

## Soluzione Proposta

Anche se non c'è un vero ciclo, il codice può essere migliorato con:

### 1. Dependency Injection Pattern
Invece di `build_default_dispatcher()` chiamato direttamente in `tool_dispatch.py`, usare un factory:

```python
# tool_dispatch.py
def dispatch_tool(name, args, root, allow_command=True, user_consent="", dispatcher=None):
    """Compatibility alias for dispatch_tool."""
    if dispatcher is None:
        dispatcher = build_default_dispatcher()
    return dispatcher.dispatch(DispatchRequest(...))
```

### 2. Interface Segregation
Separare la responsabilità di `build_default_dispatcher()` in un modulo dedicato:

```python
# application/tool_surface/dispatcher_factory.py
def create_dispatcher():
    """Create default dispatcher with all registered tools."""
    return RegistryToolDispatcher([...])
```

### 3. Lazy Loading
Rimuovere import diretti e usare lazy loading per evitare caricamento pesante:

```python
# tool_dispatch.py
def _get_dispatcher():
    """Lazy load dispatcher to avoid circular import risk."""
    from .application.tool_surface.dispatcher import build_default_dispatcher
    return build_default_dispatcher()
```

## Raccomandazione

**Nessun fix urgente necessario.** Il sistema funziona correttamente. I miglioramenti proposti sono opzionali per:
- Ridurre accoppiamento statico
- Migliorare testabilità (mock dispatcher)
- Prevenire futuri problemi di import