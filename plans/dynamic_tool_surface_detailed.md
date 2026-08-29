# Dynamic Tool Surface — Dettagli Implementativi di `dynamic_controller.py`

## Obiettivo del Modulo

Il `DynamicToolSurfaceController` è il cuore del sistema di suggerimento dinamico degli strumenti. A differenza del statico [`PLANNER_INTERNAL_TOOLS`](services/aicarmine_broker/tool_schemas.py:645), questo controller calcola **per ogni turno** quali strumenti sono rilevanti basandosi su:

1. Stato attuale dell'evidence contract
2. Storico dei turni (quali file sono stati letti, quali tool sono stati usati)
3. Classificazione semantica del goal
4. Pattern di rejection dal validator

---

## Struttura della Classe

```python
"""Dynamic tool surface controller for planner loop."""

from __future__ import annotations

from typing import Any
from ...tool_contract import normalize_tool_name


class DynamicToolSurfaceController:
    """Calcola suggerimenti dinamici per gli strumenti disponibili nel turno corrente.
    
    Il controller analizza lo stato del loop e produce una lista ordinata di 
    tool suggestions con punteggio di rilevanza. I suggerimenti non bloccano 
    nulla — sono hint che il planner può ignorare se ha buone ragioni.
    """
    
    # Mapping tra tipo di file letto e tool correlati
    _FILE_TYPE_TOOL_MAP = {
        ".py": ["repo_ruff_check", "repo_pyright_check"],  # Python → linting/type check
        ".sh": ["repo_shellcheck"],                          # Shell → shellcheck
        ".json": ["repo_jq_query"],                         # JSON → jq query
        ".yaml": [],                                        # YAML/YML → no specific tool yet
        ".yml": [],                                         # YML → no specific tool yet
        ".toml": [],                                        # TOML → no specific tool yet
        ".md": [],                                          # Markdown → no specific tool yet
        ".txt": [],                                         # Text → no specific tool yet
        ".xml": [],                                         # XML → no specific tool yet
        ".html": [],                                        # HTML → no specific tool yet
        ".css": [],                                         # CSS → no specific tool yet
        ".js": ["repo_semgrep_scan"],                      # JS → semgrep for security scan
        ".ts": ["repo_semgrep_scan"],                      # TS → semgrep for security scan
        ".go": ["repo_command"],                            # Go → go vet/golangci-lint via command
        ".rs": ["repo_command"],                            # Rust → cargo check/rustfmt via command
        ".c": ["repo_command"],                             # C → gcc -fsyntax-only via command
        ".h": [],                                           # Header → no specific tool yet
    }
```

---

## Metodo Principale: `suggest_tools()`

Questo è il punto di ingresso principale. Calcola tutti i suggerimenti per un dato stato del loop.

```python
def suggest_tools(
    self,
    goal: str,
    evidence_contract: dict[str, Any],
    history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Calcola suggerimenti dinamici per gli strumenti disponibili nel turno corrente.
    
    Args:
        goal: Goal dell'utente (es. "analizza services/aicarmine_broker")
        evidence_contract: Contract attuale con candidate_next_actions, coverage_satisfied, etc.
        history: Storico dei turni precedenti
        
    Returns:
        Lista ordinata di dicts con struttura:
        {
            "tool": "nome_tool",
            "score": 95,           # Punteggio 0-100
            "reason": "lettura file .py completata → suggerisco linting",
            "category": "post-read-suggestion",  # Per debugging
        }
    """
    suggestions = []
    
    # Step 1: Suggerimenti basati su goal classification
    suggestions.extend(self._suggest_from_goal_classification(evidence_contract))
    
    # Step 2: Suggerimenti basati su tipo di file letto
    suggestions.extend(self._suggest_from_read_history(history))
    
    # Step 3: Suggerimenti basati su rejection patterns
    suggestions.extend(self._suggest_after_rejections(history))
    
    # Step 4: Suggerimenti basati su progress state
    suggestions.extend(self._suggest_from_progress_state(goal, evidence_contract, history))
    
    # Deduplica e ordina per score
    return self._dedupe_and_sort(suggestions)
```

---

## Metodo 1: `_suggest_from_goal_classification()`

Analizza la [`semantic_goal_classification`](services/aicarmine_broker/application/prompt/evidence_contract.py:10) dall'evidence contract e suggerisce strumenti base appropriati.

```python
def _suggest_from_goal_classification(
    self,
    evidence_contract: dict[str, Any],
) -> list[dict[str, Any]]:
    """Suggerisci strumenti in base alla classificazione semantica del goal."""
    semantic = evidence_contract.get("semantic_goal_classification", {})
    if not isinstance(semantic, dict):
        return []
    
    goal_class = str(semantic.get("class") or "").strip()
    tool_list = self._GOAL_CLASS_TOOL_MAP.get(goal_class, [])
    
    if not tool_list:
        return []
    
    return [
        {
            "tool": name,
            "score": 50,  # Score base per goal-class suggestion
            "reason": f"Goal classification '{goal_class}' suggests this tool",
            "category": "goal-class-suggestion",
        }
        for name in tool_list
    ]


# Mapping tra goal class e strumenti base suggeriti
_GOAL_CLASS_TOOL_MAP = {
    "analysis_only": ["repo_status", "repo_tree", "repo_search"],
    "code_product_report": [
        "repo_read", "repo_list_files", "repo_search", 
        "repo_propose_code_edit", "planner_scratchpad_write"
    ],
    "apply_write": [
        "repo_read", "repo_list_files", "repo_search",
        "repo_apply_patch", "repo_validate", "repo_command"
    ],
    "code_security_analysis": [
        "repo_semgrep_scan", "repo_ast_grep_search", "repo_read"
    ],
    "generic": ["repo_capabilities", "vulkan_helper"],
}
```

### Esempio di Output

Per un goal come `"analizza services/aicarmine_broker/planner.py"` con `goal_class=analysis_only`:
```json
[
  {"tool": "repo_status", "score": 50, "reason": "Goal classification 'analysis_only' suggests...", "category": "goal-class-suggestion"},
  {"tool": "repo_tree", "score": 50},
  {"tool": "repo_search", "score": 50}
]
```

---

## Metodo 2: `_suggest_from_read_history()` — Il Cuore della Dynamic Surface

Questo è il metodo più importante. Analizza quali file sono stati letti nei turni precedenti e suggerisce strumenti correlati al tipo di file.

```python
def _suggest_from_read_history(
    self,
    history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Dai file letti nei turni precedenti, suggerisci tool correlati."""
    # Estrai i path dei file letti con successo
    read_paths = self._extract_successful_read_paths(history)
    
    suggestions = []
    for path in read_paths:
        suffix = self._get_file_suffix(path)
        
        if not suffix or suffix not in self._FILE_TYPE_TOOL_MAP:
            continue
        
        correlated_tools = self._FILE_TYPE_TOOL_MAP[suffix]
        for tool_name in correlated_tools:
            # Controlla se questo tool è già stato usato dopo la lettura
            if not self._is_tool_already_used_after_read(tool_name, path, history):
                suggestions.append({
                    "tool": tool_name,
                    "score": 75,  # Score alto perché basato su evidenza concreta
                    "reason": f"File '{path}' ({suffix}) letto → {tool_name} potrebbe essere utile",
                    "category": "post-read-suggestion",
                    "trigger_path": path,
                })
    
    return suggestions


def _extract_successful_read_paths(self, history: list[dict]) -> set[str]:
    """Estrai i path dei file letti con successo dai turni precedenti."""
    paths = set()
    for item in history:
        if not isinstance(item, dict):
            continue
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        if result.get("ok") is not True:
            continue
        tool = str(result.get("tool") or "").strip().lower()
        
        if tool == "repo_read":
            # Estrai il path dal risultato o dalla decisione
            path = result.get("path") or result.get("repo_path")
            if path and path != ".":
                paths.add(str(path))
        elif tool == "planner_scratchpad_write":
            # Controlla se è stato scritto un code_product_build_state
            text = result.get("text") or result.get("content") or ""
            if "code_product_build_state" in text:
                try:
                    import json
                    payload = json.loads(text)
                    target_file = payload.get("target_file", "")
                    if target_file:
                        paths.add(target_file)
                except Exception:
                    pass
    
    return paths


def _get_file_suffix(self, path: str) -> str:
    """Estrai l'estensione del file."""
    path_lower = path.lower()
    for suffix in self._FILE_TYPE_TOOL_MAP.keys():
        if path_lower.endswith(suffix):
            return suffix
    return ""


def _is_tool_already_used_after_read(
    self, 
    tool_name: str, 
    read_path: str, 
    history: list[dict]
) -> bool:
    """Controlla se questo tool è già stato usato dopo la lettura di questo path."""
    # Cerca pattern: repo_read → tool_name nella stessa finestra temporale
    found_reads = False
    for item in reversed(history[-10:] if len(history) >= 10 else history):
        if not isinstance(item, dict):
            continue
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        
        tool = str(result.get("tool") or decision.get("tool") or "").strip().lower()
        
        if tool == "repo_read":
            path = result.get("path") or result.get("repo_path")
            if path == read_path:
                found_reads = True
        
        elif tool == normalize_tool_name(tool_name):
            if found_reads:
                return True
    
    return False
```

### Esempio di Output

Dopo aver letto `services/aicarmine_broker/planner.py`:
```json
[
  {
    "tool": "repo_ruff_check",
    "score": 75,
    "reason": "File 'services/aicarmine_broker/planner.py' (.py) letto → repo_ruff_check potrebbe essere utile",
    "category": "post-read-suggestion",
    "trigger_path": "services/aicarmine_broker/planner.py"
  },
  {
    "tool": "repo_pyright_check", 
    "score": 75,
    "reason": "File 'services/aicarmine_broker/planner.py' (.py) letto → repo_pyright_check potrebbe essere utile",
    "category": "post-read-suggestion",
    "trigger_path": "services/aicarmine_broker/planner.py"
  }
]
```

---

## Metodo 3: `_suggest_after_rejections()`

Analizza le rejection signatures dal [`controller_guard`](services/aicarmine_broker/application/controller/guards.py:71) e suggerisce alternative.

```python
def _suggest_after_rejections(
    self,
    history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Dopo una rejection del validator, suggerisci tool alternativi."""
    suggestions = []
    
    # Trova l'ultima rejection
    last_rejection = self._find_last_rejection(history)
    if not last_rejection:
        return []
    
    rejected_tool = str(last_rejection.get("rejected_tool") or "").strip()
    violations = last_rejection.get("violations", [])
    
    for violation in violations:
        violation_text = str(violation).lower()
        
        if "repo_read_already_successful" in violation_text:
            suggestions.append({
                "tool": "planner_scratchpad_write",
                "score": 80,
                "reason": f"Rejection: {violation}. Suggerisco di scrivere un progresso invece di ripetere la lettura.",
                "category": "rejection-alternative",
            })
            
        elif "missing_path_or_paths_items" in violation_text:
            suggestions.append({
                "tool": "repo_list_files",
                "score": 65,
                "reason": f"Rejection: {violation}. Suggerisco prima di listare i file per identificare il path corretto.",
                "category": "rejection-alternative",
            })
            
        elif "no_progress_made" in violation_text or "already_read" in violation_text:
            suggestions.extend([
                {"tool": "repo_propose_code_edit", "score": 70},
                {"tool": "final_answer", "score": 60} if self._is_final_ready(history) else None,
            ])
    
    return [s for s in suggestions if s is not None]


def _find_last_rejection(self, history: list[dict]) -> dict | None:
    """Trova l'ultima rejection dal controller guard."""
    for item in reversed(history):
        if not isinstance(item, dict):
            continue
        
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        
        # Cerca nel risultato del tool o nella decisione
        violations = result.get("violations") or []
        rejected_decision = result.get("rejected_decision") or {}
        
        if violations and rejected_decision:
            return {
                "rejected_tool": str(rejected_decision.get("tool") or ""),
                "violations": violations,
            }
    
    return None


def _is_final_ready(self, history: list[dict]) -> bool:
    """Controlla se il planner è pronto per final (tutte le letture fatte)."""
    read_paths = set()
    for item in history:
        if not isinstance(item, dict):
            continue
        result = item.get("tool_result", {})
        if result.get("ok") is True and result.get("tool") == "repo_read":
            path = result.get("path") or ""
            if path:
                read_paths.add(path)
    
    # Se abbiamo letto almeno 3 file diversi e non ci sono loop di lettura
    recent_reads = [i for i in reversed(history[-5:]) 
                    if isinstance(i, dict) and i.get("tool_result", {}).get("tool") == "repo_read"]
    unique_recent = len(set(r.get("tool_result", {}).get("path") for r in recent_reads))
    
    return len(read_paths) >= 3 and unique_recent <= 1  # Non più di 1 ripetizione
```

---

## Metodo 4: `_suggest_from_progress_state()`

Analizza lo stato del progresso e suggerisce azioni appropriate.

```python
def _suggest_from_progress_state(
    self,
    goal: str,
    evidence_contract: dict[str, Any],
    history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Suggerisci strumenti basati sullo stato attuale del progresso."""
    suggestions = []
    
    # Step 1: Controlla se c'è un required_next_tool_call pendente
    required = evidence_contract.get("required_next_tool_call", {})
    if isinstance(required, dict) and required.get("validated"):
        tool_name = str(required.get("tool") or "").strip()
        if tool_name:
            suggestions.append({
                "tool": tool_name,
                "score": 95,  # Score massimo perché è richiesto dal contract
                "reason": f"required_next_tool_call dal contract: {tool_name}",
                "category": "contract-required",
            })
    
    # Step 2: Controlla se coverage non è soddisfatto
    coverage_satisfied = evidence_contract.get("coverage_satisfied") is True
    missing_paths = evidence_contract.get("missing_owner_paths", [])
    
    if not coverage_satisfied and missing_paths:
        for path in (missing_paths[:3] if isinstance(missing_paths, list) else []):
            suggestions.append({
                "tool": "repo_read",
                "score": 85,
                "reason": f"Coverage non soddisfato. Path mancante da leggere: {path}",
                "category": "coverage-mandatory",
                "trigger_path": path,
            })
        
        # Se repo_read non funziona, suggerisci search come alternativa
        suggestions.append({
            "tool": "repo_search",
            "score": 60,
            "reason": "Se repo_read fallisce, prova con repo_search per trovare il file.",
            "category": "coverage-alternative",
        })
    
    # Step 3: Controlla se ci sono candidate_next_actions estraibili
    candidates = evidence_contract.get("candidate_next_actions", [])
    if isinstance(candidates, list) and len(candidates) > 0:
        first_candidate = candidates[0] if isinstance(candidates[0], dict) else {}
        tool_name = str(first_candidate.get("tool") or "").strip()
        if tool_name:
            suggestions.append({
                "tool": tool_name,
                "score": 70,
                "reason": f"Primo candidate_next_action dal contract: {tool_name}",
                "category": "contract-candidate",
            })
    
    return suggestions


def _check_final_preconditions(self, goal: str, evidence_contract: dict[str, Any]) -> tuple[bool, list[str]]:
    """Verifica tutte le pre-condizioni per permettere la chiamata final.
    
    Returns:
        Tuple di (precondizioni_soddisfate, lista_motivi_non_soddisfatti)
    """
    reasons_not_ready = []
    
    # Pre-condizione 1: Coverage letture soddisfatte
    coverage_satisfied = evidence_contract.get("coverage_satisfied") is True
    if not coverage_satisfied:
        reasons_not_ready.append("coverage_satisfied=false — non tutte le letture richieste sono state completate")
    
    # Pre-condizione 2: No missing owner paths
    missing_paths = evidence_contract.get("missing_owner_paths", [])
    if isinstance(missing_paths, list) and len(missing_paths) > 0:
        reasons_not_ready.append(f"missing_owner_paths={missing_paths[:5]} — path mancanti da leggere")
    
    # Pre-condizione 3: No required_next_tool_call pendente
    required = evidence_contract.get("required_next_tool_call", {})
    if isinstance(required, dict) and required.get("validated"):
        reasons_not_ready.append(f"required_next_tool_call pendente: {required.get('tool')}")
    
    # Pre-condizione 4: Planner può scegliere final
    final_allowed = evidence_contract.get("finalization_contract", {}).get("final_allowed") is True
    if not final_allowed:
        reasons_not_ready.append("finalization_contract.final_allowed=false")
    
    # Pre-condizione 5: Non in rewrite_latch con tool insoddisfatto
    latch = str(evidence_contract.get("final_rewrite_latch") or "").strip()
    if latch and latch != "rewrite_required":
        reasons_not_ready.append(f"in final_rewrite_latch state: {latch}")
    
    return (len(reasons_not_ready) == 0), reasons_not_ready
```

---

## Metodo di Supporto: `_dedupe_and_sort()`

Deduplica e ordina i suggerimenti per score.

```python
def _dedupe_and_sort(
    self, 
    suggestions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Deduplica e ordina i suggerimenti per punteggio."""
    seen_tools = set()
    unique_suggestions = []
    
    for s in sorted(suggestions, key=lambda x: -x["score"]):
        tool_name = s["tool"]
        
        # Se abbiamo già un suggerimento per questo tool, mantieni il più alto score
        if tool_name not in seen_tools:
            seen_tools.add(tool_name)
            unique_suggestions.append(s)
        else:
            # Aggiorna solo se il nuovo score è significativamente diverso
            existing = next((item for item in unique_suggestions if item["tool"] == tool_name), None)
            if existing and abs(existing["score"] - s["score"]) > 15:
                existing.update(s)
    
    return unique_suggestions[:8]  # Max 8 suggerimenti
```

---

## Integrazione con Evidence Builder (`builder.py`)

Nel [`EvidenceBuilder.build()`](services/aicarmine_broker/application/evidence/builder.py:416), dopo aver calcolato `_candidate_actions_from_evidence`, integrare:

```python
# Dopo linea ~500+ dove _candidate_actions_from_evidence viene chiamato
from .application.tool_surface.dynamic_controller import DynamicToolSurfaceController

dynamic_controller = DynamicToolSurfaceController()
dynamic_suggestions = dynamic_controller.suggest_tools(
    goal=goal,
    evidence_contract=built_contract,
    history=history,
)

built_contract["dynamic_tool_suggestions"] = {
    "schema": "planner_dynamic_tool_suggestion.v1",
    "tools": [s["tool"] for s in dynamic_suggestions],
    "details": dynamic_suggestions[:4],  # Dettagli completi per i top-4
    "reason": f"Dynamic suggestion based on loop state ({len(dynamic_suggestions)} suggestions)",
}
```

### Schema del Campo nel Prompt Keep Keys

Aggiungere a [`EVIDENCE_PROMPT_KEEP_KEYS`](services/aicarmine_broker/application/prompt/evidence_contract.py:9):

```python
DYNAMIC_TOOL_SUGGESTIONS_KEY = "dynamic_tool_suggestions",
```

---

## Integrazione con Turn Surface Policy (`turn_surface_policy.py`)

Nel metodo [`tools_for_turn()`](services/aicarmine_broker/application/tool_surface/turn_surface_policy.py:73), dopo la catena di if esistente ma prima della logica base tools:

```python
# Dopo _contract_final_required_now check (linea ~115)
# Prima di semantic_goal_classification (linea ~120)

# NEW: Considera dynamic tool suggestions se presenti
dynamic_suggestions = contract.get("dynamic_tool_suggestions")
if isinstance(dynamic_suggestions, dict) and dynamic_suggestions.get("tools"):
    suggested_tools = [str(t).strip() for t in dynamic_suggestions["tools"] if str(t).strip()]
    if suggested_tools:
        # Usa i suggerimenti come filtro prioritizzato
        names = set(self._base_tools_for_goal_class(...))  # Base tools esistenti
        
        # Aggiungi solo i suggeriti che non sono già nei base tools
        additional = {t for t in suggested_tools if t not in names}
        names.update(additional)
        
        self._add_keyword_tools(names, goal)
        return self._ordered(names)
```

---

## Integrazione con Planner Loop (`planner.py`)

In [`_build_planner_user_payload()`](services/aicarmine_broker/planner.py:1408), aggiungere al payload utente:

```python
def _build_planner_user_payload(
    job_id: str, state: dict[str, Any], step: int, 
    history: list[dict[str, Any]], tool_manifest: list[dict[str, Any]],
    evidence_contract: dict[str, Any], planner_memory: dict[str, Any],
    intrinsic_context: dict[str, Any], last_tool_result: dict[str, Any],
    native_tools_schema: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    
    # ... codice esistente ...
    
    # NEW: Estrai dynamic suggestions dal contract
    dynamic_suggestions = evidence_contract.get("dynamic_tool_suggestions", {})
    suggestion_text = ""
    if isinstance(dynamic_suggestions, dict):
        tools_list = dynamic_suggestions.get("tools", [])
        details = dynamic_suggestions.get("details", [])
        
        if tools_list:
            suggestion_text = (
                f"\n\n=== STRUMENTI SUGGERITI DINAMICAMENTE ===\n"
                f"Suggeriti: {', '.join(str(t) for t in tools_list[:6])}\n"
            )
            if details:
                for d in details[:3]:
                    reason = d.get("reason", "")
                    score = d.get("score", 0)
                    suggestion_text += f"[Score:{score}] {d['tool']}: {reason}\n"
    
    # Passa suggestion_text al prompt utente
```

---

## Esempio di Flusso Completo

### Scenario: Goal "analizza services/aicarmine_broker/planner.py"

**Turno 1**: Planner chiama `repo_read` su planner.py
- `_suggest_from_read_history()` calcola: `[{"tool": "repo_ruff_check", "score": 75}, {"tool": "repo_pyright_check", "score": 75}]`

**Evidence Contract dopo Turno 1**:
```json
{
  "semantic_goal_classification": {"class": "analysis_only"},
  "coverage_satisfied": false,
  "missing_owner_paths": ["services/aicarmine_broker/config/models.py"],
  "dynamic_tool_suggestions": {
    "schema": "planner_dynamic_tool_suggestion.v1",
    "tools": ["repo_ruff_check", "repo_pyright_check", "repo_read"],
    "details": [
      {"tool": "repo_ruff_check", "score": 75, "reason": ".py letto → linting utile"}
    ]
  }
}
```

**Turno 2**: Planner vede i suggerimenti e decide di leggere config/models.py (perché missing_owner_paths)
- Dopo lettura, nuovi suggerimenti: `[{"tool": "repo_ruff_check", "score": 80}]`

**Turno 3**: Planner potrebbe scegliere `final_answer` se `_check_final_preconditions()` restituisce `(True, [])`

---

## Casi Edge da Gestire

| Caso | Comportamento |
|------|---------------|
| Planner ignora tutti i suggerimenti | Nessun problema — i base tools rimangono disponibili |
| Troppi file letti (>50) | Limita a max 8 suggerimenti totali |
| File non mappati nel FILE_TYPE_TOOL_MAP | Ignorati silenziosamente |
| Goal class sconosciuta | Usa default: discovery tools + capabilities |
| History vuota (primo turno) | Solo goal-class suggestions |
