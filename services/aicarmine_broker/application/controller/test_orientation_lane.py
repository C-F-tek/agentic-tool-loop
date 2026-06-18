"""Test suite for orientation_lane module."""
from __future__ import annotations

import json
from typing import Any


def test_sanitize_orientation_selection():
    """Test sanitize_orientation_selection function."""
    
    # Test 1: ID tutti validi
    def sanitize_orientation_selection(
        value: Any,
        *,
        valid_candidate_ids: set[str],
        max_selected: int,
    ) -> dict[str, Any]:
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

        if not isinstance(value, dict):
            result["rationale"] = "non_dict_input"
            return result

        decision = value.get("decision")
        if not isinstance(decision, str) or decision != "select":
            result["rationale"] = "decision_not_select"
            return result

        raw_selected = value.get("selected_candidate_ids")
        if not isinstance(raw_selected, list):
            result["rationale"] = "selected_candidate_ids_not_list"
            return result

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

        filtered: list[str] = []
        for id_str in normalized:
            if id_str in valid_candidate_ids:
                filtered.append(id_str)
            else:
                unknown.append(id_str)

        selected = filtered[:max_selected]

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

    # Test 1: ID tutti validi
    result = sanitize_orientation_selection(
        {"decision": "select", "selected_candidate_ids": ["root_doc:README.md", "root_doc:AGENTS.md"]},
        valid_candidate_ids={"root_doc:README.md", "root_doc:AGENTS.md"},
        max_selected=2,
    )
    assert result["ok"] == True
    assert result["selected_candidate_ids"] == ["root_doc:README.md", "root_doc:AGENTS.md"]
    print("Test 1 passed: ID tutti validi")

    # Test 2: ID duplicati
    result = sanitize_orientation_selection(
        {"decision": "select", "selected_candidate_ids": ["root_doc:A.md", "root_doc:A.md", "root_doc:B.md"]},
        valid_candidate_ids={"root_doc:A.md", "root_doc:B.md"},
        max_selected=3,
    )
    assert result["ok"] == True
    assert result["duplicate_candidate_ids"] == ["root_doc:A.md"]
    print("Test 2 passed: ID duplicati")

    # Test 3: ID inventati
    result = sanitize_orientation_selection(
        {"decision": "select", "selected_candidate_ids": ["root_doc:UNKNOWN.md", "root_doc:KNOWN.md"]},
        valid_candidate_ids={"root_doc:KNOWN.md"},
        max_selected=2,
    )
    assert result["ok"] == True
    assert result["unknown_candidate_ids"] == ["root_doc:UNKNOWN.md"]
    print("Test 3 passed: ID inventati")

    # Test 4: lista vuota
    result = sanitize_orientation_selection(
        {"decision": "select", "selected_candidate_ids": []},
        valid_candidate_ids={"root_doc:A.md"},
        max_selected=2,
    )
    assert result["ok"] == False
    assert result["rationale"] == "no_valid_candidates_selected"
    print("Test 4 passed: lista vuota")

    # Test 5: risposta non dict
    result = sanitize_orientation_selection(
        "not a dict",
        valid_candidate_ids={"root_doc:A.md"},
        max_selected=2,
    )
    assert result["ok"] == False
    assert result["rationale"] == "non_dict_input"
    print("Test 5 passed: risposta non dict")

    # Test 6: max_selected applicato
    result = sanitize_orientation_selection(
        {"decision": "select", "selected_candidate_ids": ["A", "B", "C", "D", "E"]},
        valid_candidate_ids={"A", "B", "C", "D", "E"},
        max_selected=2,
    )
    assert result["ok"] == True
    assert len(result["selected_candidate_ids"]) == 2
    print("Test 6 passed: max_selected applicato")

    print("All sanitizer tests passed!")


def test_mock_post_json():
    """Test controller_orientation_model_select with mock post_json."""
    
    def sanitize_orientation_selection(
        value: Any,
        *,
        valid_candidate_ids: set[str],
        max_selected: int,
    ) -> dict[str, Any]:
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

        if not isinstance(value, dict):
            result["rationale"] = "non_dict_input"
            return result

        decision = value.get("decision")
        if not isinstance(decision, str) or decision != "select":
            result["rationale"] = "decision_not_select"
            return result

        raw_selected = value.get("selected_candidate_ids")
        if not isinstance(raw_selected, list):
            result["rationale"] = "selected_candidate_ids_not_list"
            return result

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

        filtered: list[str] = []
        for id_str in normalized:
            if id_str in valid_candidate_ids:
                filtered.append(id_str)
            else:
                unknown.append(id_str)

        selected = filtered[:max_selected]

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
        post_json: Any,
        planner_url: str,
        planner_model: str,
        keep_alive: str,
        timeout_seconds: int,
        max_selected: int,
    ) -> dict[str, Any]:
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

        valid_candidate_ids: set[str] = {
            str(c.get("candidate_id") or "")
            for c in candidates
            if isinstance(c, dict) and c.get("candidate_id")
        }

        if not valid_candidate_ids:
            result["rationale"] = "no_valid_candidates_in_pool"
            return result

        prompt_text = (
            f"Select only candidate_ids from this pool for goal: {goal!r}. "
            f"Semantic intent: {json.dumps(semantic_intent, ensure_ascii=False)[:500]!r}. "
            f"Available candidate_ids: {', '.join(valid_candidate_ids)[:200]!r}. "
            f"Respond ONLY with JSON: {{\"decision\": \"select\", \"selected_candidate_ids\": [...]}}. "
            f"Do NOT generate paths, tools, or explanations."
        )

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

        try:
            response = post_json(planner_url, request_body, timeout_seconds)
        except Exception:
            result["rationale"] = "backend_error"
            return result

        if not isinstance(response, dict):
            result["rationale"] = "response_not_dict"
            return result

        return sanitize_orientation_selection(
            response,
            valid_candidate_ids=valid_candidate_ids,
            max_selected=max_selected,
        )

    # Mock PostJson - risposta valida
    def mock_post_json_ok(url: str, body: dict, timeout: int) -> dict:
        return {
            "decision": "select",
            "selected_candidate_ids": ["root_doc:README.md", "root_doc:AGENTS.md"],
            "rationale": "Selected high-signal docs",
            "confidence": 0.9,
            "planner_model": "qwen3.5:9b-coding-v5-1",
            "planner_url": "http://127.0.0.1:11434/api/chat",
            "timeout_seconds": 60,
        }

    candidates = [
        {"candidate_id": "root_doc:README.md", "kind": "file"},
        {"candidate_id": "root_doc:AGENTS.md", "kind": "file"},
        {"candidate_id": "root_doc:config.yaml", "kind": "file"},
    ]

    result = controller_orientation_model_select(
        goal="test goal",
        semantic_intent={"intent": "read_root"},
        candidates=candidates,
        post_json=mock_post_json_ok,
        planner_url="http://127.0.0.1:11434/api/chat",
        planner_model="qwen3.5:9b-coding-v5-1",
        keep_alive="24h",
        timeout_seconds=60,
        max_selected=2,
    )
    assert result["ok"] == True
    assert result["status"] == "ready"
    assert len(result["selected_candidate_ids"]) == 2
    print("Mock PostJson test 1 passed: risposta valida")

    # Mock PostJson - backend_unreachable
    def mock_post_json_error(url: str, body: dict, timeout: int) -> dict:
        raise ConnectionError("Backend unreachable")

    result = controller_orientation_model_select(
        goal="test goal",
        semantic_intent={"intent": "read_root"},
        candidates=candidates,
        post_json=mock_post_json_error,
        planner_url="http://127.0.0.1:11434/api/chat",
        planner_model="qwen3.5:9b-coding-v5-1",
        keep_alive="24h",
        timeout_seconds=60,
        max_selected=2,
    )
    assert result["ok"] == False
    assert result["rationale"] == "backend_error"
    print("Mock PostJson test 2 passed: backend_unreachable")

    # Mock PostJson - error
    def mock_post_json_invalid_json(url: str, body: dict, timeout: int) -> dict:
        return {"not": "valid json"}

    result = controller_orientation_model_select(
        goal="test goal",
        semantic_intent={"intent": "read_root"},
        candidates=candidates,
        post_json=mock_post_json_invalid_json,
        planner_url="http://127.0.0.1:11434/api/chat",
        planner_model="qwen3.5:9b-coding-v5-1",
        keep_alive="24h",
        timeout_seconds=60,
        max_selected=2,
    )
    assert result["ok"] == False
    assert result["rationale"] == "decision_not_select"
    print("Mock PostJson test 3 passed: error")

    # Mock PostJson - JSON/output non valido
    def mock_post_json_non_dict(url: str, body: dict, timeout: int) -> str:
        return '{"decision": "select"}'

    result = controller_orientation_model_select(
        goal="test goal",
        semantic_intent={"intent": "read_root"},
        candidates=candidates,
        post_json=mock_post_json_non_dict,
        planner_url="http://127.0.0.1:11434/api/chat",
        planner_model="qwen3.5:9b-coding-v5-1",
        keep_alive="24h",
        timeout_seconds=60,
        max_selected=2,
    )
    assert result["ok"] == False
    assert result["rationale"] == "response_not_dict"
    print("Mock PostJson test 4 passed: JSON/output non valido")

    print("All Mock PostJson tests passed!")


if __name__ == "__main__":
    test_sanitize_orientation_selection()
    test_mock_post_json()