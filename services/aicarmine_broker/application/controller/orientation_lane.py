"""Orientation model selector isolatfrom services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

ed module.

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


def orientation_shadow_effective_mode(
    requested_mode: object,
) -> str:
    """Determin effective mode from requested_mode.
    
    Contract:
    - Se requested_mode non è str: restituisce "legacy";
    - normalizza: strip().lower();
    - Soltanto "shadow" restituisce "shadow";
    - Tutti gli altri valori restituiscono "legacy".
    
    Inclusi: legacy, active, stringa vuota, unknown, shadowing,
    active-shadow, None, bool, numeri, dict.
    
    Vincoli: nessun environment, logging, side effect, eccezione.
    Active è fail-closed a legacy.
    """
    if not isinstance(requested_mode, str):
        return "legacy"
    
    normalized = requested_mode.strip().lower()
    if normalized == "shadow":
        return "shadow"
    
    return "legacy"


def orientation_legacy_selected_candidate_ids(
    *,
    candidates: list[dict[str, Any]],
    doc_plan: dict[str, Any] | None,
    area_plans: list[dict[str, Any]],
) -> list[str]:
    """Traduce i path già selezionati dai plan legacy in candidate_id.
    
    Obiettivo: tradurre i path già selezionati dai plan legacy in
    candidate_id già presenti nel candidate pool. Non ricostruire o
    rieseguire la policy legacy.
    
    Candidate allowlist: costruire mapping deterministici esclusivamente
    da candidates. Accettare un candidato soltanto se:
    - candidate è dict;
    - candidate_id è str;
    - candidate_id.strip() non è vuoto;
    - len(candidate_id.strip()) <= 500;
    - path è str;
    - path.strip() non è vuoto;
    - candidate_class è root_doc o root_area.
    
    Usare come chiave: (candidate_class, path) e come valore: candidate_id.
    
    Regole: preservare il primo mapping valido; non sostituirlo con
    duplicati successivi; non generare candidate_id dal path; non usare
    filesystem; non normalizzare semanticamente i path; applicare
    soltanto strip; candidate pool malformato ignorato, non sollevare.
    
    Document plan: valida se doc_plan è dict, doc_plan["arguments"] è dict,
    arguments["paths"] è list. Per ogni elemento di paths: accettare
    soltanto str non vuote dopo strip; cercare ("root_doc", path) nel
    mapping autorizzato; se trovato aggiungere il candidate_id; se
    sconosciuto ignorarlo. Non sorting, nuovi budget, repo existence check,
    file classification. Il budget è già stato applicato dal legacy plan.
    
    Area plans: valida se area_plans è list. Per ciascun elemento: deve
    essere dict, element["arguments"] deve essere dict, arguments["path"]
    deve essere str non vuota; cercare ("root_area", path) nel mapping
    autorizzato; se trovato aggiungere il candidate_id; se sconosciuto
    ignorarlo. Se area_plans non è list: ignorare soltanto la sezione aree,
    non eliminare documenti validi già selezionati.
    
    Output: ordine obbligatorio: 1) documenti nell'ordine di
    doc_plan["arguments"]["paths"]; 2) aree nell'ordine di area_plans.
    Deduplicare candidate_id preservando la prima occorrenza globale.
    
    Non includere: area read plan, path, candidate non presenti nel pool,
    ID inventati. Non modificare: candidates, doc_plan, area_plans.
    Non sollevare per shape malformate.
    """
    # Costruisci mapping deterministico da candidates
    candidate_items = candidates if isinstance(candidates, list) else []
    mapping: dict[tuple[str, str], str] = {}
    for candidate in candidate_items:
        if not isinstance(candidate, dict):
            continue
        candidate_id = candidate.get("candidate_id", "")
        path = candidate.get("path", "")
        candidate_class = candidate.get("candidate_class", "")
        
        if not isinstance(candidate_id, str):
            continue
        candidate_id_stripped = candidate_id.strip()
        if not candidate_id_stripped or len(candidate_id_stripped) > 500:
            continue
        
        if not isinstance(path, str):
            continue
        path_stripped = path.strip()
        if not path_stripped:
            continue
        
        if candidate_class not in {"root_doc", "root_area"}:
            continue
        
        key = (candidate_class, path_stripped)
        if key not in mapping:
            mapping[key] = candidate_id_stripped
    
    # Process document plan
    doc_paths: list[str] = []
    if doc_plan is not None and isinstance(doc_plan, dict):
        arguments = doc_plan.get("arguments")
        if isinstance(arguments, dict):
            paths = arguments.get("paths")
            if isinstance(paths, list):
                for item in paths:
                    if isinstance(item, str):
                        item_stripped = item.strip()
                        if item_stripped:
                            doc_paths.append(item_stripped)
    
    # Process area plans
    area_paths: list[str] = []
    if isinstance(area_plans, list):
        for element in area_plans:
            if not isinstance(element, dict):
                continue
            arguments = element.get("arguments")
            if not isinstance(arguments, dict):
                continue
            path = arguments.get("path")
            if isinstance(path, str):
                path_stripped = path.strip()
                if path_stripped:
                    area_paths.append(path_stripped)
    
    # Build result with deduplication using two separate loops
    # Ciclo documenti: usa root_doc come chiave
    seen: set[str] = set()
    result: list[str] = []
    
    for path in doc_paths:
        candidate_id = mapping.get(("root_doc", path))
        if candidate_id and candidate_id not in seen:
            seen.add(candidate_id)
            result.append(candidate_id)
    
    # Ciclo aree: usa root_area come chiave
    for path in area_paths:
        candidate_id = mapping.get(("root_area", path))
        if candidate_id and candidate_id not in seen:
            seen.add(candidate_id)
            result.append(candidate_id)
    
    return result


def orientation_shadow_selection_metrics(
    *,
    legacy_selected_candidate_ids: list[str],
    model_selected_candidate_ids: list[str],
) -> dict[str, Any]:
    """Calcola metriche di selezione shadow.

    Sanitizzazione indipendente dei due lati:
    - se input non è list: trattare come lista vuota;
    - accettare soltanto elementi str;
    - applicare strip;
    - ignorare stringhe vuote;
    - ignorare ID con len > 500;
    - deduplicare preservando la prima occorrenza;
    - fermarsi dopo 13 ID validi distinti.

    Non convertire valori non-stringa tramite str(). Non modificare gli input.

    Metriche:
    - legacy_count: len(legacy_bounded)
    - model_count: len(model_bounded)
    - selection_overlap: ID presenti in entrambi i lati, nell'ordine di legacy_bounded
    - selection_overlap_count: len(selection_overlap)
    - top1_match: true solo se entrambe le liste sono non vuote e legacy_bounded[0] == model_bounded[0]
    - exact_match: legacy_bounded == model_bounded
    - would_change_selection: not exact_match

    Output esatto minimo:
    {
        "legacy_count": int,
        "model_count": int,
        "selection_overlap": list[str],
        "selection_overlap_count": int,
        "top1_match": bool,
        "exact_match": bool,
        "would_change_selection": bool,
    }

    Non aggiungere: model call, rationale, provider metadata, state, artifact, evento, path.
    L'output deve essere deterministico.
    """

    def sanitize(ids: list[str]) -> list[str]:
        """Sanitize a bounded list of IDs."""
        if not isinstance(ids, list):
            ids = []
        
        bounded: list[str] = []
        seen: set[str] = set()
        
        for id_ in ids:
            if not isinstance(id_, str):
                continue
            
            id_stripped = id_.strip()
            if not id_stripped:
                continue
            
            if len(id_stripped) > 500:
                continue
            
            if id_stripped not in seen:
                seen.add(id_stripped)
                bounded.append(id_stripped)
            
            if len(bounded) >= 13:
                break
        
        return bounded
    
    legacy_bounded = sanitize(legacy_selected_candidate_ids)
    model_bounded = sanitize(model_selected_candidate_ids)
    
    legacy_count = len(legacy_bounded)
    model_count = len(model_bounded)
    
    overlap = [id_ for id_ in legacy_bounded if id_ in model_bounded]
    overlap_count = len(overlap)
    
    top1_match = (
        len(legacy_bounded) > 0 
        and len(model_bounded) > 0 
        and legacy_bounded[0] == model_bounded[0]
    )
    
    exact_match = legacy_bounded == model_bounded
    would_change_selection = not exact_match
    
    return {
        "legacy_count": legacy_count,
        "model_count": model_count,
        "selection_overlap": overlap,
        "selection_overlap_count": overlap_count,
        "top1_match": top1_match,
        "exact_match": exact_match,
        "would_change_selection": would_change_selection,
    }


def _apply_runtime_metadata(
    result: dict[str, Any],
    *,
    planner_model: str,
    planner_url: str,
    timeout_seconds: int,
    keep_alive: str,
) -> dict[str, Any]:
    """Applica metadata runtime autorevoli al risultato.

    Crea una copia del risultato e imposta i metadata autorevoli.
    Non modifica il dizionario ricevuto.
    """
    import copy
    copied = copy.deepcopy(result)
    copied["planner_model"] = planner_model
    copied["planner_url"] = planner_url
    copied["timeout_seconds"] = timeout_seconds
    copied["keep_alive"] = keep_alive
    return copied


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
    - message non-dict: usa message.content solo se message è dict e content è stringa;
    - ignora valori non-stringa.
    """
    if not isinstance(response, dict):
        return None, "response_not_dict"

    # Direct dict compatibility: restituisci una copia
    if response.get("decision") == "select":
        return dict(response), "direct_decision"

    # Estrai testo in ordine, solo stringhe
    # Precedenza: response["response"] > response["message"]["content"] > response["partial_content"]
    # Costruisci lista di candidati in ordine
    text_candidates: list[str | None] = []

    # 1. response["response"]
    response_field = response.get("response")
    if isinstance(response_field, str):
        text_candidates.append(response_field)

    # 2. response["message"]["content"]
    message = response.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            text_candidates.append(content)

    # 3. response["partial_content"]
    partial = response.get("partial_content")
    if isinstance(partial, str):
        text_candidates.append(partial)

    # Seleziona primo valore non vuoto
    text = next((t for t in text_candidates if isinstance(t, str) and t.strip()), None)

    if not isinstance(text, str):
        text = ""

    if not text:
        return None, "empty_model_content"

    try:
        decoded = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
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
    # I duplicati qui sono quelli emessi dal modello (dal payload)
    seen: set[str] = set()
    normalized: list[str] = []
    duplicates_from_model: list[str] = []
    unknown: list[str] = []

    for item in raw_selected:
        if item is None:
            continue
        item_str = str(item).strip()
        if not item_str:
            continue
        if item_str in seen:
            duplicates_from_model.append(item_str)
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
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or confidence < 0
        or confidence > 1
    ):
        confidence = None

    # Assegna diagnostica PRIMA del ramo no_valid_selection
    result["unknown_candidate_ids"] = unknown
    result["duplicate_candidate_ids"] = duplicates_from_model

    # Ok solo se abbiamo almeno un ID valido selezionato
    if not selected:
        result["ok"] = False
        result["rationale"] = "no_valid_candidates_selected"
        return result

    result["ok"] = True
    result["status"] = "ready"
    result["selected_candidate_ids"] = selected
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

    # Costruisci un solo candidate pool autorizzato
    prompt_candidates: list[dict[str, Any]] = []
    seen_candidate_ids: set[str] = set()
    duplicate_input_candidate_ids: list[str] = []
    seen_duplicate_ids: set[str] = set()  # Evita duplicati nella diagnostica

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        cid_raw = candidate.get("candidate_id")
        if cid_raw is None:
            continue
        cid = str(cid_raw).strip()
        if not cid:
            continue
        # Limite 500 caratteri
        if len(cid) > 500:
            continue
        if cid in seen_candidate_ids:
            # Registra duplicato SOLO se non già registrato
            if cid not in seen_duplicate_ids:
                duplicate_input_candidate_ids.append(cid)
                seen_duplicate_ids.add(cid)
            continue
        seen_candidate_ids.add(cid)
        # Normalizza kind e candidate_class
        kind_raw = candidate.get("kind")
        if isinstance(kind_raw, str):
            kind = kind_raw.strip()
        else:
            kind = "file"
        if not kind:
            kind = "file"
        kind = kind[:80]
        candidate_class_raw = candidate.get("candidate_class")
        if isinstance(candidate_class_raw, str):
            candidate_class = candidate_class_raw.strip()
        else:
            candidate_class = "root_doc"
        if not candidate_class:
            candidate_class = "root_doc"
        candidate_class = candidate_class[:80]
        # Normalizza static_rank: accetta solo int, non bool
        static_rank = candidate.get("static_rank")
        if isinstance(static_rank, bool):
            static_rank = 0
        elif not isinstance(static_rank, int):
            static_rank = 0
        # Normalizza signals: esplicito e deterministico
        # Caratteri qualsiasi, max 80, max 8 segnali
        raw_signals = candidate.get("signals") or []
        signals: list[str] = []
        for s in raw_signals:
            if not isinstance(s, str):
                continue
            s_stripped = s.strip()
            if not s_stripped:
                continue
            # Tronca a 80 caratteri
            if len(s_stripped) > 80:
                s_stripped = s_stripped[:80]
            signals.append(s_stripped)
        signals = signals[:8]
        prompt_candidates.append({
            "candidate_id": cid,
            "kind": kind,
            "candidate_class": candidate_class,
            "static_rank": static_rank,
            "signals": signals,
        })

    # Costruisci valid_candidate_ids solo dai prompt_candidates
    valid_candidate_ids: set[str] = {c["candidate_id"] for c in prompt_candidates}

    # Terminare prima della chiamata AI quando il pool è vuoto
    if not valid_candidate_ids:
        result["status"] = "unavailable"
        result["rationale"] = "no_valid_candidates_in_pool"
        result["duplicate_input_candidate_ids"] = duplicate_input_candidate_ids
        return _apply_runtime_metadata(result, planner_model=planner_model, planner_url=planner_url, timeout_seconds=timeout_seconds, keep_alive=keep_alive)

    # Bound goal
    goal_bounded = str(goal)[:4000]

    # Rendi semantic_intent JSON-safe
    semantic_intent_raw = json.dumps(semantic_intent, ensure_ascii=False, default=str)
    if len(semantic_intent_raw) > 4000:
        semantic_intent_bounded = {
            "truncated": True,
            "preview": semantic_intent_raw[:4000],
        }
    else:
        semantic_intent_bounded = json.loads(semantic_intent_raw)

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
    except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}:
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )
        result["rationale"] = "backend_exception"
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)[:500]
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

    # Riconosci backend error prima del parsing
    backend_timeout = response.get("backend_timeout")
    backend_unreachable = response.get("backend_unreachable")
    error = response.get("error")
    ok_flag = response.get("ok")

    if backend_timeout or backend_unreachable or error or (ok_flag is False and (error or response.get("error_type"))):
        result["rationale"] = "backend_request_failed"
        result["status"] = "unavailable"
        result["backend_timeout"] = bool(backend_timeout)
        result["backend_unreachable"] = bool(backend_unreachable)
        result["error_type"] = str(response.get("error_type") or "")[:120]
        result["error"] = str(error or "")[:500]
        result["planner_model"] = planner_model
        result["planner_url"] = planner_url
        result["timeout_seconds"] = timeout_seconds
        result["keep_alive"] = keep_alive
        return result

    # Estrai oggetto Ollama
    extracted, extraction_reason = _extract_orientation_response_object(response)

    if extracted is None:
        result["rationale"] = extraction_reason
        result["status"] = "invalid"
        result["planner_model"] = planner_model
        result["planner_url"] = planner_url
        result["timeout_seconds"] = timeout_seconds
        result["keep_alive"] = keep_alive
        return _apply_runtime_metadata(result, planner_model=planner_model, planner_url=planner_url, timeout_seconds=timeout_seconds, keep_alive=keep_alive)

    # Sanitize
    sanitized = sanitize_orientation_selection(
        extracted,
        valid_candidate_ids=valid_candidate_ids,
        max_selected=max_selected,
    )

    # Aggiorna duplicate_input_candidate_ids separatamente da duplicate_candidate_ids
    # duplicate_candidate_ids viene già impostato da sanitize_orientation_selection() con i duplicati dal modello
    # duplicate_input_candidate_ids contiene i duplicati del pool di input
    if duplicate_input_candidate_ids:
        sanitized["duplicate_input_candidate_ids"] = duplicate_input_candidate_ids

    # Applica metadata autorevoli DOPO il sanitizer
    return _apply_runtime_metadata(sanitized, planner_model=planner_model, planner_url=planner_url, timeout_seconds=timeout_seconds, keep_alive=keep_alive)
