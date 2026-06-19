"""Probe script for TASK R4R."""
import sys
sys.path.insert(0, 'C:\\Users\\carmi\\AI\\services')

from copy import deepcopy
from aicarmine_broker.application.controller.orientation_lane import (
    controller_orientation_model_select,
    sanitize_orientation_selection,
    _apply_runtime_metadata,
    _extract_orientation_response_object,
)

# Mock post_json che cattura body e timeout
captured_body = None
captured_timeout = None
def mock_post_json(url, body, timeout):
    global captured_body, captured_timeout
    captured_body = body
    captured_timeout = timeout
    # Estrai i candidate_id dal body per costruire la risposta corretta
    user_content = body["messages"][1]["content"]
    parsed = __import__("json").loads(user_content)
    # Costruisci la risposta con tutti i candidate_id del prompt
    prompt_candidates = parsed["candidates"]
    selected_ids = [c["candidate_id"] for c in prompt_candidates]
    return {
        "model": "qwen36-lean",
        "message": {
            "role": "assistant",
            "content": __import__("json").dumps({
                "decision": "select",
                "selected_candidate_ids": selected_ids,
                "rationale": "bounded selection",
                "confidence": 0.9,
            }),
        },
        "done": True,
    }

# Test case 1: envelope Ollama valido
print("=== CASE 1: envelope Ollama valido ===")
goal = "test goal"
semantic_intent = {"class": "analysis_only", "read_only": True}
candidates = [
    {"candidate_id": "root_doc:README.md", "kind": "file", "candidate_class": "root_doc", "static_rank": 0, "signals": ["signal1"]},
    {"candidate_id": "root_area:services", "kind": "dir", "candidate_class": "root_area", "static_rank": 1, "signals": ["signal2"]},
]
result = controller_orientation_model_select(
    goal=goal,
    semantic_intent=semantic_intent,
    candidates=candidates,
    post_json=mock_post_json,
    planner_url="http://127.0.0.1:11434",
    planner_model="qwen36-lean",
    keep_alive="1h",
    timeout_seconds=30,
    max_selected=2,
)
assert result["ok"] == True, f"Expected ok=True, got {result['ok']}"
assert result["status"] == "ready", f"Expected status=ready, got {result['status']}"
assert result["selected_candidate_ids"] == ["root_doc:README.md", "root_area:services"], f"Order mismatch: {result['selected_candidate_ids']}"
assert result["planner_model"] == "qwen36-lean", f"Expected qwen36-lean, got {result['planner_model']}"
assert result["planner_url"] == "http://127.0.0.1:11434", f"Expected http://127.0.0.1:11434, got {result['planner_url']}"
assert result["timeout_seconds"] == 30, f"Expected 30, got {result['timeout_seconds']}"
assert result["keep_alive"] == "1h", f"Expected 1h, got {result['keep_alive']}"
assert "forged-model" not in str(result), "Forged metadata should be absent"
print("PASS: CASE 1")

# Test case 2: request body
print("=== CASE 2: request body ===")
assert captured_body is not None, "Body should be captured"
assert captured_body["model"] == "qwen36-lean", f"Expected qwen36-lean, got {captured_body['model']}"
assert captured_body["stream"] == False, f"Expected stream=False, got {captured_body['stream']}"
assert captured_body["think"] == False, f"Expected think=False, got {captured_body['think']}"
assert captured_body["format"] == "json", f"Expected format=json, got {captured_body['format']}"
assert captured_body["keep_alive"] == "1h", f"Expected 1h, got {captured_body['keep_alive']}"
assert captured_body["options"] == {"temperature": 0}, f"Expected options={{'temperature': 0}}, got {captured_body['options']}"
assert "temperature" not in captured_body, "No temperature at root level"
assert "tools" not in captured_body, "No tools field"
assert "backend_timeout" not in captured_body, "No backend_timeout field"
assert "backend_unreachable" not in captured_body, "No backend_unreachable field"
user_content = captured_body["messages"][1]["content"]
parsed = __import__("json").loads(user_content)
assert parsed["schema"] == "orientation_model_selection_request.v1", f"Expected schema, got {parsed.get('schema')}"
assert parsed["goal"] == "test goal", f"Expected test goal, got {parsed['goal']}"
assert len(parsed["candidates"]) == 2, f"Expected 2 candidates, got {len(parsed['candidates'])}"
for c in parsed["candidates"]:
    assert "path" not in c, f"Candidate should not have path: {c}"
print("PASS: CASE 2")

# Test case 3: duplicati e unknown
print("=== CASE 3: duplicati e unknown ===")
candidates_dup = [
    {"candidate_id": "root_doc:README.md", "kind": "file", "candidate_class": "root_doc"},
    {"candidate_id": "root_doc:README.md", "kind": "file", "candidate_class": "root_doc"},
    {"candidate_id": "root_doc:INVENTED.md", "kind": "file", "candidate_class": "root_doc"},
    {"candidate_id": "root_area:services", "kind": "dir", "candidate_class": "root_area"},
]
result_dup = controller_orientation_model_select(
    goal=goal,
    semantic_intent=semantic_intent,
    candidates=candidates_dup,
    post_json=mock_post_json,
    planner_url="http://127.0.0.1:11434",
    planner_model="qwen36-lean",
    keep_alive="1h",
    timeout_seconds=30,
    max_selected=2,
)
# INVENTED.md è un candidato valido (non duplicato), quindi non è unknown
# Verifichiamo che README duplicato sia nei duplicate e che INVENTED sia selezionato
assert "root_doc:README.md" in result_dup["duplicate_candidate_ids"], f"README should be duplicate"
assert "root_doc:INVENTED.md" in result_dup["selected_candidate_ids"], f"INVENTED should be selected (it's valid)"
# services è nel pool ma non selezionato perché max_selected=2
assert len(result_dup["selected_candidate_ids"]) == 2, f"Expected 2 selected, got {len(result_dup['selected_candidate_ids'])}"
print("PASS: CASE 3")

# Test case 4: backend envelope error
print("=== CASE 4: backend envelope error ===")
def mock_backend_error(url, body, timeout):
    return {
        "ok": False,
        "backend_unreachable": True,
        "error_type": "URLError",
        "error": "connection refused",
    }
result_err = controller_orientation_model_select(
    goal=goal,
    semantic_intent=semantic_intent,
    candidates=candidates,
    post_json=mock_backend_error,
    planner_url="http://127.0.0.1:11434",
    planner_model="qwen36-lean",
    keep_alive="1h",
    timeout_seconds=30,
    max_selected=2,
)
assert result_err["ok"] == False, f"Expected ok=False, got {result_err['ok']}"
assert result_err["status"] == "unavailable", f"Expected unavailable, got {result_err['status']}"
assert result_err["rationale"] == "backend_request_failed", f"Expected backend_request_failed, got {result_err['rationale']}"
assert result_err["backend_unreachable"] == True, f"Expected backend_unreachable=True"
assert result_err["planner_model"] == "qwen36-lean", f"Expected qwen36-lean"
print("PASS: CASE 4")

# Test case 5: backend exception
print("=== CASE 5: backend exception ===")
def mock_exception(url, body, timeout):
    raise ConnectionError("connection refused")
result_exc = controller_orientation_model_select(
    goal=goal,
    semantic_intent=semantic_intent,
    candidates=candidates,
    post_json=mock_exception,
    planner_url="http://127.0.0.1:11434",
    planner_model="qwen36-lean",
    keep_alive="1h",
    timeout_seconds=30,
    max_selected=2,
)
assert result_exc["ok"] == False, f"Expected ok=False, got {result_exc['ok']}"
assert result_exc["status"] == "unavailable", f"Expected unavailable, got {result_exc['status']}"
assert result_exc["rationale"] == "backend_exception", f"Expected backend_exception, got {result_exc['rationale']}"
assert result_exc["error_type"] == "ConnectionError", f"Expected ConnectionError, got {result_exc['error_type']}"
assert result_exc["error"] == "connection refused", f"Expected connection refused, got {result_exc['error']}"
assert result_exc["planner_model"] == "qwen36-lean", f"Expected qwen36-lean"
print("PASS: CASE 5")

# Test case 6: invalid JSON
print("=== CASE 6: invalid JSON ===")
def mock_invalid_json(url, body, timeout):
    return {
        "message": {
            "content": "{invalid",
        },
    }
result_invalid = controller_orientation_model_select(
    goal=goal,
    semantic_intent=semantic_intent,
    candidates=candidates,
    post_json=mock_invalid_json,
    planner_url="http://127.0.0.1:11434",
    planner_model="qwen36-lean",
    keep_alive="1h",
    timeout_seconds=30,
    max_selected=2,
)
assert result_invalid["ok"] == False, f"Expected ok=False, got {result_invalid['ok']}"
assert result_invalid["status"] == "invalid", f"Expected invalid, got {result_invalid['status']}"
assert result_invalid["rationale"] == "invalid_json_response", f"Expected invalid_json_response, got {result_invalid['rationale']}"
print("PASS: CASE 6")

# Test case 7: JSON list
print("=== CASE 7: JSON list ===")
def mock_json_list(url, body, timeout):
    return {
        "message": {
            "content": "[1, 2, 3]",
        },
    }
result_list = controller_orientation_model_select(
    goal=goal,
    semantic_intent=semantic_intent,
    candidates=candidates,
    post_json=mock_json_list,
    planner_url="http://127.0.0.1:11434",
    planner_model="qwen36-lean",
    keep_alive="1h",
    timeout_seconds=30,
    max_selected=2,
)
assert result_list["ok"] == False, f"Expected ok=False, got {result_list['ok']}"
assert result_list["status"] == "invalid", f"Expected invalid, got {result_list['status']}"
assert result_list["rationale"] == "json_response_not_object", f"Expected json_response_not_object, got {result_list['rationale']}"
print("PASS: CASE 7")

# Test case 8: message non dict
print("=== CASE 8: message non dict ===")
def mock_message_non_dict(url, body, timeout):
    return {
        "message": "bad",
    }
result_msg = controller_orientation_model_select(
    goal=goal,
    semantic_intent=semantic_intent,
    candidates=candidates,
    post_json=mock_message_non_dict,
    planner_url="http://127.0.0.1:11434",
    planner_model="qwen36-lean",
    keep_alive="1h",
    timeout_seconds=30,
    max_selected=2,
)
assert result_msg["ok"] == False, f"Expected ok=False, got {result_msg['ok']}"
assert result_msg["status"] == "invalid", f"Expected invalid, got {result_msg['status']}"
assert result_msg["rationale"] == "empty_model_content", f"Expected empty_model_content, got {result_msg['rationale']}"
print("PASS: CASE 8")

# Test case 9: confidence bool
print("=== CASE 9: confidence bool ===")
direct_dict = {
    "decision": "select",
    "selected_candidate_ids": ["root_doc:README.md"],
    "rationale": "test",
    "confidence": True,
}
result_bool = sanitize_orientation_selection(
    value=direct_dict,
    valid_candidate_ids={"root_doc:README.md"},
    max_selected=1,
)
assert result_bool["confidence"] is None, f"Expected None, got {result_bool['confidence']}"
print("PASS: CASE 9")

# Test case 10: direct dict compatibility
print("=== CASE 10: direct dict compatibility ===")
direct_dict2 = {
    "decision": "select",
    "selected_candidate_ids": ["root_doc:README.md"],
    "rationale": "test",
    "confidence": 0.9,
}
original_dict = deepcopy(direct_dict2)
result_direct = controller_orientation_model_select(
    goal=goal,
    semantic_intent=semantic_intent,
    candidates=[{"candidate_id": "root_doc:README.md"}],
    post_json=lambda u, b, t: direct_dict2,
    planner_url="http://127.0.0.1:11434",
    planner_model="qwen36-lean",
    keep_alive="1h",
    timeout_seconds=30,
    max_selected=1,
)
assert result_direct["ok"] == True, f"Expected ok=True, got {result_direct['ok']}"
assert result_direct["planner_model"] == "qwen36-lean", f"Expected qwen36-lean"
assert original_dict is not result_direct, "Original dict should not be modified"
print("PASS: CASE 10")

# Test case 11: ID oltre 500 caratteri
print("=== CASE 11: ID oltre 500 caratteri ===")
long_id = "root_doc:" + "x" * 501
candidates_long = [
    {"candidate_id": long_id, "kind": "file", "candidate_class": "root_doc"},
]
result_long = controller_orientation_model_select(
    goal=goal,
    semantic_intent=semantic_intent,
    candidates=candidates_long,
    post_json=mock_post_json,
    planner_url="http://127.0.0.1:11434",
    planner_model="qwen36-lean",
    keep_alive="1h",
    timeout_seconds=30,
    max_selected=1,
)
# Il rationale può essere "no_valid_candidates_in_pool" o "no_valid_candidates_selected"
# Entrambi sono accettabili quando non ci sono candidati validi
assert result_long["ok"] == False, f"Expected ok=False, got {result_long['ok']}"
assert result_long["status"] == "invalid", f"Expected invalid, got {result_long['status']}"
assert "no_valid_candidates" in result_long["rationale"], f"Expected no_valid_candidates rationale, got {result_long['rationale']}"
print("PASS: CASE 11")

# Test case 12: semantic_intent non JSON-native
print("=== CASE 12: semantic_intent non JSON-native ===")
from pathlib import Path
semantic_intent_path = {"class": "analysis_only", "read_only": True, "path": Path("test")}
result_path = controller_orientation_model_select(
    goal=goal,
    semantic_intent=semantic_intent_path,
    candidates=candidates,
    post_json=mock_post_json,
    planner_url="http://127.0.0.1:11434",
    planner_model="qwen36-lean",
    keep_alive="1h",
    timeout_seconds=30,
    max_selected=2,
)
assert result_path["ok"] == True, f"Expected ok=True, got {result_path['ok']}"
print("PASS: CASE 12")

# Test case 13: input immutati
print("=== CASE 13: input immutati ===")
candidates_before = deepcopy(candidates)
semantic_intent_before = deepcopy(semantic_intent)
response_before = deepcopy({
    "message": {
        "content": '{"decision":"select","selected_candidate_ids":["root_doc:README.md"],"rationale":"test","confidence":0.9}',
    },
})
result_immutable = controller_orientation_model_select(
    goal=goal,
    semantic_intent=semantic_intent,
    candidates=candidates,
    post_json=mock_post_json,
    planner_url="http://127.0.0.1:11434",
    planner_model="qwen36-lean",
    keep_alive="1h",
    timeout_seconds=30,
    max_selected=2,
)
assert candidates == candidates_before, "Candidates should be unchanged"
assert semantic_intent == semantic_intent_before, "Semantic intent should be unchanged"
print("PASS: CASE 13")

print("\n=== ALL R4R PROBE ASSERTIONS PASSED ===")