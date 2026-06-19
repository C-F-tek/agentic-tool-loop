"""Orientation model selector isolated module.

Autonomous module for bounded AI calls that can only return candidate_ids
belonging to the pool provided by the controller.

No imports from planner.py or loop.py.
No filesystem access, no dispatch, no events, no state modification.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


PostJson = Callable[
    [str, dict[str, Any], int],
    dict[str, Any],
]


def _extract_orientation_response_object(
    response: Any,
) -> tuple[dict[str, Any] | None, str]:
    """Extract Ollama response object from envelope.

    Contract:
    - se response non è dict: restituisce (None, "response_not_dict");
    - se response contiene già una decisione top-level valida: può restituire direttamente;
    - altrimenti estrae testo in quest'ordine:
      response["response"]
      response["message"]["content"]
      response["partial_content"]
    - se il testo è vuoto: restituisce (None, "empty_model_content");
    - esegue json.loads sul testo completo;
    - accetta soltanto un oggetto JSON dict;
    - JSON invalido: restituisce (None, "invalid_json_response");
    - JSON valido ma non dict: restituisce (None, "json_response_not_object");
    - non recuperare oggetti embedded da prosa;
    - non usare regex;
    - non fare JSON repair;
    - non sollevare eccezioni per output modello invalido.
    """
    if not isinstance(response, dict):
        return None, "response_not_dict"

    # Prova a restituire direttamente se è già un decision object
    if response.get("decision") == "select":
        return response, "direct_decision"

    # Estrai testo in ordine
    text = (
        response.get("response")
        or response.get("message", {}).get("content")
        or response.get("partial_content")
        or ""
    )

    if not text:
        return None, "empty_model_content"

    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return None, "invalid_json_response"

    if not isinstance(decoded, dict):
        return None, "json_response_not_object"

    return decoded, "parsed_json_object"


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
    if not isinstance(confidence, bool) and (not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1):
        confidence = None

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

    # Preserva ordine dei candidati
    ordered_candidate_ids: list[str] = []
    seen_candidate_ids: set[str] = set()
    prompt_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        cid = str(candidate.get("candidate_id") or "")
        if cid and cid not in seen_candidate_ids:
            seen_candidate_ids.add(cid)
            prompt_candidates.append({
                "candidate_id": cid,
                "kind": candidate.get("kind", "file"),
                "candidate_class": candidate.get("candidate_class", "root_doc"),
                "static_rank": candidate.get("static_rank", 0),
                "signals": [
                    s for s in (candidate.get("signals") or [])
                    if isinstance(s, str) and s and len(s) <= 80
                ][:8],
            })

    # Bound goal
    goal_bounded = str(goal)[:4000]

    # Bound semantic_intent
    semantic_intent_raw = json.dumps(semantic_intent, ensure_ascii=False)
    if len(semantic_intent_raw) > 4000:
        semantic_intent_bounded = {
            "truncated": True,
            "preview": semantic_intent_raw[:4000],
        }
    else:
        semantic_intent_bounded = semantic_intent

    orientation_request = {
        "schema": "orientation_model_selection_request.v1",
        "goal": goal_bounded,
        "semantic_intent": semantic_intent_bounded,
        "candidates": prompt_candidates,
        "required_output": {
            "decision": "select",
            "selected_candidate_ids": ["candidate_id"],
            "rationale": "short rationale",
            "confidence": 0.0,
        },
        "constraints": [
            "Choose only candidate_id values present in candidates.",
            "Do not generate paths.",
            "Do not generate tools.",
            "Do not answer the repository task.",
        ],
    }

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
                "content": json.dumps(orientation_request, ensure_ascii=False, default=str),
            },
        ],
        "format": "json",
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0,
        },
        "keep_alive": keep_alive,
    }

    # POST
    try:
        response = post_json(planner_url, request_body, timeout_seconds)
    except Exception:
        result["rationale"] = "backend_exception"
        result["error_type"] = type(Exception).__name__
        result["error"] = ""
        result["planner_model"] = planner_model
        result["planner_url"] = planner_url
        result["timeout_seconds"] = timeout_seconds
        result["keep_alive"] = keep_alive
        return result

    if not isinstance(response, dict):
        result["rationale"] = "response_not_dict"
        result["planner_model"] = planner_model
        result["planner_url"] = planner_url
        result["timeout_seconds"] = timeout_seconds
        result["keep_alive"] = keep_alive
        return result

    # Estrai oggetto Ollama
    extracted, extraction_reason = _extract_orientation_response_object(response)

    if extracted is None:
        result["rationale"] = extraction_reason
        result["planner_model"] = planner_model
        result["planner_url"] = planner_url
        result["timeout_seconds"] = timeout_seconds
        result["keep_alive"] = keep_alive
        return result

    # Applica metadata autorevoli
    extracted["planner_model"] = planner_model
    extracted["planner_url"] = planner_url
    extracted["timeout_seconds"] = timeout_seconds
    extracted["keep_alive"] = keep_alive

    # Sanitize
    return sanitize_orientation_selection(
        extracted,
        valid_candidate_ids=valid_candidate_ids,
        max_selected=max_selected,
    )
