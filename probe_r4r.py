"""Probe script for TASK R4S — casi mirati sul codice di produzione."""

from __future__ import annotations

import json
import sys
from copy import deepcopy

sys.path.insert(0, r"C:\Users\carmi\AI\services")

from aicarmine_broker.application.controller.orientation_lane import (
    controller_orientation_model_select,
)

PLANNER_URL = "http://127.0.0.1:11434"
PLANNER_MODEL = "mio-qwen-code-6:latest"
KEEP_ALIVE = "1h"
TIMEOUT_SECONDS = 30
GOAL = "test goal"
SEMANTIC_INTENT = {"class": "analysis_only", "read_only": True}

captured_body: dict | None = None
captured_timeout: int | None = None


def reset_capture() -> None:
    global captured_body, captured_timeout
    captured_body = None
    captured_timeout = None


def call_selector(*, candidates, post_json, max_selected=2):
    return controller_orientation_model_select(
        goal=GOAL,
        semantic_intent=SEMANTIC_INTENT,
        candidates=candidates,
        post_json=post_json,
        planner_url=PLANNER_URL,
        planner_model=PLANNER_MODEL,
        keep_alive=KEEP_ALIVE,
        timeout_seconds=TIMEOUT_SECONDS,
        max_selected=max_selected,
    )


# CASE A — pool completamente invalido
print("=== CASE A: pool completamente invalido ===")
reset_capture()


def mock_post_json_no_call(url, body, timeout):
    raise AssertionError("post_json should NOT be called when pool is empty")


candidates_invalid = [
    {"candidate_id": "", "kind": "file", "candidate_class": "root_doc"},
    {
        "candidate_id": "root_doc:" + "x" * 501,
        "kind": "file",
        "candidate_class": "root_doc",
    },
    {"candidate_id": None, "kind": "file", "candidate_class": "root_doc"},
]
candidates_invalid_before = deepcopy(candidates_invalid)

result_a = call_selector(
    candidates=candidates_invalid,
    post_json=mock_post_json_no_call,
)

assert captured_body is None, f"captured_body should be None, got {captured_body!r}"
assert result_a["ok"] is False, result_a
assert result_a["status"] == "unavailable", result_a
assert result_a["rationale"] == "no_valid_candidates_in_pool", result_a
assert result_a["planner_model"] == PLANNER_MODEL, result_a
assert result_a["planner_url"] == PLANNER_URL, result_a
assert result_a["timeout_seconds"] == TIMEOUT_SECONDS, result_a
assert result_a["keep_alive"] == KEEP_ALIVE, result_a
assert candidates_invalid == candidates_invalid_before
print("PASS: CASE A")


# CASE B — duplicati input distinti dai duplicati emessi dal modello
print("=== CASE B: duplicati input distinti dai duplicati modello ===")
reset_capture()


def mock_model_emits_dups(url, body, timeout):
    global captured_body, captured_timeout
    captured_body = deepcopy(body)
    captured_timeout = timeout

    parsed = json.loads(body["messages"][1]["content"])
    prompt_ids = [
        candidate["candidate_id"]
        for candidate in parsed["candidates"]
    ]

    # Il candidate pool inviato al modello deve essere già deduplicato.
    assert prompt_ids == [
        "root_doc:README.md",
        "root_area:services",
    ], prompt_ids

    # Il modello, indipendentemente dal prompt deduplicato, emette:
    # - README due volte: duplicato di output del modello;
    # - INVENTED: ID sconosciuto;
    # - services: secondo ID valido.
    model_selected_ids = [
        "root_doc:README.md",
        "root_doc:README.md",
        "root_doc:INVENTED.md",
        "root_area:services",
    ]

    return {
        "model": "ignored-envelope-model",
        "message": {
            "role": "assistant",
            "content": json.dumps(
                {
                    "decision": "select",
                    "selected_candidate_ids": model_selected_ids,
                    "rationale": "bounded selection",
                    "confidence": 0.9,
                }
            ),
        },
        "done": True,
    }


candidates_dup = [
    {
        "candidate_id": "root_doc:README.md",
        "kind": "file",
        "candidate_class": "root_doc",
    },
    {
        "candidate_id": "root_doc:README.md",
        "kind": "file",
        "candidate_class": "root_doc",
    },
    {
        "candidate_id": "root_area:services",
        "kind": "dir",
        "candidate_class": "root_area",
    },
]
candidates_dup_before = deepcopy(candidates_dup)

result_b = call_selector(
    candidates=candidates_dup,
    post_json=mock_model_emits_dups,
)

assert captured_body is not None
assert captured_timeout == TIMEOUT_SECONDS
assert result_b["ok"] is True, result_b
assert result_b["status"] == "ready", result_b
assert result_b["duplicate_input_candidate_ids"] == [
    "root_doc:README.md"
], result_b
assert result_b["duplicate_candidate_ids"] == [
    "root_doc:README.md"
], result_b
assert result_b["unknown_candidate_ids"] == [
    "root_doc:INVENTED.md"
], result_b
assert result_b["selected_candidate_ids"] == [
    "root_doc:README.md",
    "root_area:services",
], result_b
assert candidates_dup == candidates_dup_before
print("PASS: CASE B")


# CASE C — partial_content fallback quando message.content è vuoto
print("=== CASE C: partial_content fallback ===")
reset_capture()


def mock_partial_content(url, body, timeout):
    global captured_body, captured_timeout
    captured_body = deepcopy(body)
    captured_timeout = timeout
    return {
        "message": {"content": ""},
        "partial_content": json.dumps(
            {
                "decision": "select",
                "selected_candidate_ids": ["root_doc:README.md"],
                "rationale": "fallback to partial_content",
                "confidence": 0.9,
            }
        ),
    }


result_c = call_selector(
    candidates=[{"candidate_id": "root_doc:README.md"}],
    post_json=mock_partial_content,
)

assert captured_body is not None
assert captured_timeout == TIMEOUT_SECONDS
assert result_c["ok"] is True, result_c
assert result_c["status"] == "ready", result_c
assert result_c["selected_candidate_ids"] == [
    "root_doc:README.md"
], result_c
print("PASS: CASE C")


# CASE D — normalizzazione dei candidate inviati nel prompt
print("=== CASE D: normalizzazione prompt candidate ===")
reset_capture()


def mock_capture_body(url, body, timeout):
    global captured_body, captured_timeout
    captured_body = deepcopy(body)
    captured_timeout = timeout
    return {
        "model": "ignored-envelope-model",
        "message": {
            "role": "assistant",
            "content": json.dumps(
                {
                    "decision": "select",
                    "selected_candidate_ids": ["root_doc:README.md"],
                    "rationale": "bounded selection",
                    "confidence": 0.9,
                }
            ),
        },
        "done": True,
    }


candidates_norm = [
    {
        "candidate_id": "root_doc:README.md",
        "kind": "  file  ",
        "candidate_class": "  root_doc  ",
        "static_rank": True,
        "signals": ["  one  ", "", "x" * 100, " two "],
    },
]
candidates_norm_before = deepcopy(candidates_norm)

result_d = call_selector(
    candidates=candidates_norm,
    post_json=mock_capture_body,
)

assert captured_body is not None
assert captured_timeout == TIMEOUT_SECONDS
assert result_d["ok"] is True, result_d
assert result_d["selected_candidate_ids"] == [
    "root_doc:README.md"
], result_d

user_content = captured_body["messages"][1]["content"]
parsed = json.loads(user_content)
prompt_candidates = parsed["candidates"]

assert len(prompt_candidates) == 1, prompt_candidates
candidate = prompt_candidates[0]

assert candidate["kind"] == "file", candidate
assert candidate["candidate_class"] == "root_doc", candidate
assert candidate["static_rank"] == 0, candidate

# "one" e "two" sono entrambi validi dopo strip.
# La stringa da 100 caratteri composta solo da 'x' viene esclusa.
assert candidate["signals"] == ["one", "two"], candidate
assert "path" not in candidate
assert candidates_norm == candidates_norm_before
print("PASS: CASE D")


# CASE E — campi di errore backend bounded
print("=== CASE E: backend error bounded ===")
reset_capture()


def mock_bounded_error(url, body, timeout):
    global captured_body, captured_timeout
    captured_body = deepcopy(body)
    captured_timeout = timeout
    return {
        "ok": False,
        "backend_unreachable": True,
        "error_type": "X" * 500,
        "error": "Y" * 1000,
    }


result_e = call_selector(
    candidates=[{"candidate_id": "root_doc:README.md"}],
    post_json=mock_bounded_error,
)

assert captured_body is not None
assert captured_timeout == TIMEOUT_SECONDS
assert result_e["ok"] is False, result_e
assert result_e["status"] == "unavailable", result_e
assert result_e["rationale"] == "backend_request_failed", result_e
assert result_e["backend_unreachable"] is True, result_e
assert len(result_e["error_type"]) == 120, result_e
assert len(result_e["error"]) == 500, result_e
assert result_e["planner_model"] == PLANNER_MODEL, result_e
assert result_e["planner_url"] == PLANNER_URL, result_e
assert result_e["timeout_seconds"] == TIMEOUT_SECONDS, result_e
assert result_e["keep_alive"] == KEEP_ALIVE, result_e
print("PASS: CASE E")


print("\n=== ALL R4S PROBE ASSERTIONS PASSED ===")
