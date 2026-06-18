"""Orientation model selector isolated module.

Autonomous module for bounded AI calls that can only return candidate_ids
belonging to the pool provided by the controller.

No imports from planner.py or loop.py.
No filesystem access, no dispatch, no events, no state modification.
"""
from __future__ import annotations

import json
from typing import Any


PostJson = Any  # type: ignore[assignment]


def sanitize_orientation_selection(
    value: Any,
    *,
    valid_candidate_ids: set[str],
    max_selected: int,
) -> dict[str, Any]:
    """Sanitize model response for orientation selection.

    Contract:
    - accetta soltanto un dict;
    - decision deve essere select;
    - selected_candidate_ids deve essere una lista;
    - normalizza in stringhe non vuote;
    - rimuove duplicati preservando l'ordine;
    - separa unknown_candidate_ids;
    - conserva soltanto ID presenti in valid_candidate_ids;
    - applica max_selected;
    - non ricostruisce path;
    - non aggiunge candidate mancanti;
    - non sceglie fallback;
    - nessun ID valido => ok=false;
    - backend error => ok=false;
    - JSON invalido => ok=false;
    - non solleva eccezioni per output modello invalido.

    Args:
        value: Il valore restituito dal modello (deve essere un dict).
        valid_candidate_ids: Set di candidate_id validi.
        max_selected: Massimo numero di candidati da selezionare.

    Returns:
        Dict con schema orientamento_model_selection.v1.
    """
    result: dict[str, Any] = {
        "schema": "orientation_model_selection.v1",
        "ok": False,
        "status": "invalid",
        "selected_candidate_ids": [],
        "unknown_candidate_ids": [],
        "duplicate_candidate_ids": [],
        "rationale": "",
        "confidence": None,
        "planner_model": "",
        "planner_url": "",
        "timeout_seconds": 0,
    }

    # Non è un dict => invalid
    if not isinstance(value, dict):
        result["rationale"] = "non_dict_input"
        return result

    # Estrai decision
    decision = value.get("decision")
    if not isinstance(decision, str) or decision != "select":
        result["rationale"] = "decision_not_select"
        return result

    # Estrai selected_candidate_ids
    raw_selected = value.get("selected_candidate_ids")
    if not isinstance(raw_selected, list):
        result["rationale"] = "selected_candidate_ids_not_list"
        return result

    # Normalizza in stringhe non vuote, rimuovi duplicati preservando ordine
    seen: set[str] = set()
    normalized: list[str] = []
    duplicates: list[str] = []
    unknown: list[str] = []

    for item in raw_selected:
        if item is None:
            continue
        item_str = str(item).strip()
        if not item_str:
            continue
        if item_str in seen:
            duplicates.append(item_str)
        else:
            seen.add(item_str)
            normalized.append(item_str)

    # Conserva soltanto ID presenti in valid_candidate_ids
    filtered: list[str] = []
    for id_str in normalized:
        if id_str in valid_candidate_ids:
            filtered.append(id_str)
        else:
            unknown.append(id_str)

    # Applica max_selected
    selected = filtered[:max_selected]

    # Estrai altri campi opzionali
    rationale = value.get("rationale", "")
    if not isinstance(rationale, str):
        rationale = ""
    confidence = value.get("confidence")
    if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
        confidence = None
    planner_model = value.get("planner_model", "")
    if not isinstance(planner_model, str):
        planner_model = ""
    planner_url = value.get("planner_url", "")
    if not isinstance(planner_url, str):
        planner_url = ""
    timeout_seconds = value.get("timeout_seconds", 0)
    if not isinstance(timeout_seconds, int):
        timeout_seconds = 0

    # Ok solo se abbiamo almeno un ID valido selezionato
    if not selected:
        result["ok"] = False
        result["rationale"] = "no_valid_candidates_selected"
        return result

    result["ok"] = True
    result["status"] = "ready"
    result["selected_candidate_ids"] = selected
    result["unknown_candidate_ids"] = unknown
    result["duplicate_candidate_ids"] = duplicates
    result["rationale"] = rationale
    result["confidence"] = confidence
    result["planner_model"] = planner_model
    result["planner_url"] = planner_url
    result["timeout_seconds"] = timeout_seconds

    return result


def controller_orientation_model_select(
    *,
    goal: str,
    semantic_intent: dict[str, Any],
    candidates: list[dict[str, Any]],
    post_json: PostJson,
    planner_url: str,
    planner_model: str,
    keep_alive: str,
    timeout_seconds: int,
    max_selected: int,
) -> dict[str, Any]:
    """Call orientation model selector for bounded candidate selection.

    Contract:
    - format=json;
    - stream=false;
    - think=false;
    - temperature=0;
    - nessun tool schema;
    - nessuna tool call;
    - nessun file content;
    - nessuna history completa;
    - soltanto goal bounded, semantic_intent compatta e candidate pool;
    - il modello non deve rispondere al task;
    - il modello non deve generare path;
    - il modello non deve generare tool;
    - il modello deve scegliere soltanto candidate_id.

    Args:
        goal: Goal del job.
        semantic_intent: Intent semantico compatto.
        candidates: Pool di candidati.
        post_json: Callable per POST a Ollama.
        planner_url: URL del planner.
        planner_model: Modello del planner.
        keep_alive: Keep alive per Ollama.
        timeout_seconds: Timeout della chiamata.
        max_selected: Massimo candidati da selezionare.

    Returns:
        Dict con schema orientamento_model_selection.v1.
    """
    result: dict[str, Any] = {
        "schema": "orientation_model_selection.v1",
        "ok": False,
        "status": "unavailable",
        "selected_candidate_ids": [],
        "unknown_candidate_ids": [],
        "duplicate_candidate_ids": [],
        "rationale": "",
        "confidence": None,
        "planner_model": "",
        "planner_url": "",
        "timeout_seconds": 0,
    }

    # Valid candidate ids dai candidates
    valid_candidate_ids: set[str] = {
        str(c.get("candidate_id") or "")
        for c in candidates
        if isinstance(c, dict) and c.get("candidate_id")
    }

    if not valid_candidate_ids:
        result["rationale"] = "no_valid_candidates_in_pool"
        return result

    # Costruisci prompt bounded
    # Nessun tool schema, nessuna tool call, nessun file content, nessuna history completa
    prompt_text = (
        f"Select only candidate_ids from this pool for goal: {goal!r}. "
        f"Semantic intent: {json.dumps(semantic_intent, ensure_ascii=False)[:500]!r}. "
        f"Available candidate_ids: {', '.join(valid_candidate_ids)[:200]!r}. "
        f"Respond ONLY with JSON: {{\"decision\": \"select\", \"selected_candidate_ids\": [...]}}. "
        f"Do NOT generate paths, tools, or explanations."
    )

    # Request body
    request_body: dict[str, Any] = {
        "model": planner_model,
        "messages": [
            {
                "role": "system",
                "content": "You are an orientation model selector. Choose candidate_ids only. Respond with valid JSON only.",
            },
            {
                "role": "user",
                "content": prompt_text,
            },
        ],
        "format": "json",
        "stream": False,
        "think": False,
        "temperature": 0,
    }

    # POST
    try:
        response = post_json(planner_url, request_body, timeout_seconds)
    except Exception:
        result["rationale"] = "backend_error"
        return result

    if not isinstance(response, dict):
        result["rationale"] = "response_not_dict"
        return result

    # Sanitize
    return sanitize_orientation_selection(
        response,
        valid_candidate_ids=valid_candidate_ids,
        max_selected=max_selected,
    )