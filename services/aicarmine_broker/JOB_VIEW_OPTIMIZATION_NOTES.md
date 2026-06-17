# Job View HTML Assets Optimization

## Panoramica

Questa nota documenta l'ottimizzazione delle view HTML del job per ridurre la duplicazione di CSS/JS tra `job_html.py` e `job_planner_lab.py`.

## Stato attuale

### File coinvolti

- `services/aicarmine_broker/job_html_assets.py` - Modulo condiviso per asset CSS/JS
- `services/aicarmine_broker/job_html.py` - Renderer principale per tutte le view tranne planner-lab
- `services/aicarmine_broker/job_planner_lab.py` - Renderer per planner-lab (ora ottimizzato)

### Asset condivisi

#### `BASE_CSS` (4395 caratteri)
CSS base condiviso tra tutte le view:
- Reset CSS (`box-sizing`)
- Layout grid
- Componenti: `.card`, `.metric`, `.pill`, `.toolbar`, `.timeline`, `.step-card`
- Stili bubble chat, metric, badge stato
- Media query responsive

#### `BASE_JS` (2693 caratteri)
Utility JS base:
- `htmlEscape()` - Escape HTML
- `pretty()` - JSON.stringify indentato
- `setStatus()` - Aggiorna elemento status
- `jobPath()` - Genera URL job
- `stopPolling()` - Ferma polling
- `updateActiveJob()` - Aggiorna pannello job attivo
- `selectJob()` - Seleziona job
- `setLaunchBusy()` - Disabilita/enabled bottoni

#### `PLANNER_LAB_EXTRA_CSS` (1577 caratteri)
CSS specifico per planner-lab:
- `.planner-lab-container`
- `.planner-lab-section`
- `.planner-lab-followup-panel`
- `.planner-lab-chain`
- `.planner-lab-assessment`
- `.planner-lab-missing`
- `.planner-lab-ready`
- `.planner-lab-products`
- `.planner-lab-faq`

#### `PLANNER_LAB_JS` (3622 caratteri)
JS specifico per planner-lab:
- Variabili: `guidedConversation`, `guidedTurnCounter`, `guidedDraftText`, `guidedComposeInFlight`
- `renderPendingChat()`
- `renderChatBubble()`
- `renderMetrics()`
- `renderTopLevelSurface()`
- `renderInlineFields()`
- `renderResultRows()`
- `renderOwnerPayloadFocus()`
- `renderPriorityRows()`
- `renderArtifactRows()`
- `renderStructureRows()`
- `renderPublicToolResponse()`
- `renderPendingChat()`
- `renderChatTurn()`
- `renderSteps()`
- `renderCodeProducts()`
- `copyCandidate()`
- `copyApplyToolCall()`
- `applyCandidate()`
- `captureGuidedDraft()`
- `composeFromPayload()`
- `renderGuidedConversation()`
- `renderGuidedTurn()`
- `renderLab()`

## Modifiche apportate

### `job_planner_lab.py`

**Prima:**
- CSS inline completo (~1500 righe)
- JS inline completo (~800 righe)
- Funzioni duplicate: `htmlEscape`, `pretty`, `setStatus`, `jobPath`, `stopPolling`, `updateActiveJob`

**Dopo:**
- Importa `BASE_CSS`, `BASE_JS`, `PLANNER_LAB_EXTRA_CSS`, `PLANNER_LAB_JS` da `job_html_assets.py`
- CSS combinato: `{css}` nel template
- JS combinato: `{js}` nel template
- Nessuna funzione comune duplicata

**Import aggiunti:**
```python
from .job_html_assets import BASE_CSS, BASE_JS, PLANNER_LAB_EXTRA_CSS, PLANNER_LAB_JS
```

**Funzione `_html_page` modificata:**
```python
def _html_page(title: str, body: str, *, initial_job_id: str = "") -> str:
    initial = json.dumps(str(initial_job_id or ""))
    css = BASE_CSS + PLANNER_LAB_EXTRA_CSS
    js = BASE_JS + PLANNER_LAB_JS
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
{css}
</style>
</head>
<body>
{body}
<script>
const initialJobId = {initial};
{js}
</script>
...
```

## Benefici

1. **Riduzione duplicazione**: CSS/JS comuni ora in un unico luogo
2. **Manutenibilità**: Cambiamenti CSS/JS in un solo file
3. **Consistenza**: Tutte le view usano gli stessi asset
4. **Dimensioni**: Riduzione del codice duplicato

## Verifica

```bash
# Compilazione
python -m py_compile services/aicarmine_broker/job_planner_lab.py

# Import asset
python -c "from aicarmine_broker.job_html_assets import BASE_CSS, BASE_JS, PLANNER_LAB_EXTRA_CSS, PLANNER_LAB_JS; print('Assets OK')"
```

## Prossimi passi

1. **Pannello follow-up**: Aggiungere UI chiara "Rispondi / chiedi integrazione" sotto la risposta terminale nel planner-lab
2. **Persistenza thread**: Implementare `operator-thread.ndjson` per persistenza job-local
3. **Endpoint thread**: Aggiungere GET/POST `/jobs/{job_id}/planner-lab/thread`
4. **Chiarezza UI**: Mostrare separatamente: Risposta, Valutazione payload, Cosa manca, Domande successive, Patch/apply readiness, Code products

## Note

- Non introdurre `/static/*.css` o `/static/*.js`: il contratto MCP è "local renderer no HTTP"
- Gli asset rimangono stringhe Python inline per compatibilità offline/MCP
- Le funzioni specifiche del planner-lab (`startPlannerJob`, `loadJob`, `startPolling`, `renderLab`, `compose/apply/guidedConversation`) rimangono nel file
