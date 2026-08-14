from __future__ import annotations

from copy import deepcopy
import importlib
import importlib.util
import json
from pathlib import Path
from random import seed
import sys
from turtle import st
from typing import Any, Callable, NoReturn

from hypothesis import HealthCheck, given, settings
PROFILE_ORIENTATION_SELECTOR = "orientation.selector.contract.v1"
PROFILE_ORIENTATION_SHADOW_HELPERS = (
    "orientation.shadow_helpers.contract.v1"
)
PROFILE_ORIENTATION_SHADOW_EVALUATOR = (
    "orientation.shadow_evaluator.contract.v1"
)

_PROFILE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "profile_id": PROFILE_ORIENTATION_SELECTOR,
        "description": (
            "Validate the isolated orientation selector contract with deterministic "
            "cases and optional Hypothesis-generated inputs."
        ),
        "target_module": (
            "aicarmine_broker.application.controller.orientation_lane"
        ),
        "engines": ["deterministic", "hypothesis", "both"],
        "network_calls": False,
        "source_writes": False,
        "arbitrary_python": False,
        "properties": [
            {
                "name": "valid_ollama_envelope_and_request",
                "description": "Valid Ollama envelope and request body structure",
            },
            {
                "name": "model_selection_never_escapes_allowlist",
                "description": "Model selection stays within authorized candidate pool",
            },
            {
                "name": "runtime_metadata_cannot_be_forged",
                "description": "Runtime metadata cannot be forged by model output",
            },
            {
                "name": "empty_authorized_pool_skips_backend",
                "description": "Empty authorized pool skips backend call",
            },
            {
                "name": "input_and_model_duplicates_are_distinct",
                "description": "Input and model duplicates are tracked separately",
            },
            {
                "name": "first_non_empty_ollama_content_precedence",
                "description": "First non-empty Ollama content field takes precedence",
            },
            {
                "name": "candidate_prompt_fields_are_bounded",
                "description": "Candidate prompt fields are bounded before sending to model",
            },
            {
                "name": "valid_bounded_signals_are_preserved",
                "description": "Valid bounded signals are preserved in prompt",
            },
            {
                "name": "backend_errors_are_bounded",
                "description": "Backend errors are bounded in size",
            },
            {
                "name": "extractor_never_raises_for_json_like_values",
                "description": "Extractor never raises for JSON-like values",
            },
            {
                "name": "sanitizer_never_escapes_allowlist",
                "description": "Sanitizer never escapes allowlist",
            },
        ],
    },
    {
        "profile_id": PROFILE_ORIENTATION_SHADOW_HELPERS,
        "description": (
            "Validate shadow helper contracts with deterministic cases. "
            "Profile executes real tests against implemented helpers. "
            "Fails RED when helpers are absent, GREEN when correctly implemented."
        ),
        "target_module": (
            "aicarmine_broker.application.controller.orientation_lane"
        ),
        "engines": ["deterministic"],
        "network_calls": False,
        "source_writes": False,
        "arbitrary_python": False,
        "properties": [
            {
                "name": "active_mode_fails_closed_to_legacy",
                "description": "Active mode fails closed to legacy behavior",
            },
            {
                "name": "legacy_mode_never_requests_shadow",
                "description": "Legacy mode never requests shadow selection",
            },
            {
                "name": "shadow_mode_is_exact_match_only",
                "description": "Shadow mode performs exact match only",
            },
            {
                "name": "legacy_selection_uses_executed_plans",
                "description": "Legacy selection uses already executed plans",
            },
            {
                "name": "legacy_selection_ignores_unknown_paths",
                "description": "Legacy selection ignores unknown paths",
            },
            {
                "name": "legacy_selection_preserves_doc_then_area_order",
                "description": "Legacy selection preserves doc then area order",
            },
            {
                "name": "legacy_selection_deduplicates_candidate_ids",
                "description": "Legacy selection deduplicates candidate IDs",
            },
            {
                "name": "selection_metrics_report_exact_match",
                "description": "Selection metrics report exact match",
            },
            {
                "name": "selection_metrics_report_partial_overlap",
                "description": "Selection metrics report partial overlap",
            },
            {
                "name": "selection_metrics_are_bounded_and_deterministic",
                "description": "Selection metrics are bounded and deterministic",
            },
            {
                "name": "legacy_selection_handles_malformed_candidate_pool",
                "description": (
                    "Non-list and partially malformed candidate pools are ignored without "
                    "exceptions while valid candidate entries remain usable."
                ),
            },
            {
                "name": "legacy_selection_distinguishes_candidate_class",
                "description": (
                    "Document and area selections preserve candidate_class even when the "
                    "selected path string is identical."
                ),
            },
        ],
    },
    {
        "profile_id": PROFILE_ORIENTATION_SHADOW_EVALUATOR,
        "description": (
            "Validate the bounded initial-orientation shadow evaluator "
            "before runtime wiring and persistence."
        ),
        "target_module": (
            "aicarmine_broker.application.planner.loop"
        ),
        "engines": ["deterministic"],
        "network_calls": False,
        "source_writes": False,
        "arbitrary_python": False,
        "properties": [
            {
                "name": "legacy_mode_skips_shadow_callbacks",
                "description": (
                    "Legacy mode never builds candidates or calls the selector."
                ),
            },
            {
                "name": "active_mode_fails_closed_to_legacy",
                "description": "Active mode is temporarily treated as legacy.",
            },
            {
                "name": "root_result_must_be_ok",
                "description": "A missing or unsuccessful root result skips shadow evaluation.",
            },
            {
                "name": "empty_candidate_pool_skips_selector",
                "description": "An empty authorized pool never calls the selector.",
            },
            {
                "name": "successful_evaluation_calls_each_stage_once",
                "description": (
                    "A successful shadow evaluation calls each bounded stage once."
                ),
            },
            {
                "name": "legacy_plan_order_drives_comparison",
                "description": (
                    "Legacy selected IDs derive from executed plans, not pool order."
                ),
            },
            {
                "name": "candidate_pool_failure_fails_open",
                "description": (
                    "Candidate-pool failure leaves legacy authoritative."
                ),
            },
            {
                "name": "legacy_selection_failure_fails_open",
                "description": (
                    "Legacy-comparison failure leaves legacy authoritative."
                ),
            },
            {
                "name": "selector_failure_fails_open",
                "description": "Selector exceptions never block legacy execution.",
            },
            {
                "name": "selector_not_ready_fails_open",
                "description": (
                    "Unavailable or invalid selector results remain diagnostic."
                ),
            },
            {
                "name": "evaluation_output_is_bounded",
                "description": (
                    "The diagnostic result has bounded identifiers and messages."
                ),
            },
            {
                "name": "evaluation_is_deterministic_and_input_immutable",
                "description": (
                    "Repeated evaluation is deterministic and does not mutate input."
                ),
            },
        ],
    },
)


def _module_origin_status(
    root: Path,
    module_name: str,
) -> dict[str, Any]:
    try:
        spec = importlib.util.find_spec(module_name)
    except Exception as exc:
        return {
            "ok": False,
            "module": module_name,
            "error": "module_spec_failed",
            "error_type": type(exc).__name__,
            "message": str(exc)[:500],
        }
    origin_text = str(spec.origin or "") if spec is not None else ""
    if not origin_text or origin_text in {"built-in", "frozen"}:
        return {
            "ok": False,
            "module": module_name,
            "origin": origin_text,
            "error": "module_origin_unavailable",
        }
    try:
        origin = Path(origin_text).resolve()
        repo_root = root.resolve()
        origin.relative_to(repo_root)
    except Exception:
        return {
            "ok": False,
            "module": module_name,
            "origin": origin_text,
            "repo_root": str(root),
            "error": "module_outside_repo_root",
        }
    return {
        "ok": True,
        "module": module_name,
        "origin": str(origin),
        "repo_root": str(repo_root),
    }


def _bounded_int(
    args: dict[str, Any],
    name: str,
    
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = args.get(name, default)
    if isinstance(raw, bool):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _hypothesis_info() -> dict[str, Any]:
    spec = importlib.util.find_spec("hypothesis")
    if spec is None:
        return {
            "available": False,
            "version": "",
            "error": "hypothesis_not_installed",
        }
    try:
        module = importlib.import_module("hypothesis")
        from hypothesis import HealthCheck, given, seed, settings
        from hypothesis import strategies as st
    except Exception as exc:
        return {
            "available": False,
            "version": "",
            "error": "hypothesis_import_failed",
            "error_type": type(exc).__name__,
            "message": str(exc)[:500],
        }
    return {
        "available": True,
        "version": str(getattr(module, "__version__", "")),
        "error": "",
    }


def repo_probe_profiles(args: dict[str, Any], root: Path) -> dict[str, Any]:
    del args
    target_module = str(_PROFILE_SPECS[0]["target_module"])
    origin = _module_origin_status(root, target_module)
    return {
        "ok": origin.get("ok") is True,
        "tool": "repo_probe_profiles",
        "repo_root": str(root),
        "python_executable": sys.executable,
        "profiles": [dict(item) for item in _PROFILE_SPECS],
        "profile_count": len(_PROFILE_SPECS),
        "target_module_origin": origin,
        "hypothesis": _hypothesis_info(),
        "source_writes_performed": False,
        "network_calls_performed": False,
        "arbitrary_python_allowed": False,
    }


def _case(
    name: str,
    callback: Callable[[], dict[str, Any] | None],
) -> dict[str, Any]:
    try:
        details = callback() or {}
    except AssertionError as exc:
        return {
            "name": name,
            "ok": False,
            "error": "assertion_failed",
            "message": str(exc)[:1000],
        }
    except Exception as exc:
        return {
            "name": name,
            "ok": False,
            "error": "unexpected_exception",
            "error_type": type(exc).__name__,
            "message": str(exc)[:1000],
        }
    return {"name": name, "ok": True, "details": details}


def _orientation_call(
    selector: Callable[..., dict[str, Any]],
    response_factory: Callable[[str, dict[str, Any], int], dict[str, Any]],
    
    candidates: list[dict[str, Any]] | None = None,
    semantic_intent: dict[str, Any] | None = None,
    goal: str = "Inspect the repository",
    max_selected: int = 4,
) -> tuple[dict[str, Any], dict[str, Any]]:
    captured: dict[str, Any] = {}

    def post_json(
        url: str,
        body: dict[str, Any],
        timeout: int,
    ) -> dict[str, Any]:
        captured["url"] = url
        captured["body"] = deepcopy(body)
        captured["timeout"] = timeout
        return response_factory(url, body, timeout)

    selected_candidates = candidates or [
        {
            "candidate_id": "root_doc:README.md",
            "path": "README.md",
            "kind": "file",
            "candidate_class": "root_doc",
            "static_rank": 0,
            "signals": ["existing_file", "doc_or_config"],
        },
        {
            "candidate_id": "root_area:services",
            "path": "services",
            "kind": "dir",
            "candidate_class": "root_area",
            "static_rank": 1,
            "signals": ["existing_dir", "non_low_signal"],
        },
    ]

    result = selector(
        goal=goal,
        semantic_intent=semantic_intent or {"target_kind": "repository"},
        candidates=selected_candidates,
        post_json=post_json,
        planner_url="http://127.0.0.1:11434/api/chat",
        planner_model="Qwen_Qwen3.6-35B_v1:latest",
        keep_alive="30m",
        timeout_seconds=37,
        max_selected=max_selected,
    )
    return result, captured


def _deterministic_orientation_profile() -> dict[str, Any]:
    module = importlib.import_module(
        "aicarmine_broker.application.controller.orientation_lane"
    )
    selector = getattr(module, "controller_orientation_model_select")
    sanitizer = getattr(module, "sanitize_orientation_selection")

    cases: list[dict[str, Any]] = []

    def valid_envelope() -> dict[str, Any]:
        forged_payload = {
            "decision": "select",
            "selected_candidate_ids": [
                "root_doc:README.md",
                "root_area:services",
            ],
            "rationale": "bounded selection",
            "confidence": 0.9,
            "planner_model": "forged-model",
            "planner_url": "http://forged.invalid",
            "timeout_seconds": 999999,
            "keep_alive": "forged",
        }

        result, captured = _orientation_call(
            selector,
            lambda _url, _body, _timeout: {
                "model": "ignored-envelope-model",
                "message": {
                    "role": "assistant",
                    "content": json.dumps(forged_payload),
                },
                "done": True,
            },
        )

        assert result.get("ok") is True, result
        assert result.get("status") == "ready", result
        assert result.get("selected_candidate_ids") == [
            "root_doc:README.md",
            "root_area:services",
        ], result
        assert result.get("planner_model") == "Qwen_Qwen3.6-35B_v1:latest", result
        assert result.get("planner_url") == (
            "http://127.0.0.1:11434/api/chat"
        ), result
        assert result.get("timeout_seconds") == 37, result
        assert result.get("keep_alive") == "30m", result

        body = captured.get("body")
        assert isinstance(body, dict), captured
        assert body.get("model") == "Qwen_Qwen3.6-35B_v1:latest", body
        assert body.get("stream") is False, body
        assert body.get("think") is False, body
        assert body.get("format") == "json", body
        assert body.get("keep_alive") == "30m", body
        assert body.get("options") == {"temperature": 0}, body
        assert "temperature" not in body, body
        assert "tools" not in body, body
        assert captured.get("timeout") == 37, captured

        messages = body.get("messages")
        assert isinstance(messages, list) and len(messages) >= 2, body
        user_content = messages[-1].get("content")
        request = json.loads(user_content)
        assert request.get("schema") == (
            "orientation_model_selection_request.v1"
        ), request
        prompt_candidates = request.get("candidates")
        assert isinstance(prompt_candidates, list), request
        assert [
            item.get("candidate_id") for item in prompt_candidates
        ] == [
            "root_doc:README.md",
            "root_area:services",
        ], prompt_candidates
        assert all("path" not in item for item in prompt_candidates), (
            prompt_candidates
        )

        return {
            "selected_candidate_ids": result["selected_candidate_ids"],
            "request_candidate_count": len(prompt_candidates),
        }

    cases.append(_case("valid_ollama_envelope_and_request", valid_envelope))

    def duplicate_and_unknown() -> dict[str, Any]:
        result, _captured = _orientation_call(
            selector,
            lambda _url, _body, _timeout: {
                "message": {
                    "content": json.dumps(
                        {
                            "decision": "select",
                            "selected_candidate_ids": [
                                "root_doc:README.md",
                                "root_doc:README.md",
                                "root_doc:INVENTED.md",
                                "root_area:services",
                            ],
                        }
                    )
                }
            },
        )
        assert result.get("ok") is True, result
        assert result.get("selected_candidate_ids") == [
            "root_doc:README.md",
            "root_area:services",
        ], result
        assert "root_doc:README.md" in result.get(
            "duplicate_candidate_ids", []
        ), result
        assert "root_doc:INVENTED.md" in result.get(
            "unknown_candidate_ids", []
        ), result
        return {
            "duplicates": result.get("duplicate_candidate_ids"),
            "unknown": result.get("unknown_candidate_ids"),
        }

    cases.append(_case("duplicate_and_unknown_selection", duplicate_and_unknown))

    def backend_error() -> dict[str, Any]:
        result, _captured = _orientation_call(
            selector,
            lambda _url, _body, _timeout: {
                "ok": False,
                "backend_unreachable": True,
                "error_type": "URLError",
                "error": "connection refused",
            },
        )
        assert result.get("ok") is False, result
        assert result.get("status") == "unavailable", result
        assert result.get("rationale") == "backend_request_failed", result
        assert result.get("backend_unreachable") is True, result
        assert result.get("error_type") == "URLError", result
        assert result.get("planner_model") == "Qwen_Qwen3.6-35B_v1:latest", (
            result
        )
        return {"error_type": result.get("error_type")}

    cases.append(_case("backend_error_envelope", backend_error))

    def backend_exception() -> dict[str, Any]:
        def raise_connection(
            _url: str,
            _body: dict[str, Any],
            _timeout: int,
        ) -> dict[str, Any]:
            raise ConnectionError("refused")

        result, _captured = _orientation_call(selector, raise_connection)
        assert result.get("ok") is False, result
        assert result.get("status") == "unavailable", result
        assert result.get("rationale") == "backend_exception", result
        assert result.get("error_type") == "ConnectionError", result
        assert result.get("error") == "refused", result
        return {"error_type": result.get("error_type")}

    cases.append(_case("backend_exception", backend_exception))

    def invalid_json() -> dict[str, Any]:
        result, _captured = _orientation_call(
            selector,
            lambda _url, _body, _timeout: {
                "message": {"content": "{invalid"}
            },
        )
        assert result.get("ok") is False, result
        assert result.get("status") == "invalid", result
        assert result.get("rationale") == "invalid_json_response", result
        return {}

    cases.append(_case("invalid_json", invalid_json))

    def json_list() -> dict[str, Any]:
        result, _captured = _orientation_call(
            selector,
            lambda _url, _body, _timeout: {
                "message": {"content": "[1, 2, 3]"}
            },
        )
        assert result.get("ok") is False, result
        assert result.get("status") == "invalid", result
        assert result.get("rationale") == "json_response_not_object", result
        return {}

    cases.append(_case("json_non_object", json_list))

    def message_not_dict() -> dict[str, Any]:
        result, _captured = _orientation_call(
            selector,
            lambda _url, _body, _timeout: {"message": "bad"},
        )
        assert result.get("ok") is False, result
        assert result.get("status") == "invalid", result
        assert result.get("rationale") == "empty_model_content", result
        return {}

    cases.append(_case("message_not_dict", message_not_dict))

    def bool_confidence() -> dict[str, Any]:
        result = sanitizer(
            {
                "decision": "select",
                "selected_candidate_ids": ["root_doc:README.md"],
                "confidence": True,
            },
            valid_candidate_ids={"root_doc:README.md"},
            max_selected=1,
        )
        assert result.get("ok") is True, result
        assert result.get("confidence") is None, result
        return {}

    cases.append(_case("confidence_bool_rejected", bool_confidence))

    def direct_dict_compatibility() -> dict[str, Any]:
        response = {
            "decision": "select",
            "selected_candidate_ids": ["root_doc:README.md"],
            "planner_model": "forged",
        }
        response_before = deepcopy(response)

        result, _captured = _orientation_call(
            selector,
            lambda _url, _body, _timeout: response,
        )
        assert result.get("ok") is True, result
        assert result.get("planner_model") == "Qwen_Qwen3.6-35B_v1:latest", (
            result
        )
        assert response == response_before, (response, response_before)
        return {}

    cases.append(_case("direct_dict_compatibility", direct_dict_compatibility))

    def first_non_empty_ollama_content() -> dict[str, Any]:
        """Caso: first_non_empty_ollama_content_precedence

        Il mock response deve essere:
        {
          "response": "",
          "message": {
            "content": json.dumps({
              "decision": "select",
              "selected_candidate_ids": [
                "root_doc:README.md"
              ]
            })
          },
          "partial_content": "{invalid"
        }

        Assert:
        - ok=True;
        - status="ready";
        - selected_candidate_ids == ["root_doc:README.md"].
        """
        result, _captured = _orientation_call(
            selector,
            lambda _url, _body, _timeout: {
                "response": "",
                "message": {
                    "content": json.dumps(
                        {
                            "decision": "select",
                            "selected_candidate_ids": [
                                "root_doc:README.md",
                            ],
                        }
                    ),
                },
                "partial_content": "{invalid",
            },
        )
        assert result.get("ok") is True, result
        assert result.get("status") == "ready", result
        assert result.get("selected_candidate_ids") == [
            "root_doc:README.md",
        ], result
        return {}

    cases.append(_case("first_non_empty_ollama_content_precedence", first_non_empty_ollama_content))

    def duplicate_input_candidate_ids_are_unique() -> dict[str, Any]:
        """Caso: duplicate_input_candidate_ids_are_unique

        Candidate input:
        [
          README,
          README,
          README,
          services
        ]

        Il mock modello deve selezionare:
        [
          README,
          README,
          INVENTED,
          services
        ]

        Assert:
        - duplicate_input_candidate_ids == ["root_doc:README.md"];
        - duplicate_candidate_ids == ["root_doc:README.md"];
        - unknown_candidate_ids == ["root_doc:INVENTED.md"];
        - selected_candidate_ids == [
            "root_doc:README.md",
            "root_area:services"
          ].

        Le due diagnostiche non devono sovrascriversi.
        """
        candidates = [
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

        def model_response(url, body, timeout):
            parsed = json.loads(body["messages"][1]["content"])
            prompt_ids = [c["candidate_id"] for c in parsed["candidates"]]
            # Il modello emette: README due volte + INVENTED + services
            return {
                "model": "Qwen_Qwen3.6-35B_v1:latest",
                "message": {
                    "role": "assistant",
                    "content": json.dumps({
                        "decision": "select",
                        "selected_candidate_ids": [
                            "root_doc:README.md",
                            "root_doc:README.md",
                            "root_doc:INVENTED.md",
                            "root_area:services",
                        ],
                        "rationale": "bounded selection",
                        "confidence": 0.9,
                    }),
                },
                "done": True,
            }

        result, _captured = _orientation_call(
            selector,
            model_response,
            candidates=candidates,
        )

        assert result.get("ok") is True, result
        assert result.get("duplicate_input_candidate_ids") == [
            "root_doc:README.md",
        ], result
        assert result.get("duplicate_candidate_ids") == [
            "root_doc:README.md",
        ], result
        assert result.get("unknown_candidate_ids") == [
            "root_doc:INVENTED.md",
        ], result
        assert result.get("selected_candidate_ids") == [
            "root_doc:README.md",
            "root_area:services",
        ], result
        return {}

    cases.append(_case("duplicate_input_candidate_ids_are_unique", duplicate_input_candidate_ids_are_unique))

    def valid_bounded_signals_are_preserved() -> dict[str, Any]:
        """Caso: valid_bounded_signals_are_preserved

        Candidate input:
        {
          "candidate_id": "root_doc:README.md",
          "kind": "  file  ",
          "candidate_class": "  root_doc  ",
          "static_rank": true,
          "signals": [
            "x",
            "aaa",
            "  normal  ",
            "",
            "z" ripetuto 100 volte
          ]
        }

        Assert sul candidato inviato nel JSON user:
        - kind == "file";
        - candidate_class == "root_doc";
        - static_rank == 0;
        - signals == ["x", "aaa", "normal", primi 80 caratteri della stringa di z];
        - nessuna stringa vuota;
        - ogni signal ha lunghezza <= 80;
        - ordine preservato;
        - input originale immutato.

        Il profilo non deve giudicare semanticamente il contenuto dei signal.
        """
        candidates = [
            {
                "candidate_id": "root_doc:README.md",
                "kind": "  file  ",
                "candidate_class": "  root_doc  ",
                "static_rank": True,
                "signals": [
                    "x",
                    "aaa",
                    "  normal  ",
                    "",
                    "z" * 100,
                ],
            },
        ]
        candidates_before = deepcopy(candidates)

        def capture_request(url, body, timeout):
            return {
                "model": "Qwen_Qwen3.6-35B_v1:latest",
                "message": {
                    "role": "assistant",
                    "content": json.dumps({
                        "decision": "select",
                        "selected_candidate_ids": ["root_doc:README.md"],
                        "rationale": "bounded selection",
                        "confidence": 0.9,
                    }),
                },
                "done": True,
            }

        result, captured = _orientation_call(
            selector,
            capture_request,
            candidates=candidates,
        )

        assert result.get("ok") is True, result

        body = captured.get("body")
        messages = body.get("messages") if isinstance(body, dict) else []
        request = json.loads(messages[-1]["content"])
        prompt_candidates = request.get("candidates")

        assert len(prompt_candidates) == 1, prompt_candidates
        candidate = prompt_candidates[0]

        assert candidate.get("kind") == "file", candidate
        assert candidate.get("candidate_class") == "root_doc", candidate
        assert candidate.get("static_rank") == 0, candidate

        signals = candidate.get("signals", [])
        # Preserve every non-empty bounded string after strip.
        # Do not apply semantic filtering based on repeated characters.
        expected_signals = ["x", "aaa", "normal", "z" * 80]
        assert signals == expected_signals, f"Expected {expected_signals!r}, got {signals!r}"
        assert all(len(s) <= 80 for s in signals), signals
        assert all(s for s in signals), signals

        assert candidates == candidates_before, (candidates, candidates_before)

        return {}

    cases.append(_case("valid_bounded_signals_are_preserved", valid_bounded_signals_are_preserved))

    def oversized_candidate_id() -> dict[str, Any]:
        oversized = "x" * 501
        candidates = [
            {
                "candidate_id": oversized,
                "path": "ignored",
                "kind": "file",
                "candidate_class": "root_doc",
                "static_rank": 0,
                "signals": [],
            },
            {
                "candidate_id": "root_doc:README.md",
                "path": "README.md",
                "kind": "file",
                "candidate_class": "root_doc",
                "static_rank": 1,
                "signals": [],
            },
        ]

        result, captured = _orientation_call(
            selector,
            lambda _url, _body, _timeout: {
                "decision": "select",
                "selected_candidate_ids": [oversized],
            },
            candidates=candidates,
        )
        body = captured.get("body")
        messages = body.get("messages") if isinstance(body, dict) else []
        request = json.loads(messages[-1]["content"])
        prompt_ids = [
            item["candidate_id"] for item in request["candidates"]
        ]
        assert oversized not in prompt_ids, prompt_ids
        assert result.get("ok") is False, result
        assert oversized in result.get("unknown_candidate_ids", []), result
        return {"prompt_candidate_ids": prompt_ids}

    cases.append(_case("oversized_candidate_id_excluded", oversized_candidate_id))

    def empty_authorized_pool() -> dict[str, Any]:
        """Caso: empty_authorized_pool_skips_backend

        Candidate input:
        [
          {"candidate_id": ""},
          {"candidate_id": "x" * 501},
          "not-a-dict"
        ]

        La response factory deve sollevare:
        AssertionError(
            "backend must not be called for an empty authorized pool"
        )

        Assert:
        - result["ok"] is False;
        - result["status"] == "unavailable";
        - result["rationale"] == "no_valid_candidates_in_pool";
        - captured == {};
        - planner_model autorevole presente;
        - planner_url autorevole presente;
        - timeout_seconds autorevole presente;
        - keep_alive autorevole presente;
        - candidates invariati.
        """
        candidates = [
            {"candidate_id": ""},
            {"candidate_id": "x" * 501},
            "not-a-dict",
        ]
        candidates_before = deepcopy(candidates)

        def raise_empty_pool_error(url, body, timeout):
            raise AssertionError(
                "backend must not be called for an empty authorized pool"
            )

        result, captured = _orientation_call(
            selector,
            raise_empty_pool_error,
            candidates=candidates,
        )

        assert result.get("ok") is False, result
        assert result.get("status") == "unavailable", result
        assert result.get("rationale") == "no_valid_candidates_in_pool", result
        assert captured == {}, captured
        assert result.get("planner_model") == "Qwen_Qwen3.6-35B_v1:latest", result
        assert result.get("planner_url") == "http://127.0.0.1:11434/api/chat", result
        assert result.get("timeout_seconds") == 37, result
        assert result.get("keep_alive") == "30m", result
        assert candidates == candidates_before, (candidates, candidates_before)

        return {}

    cases.append(_case("empty_authorized_pool_skips_backend", empty_authorized_pool))

    def backend_errors_are_bounded() -> dict[str, Any]:
        """Caso: backend_errors_are_bounded

        Mock response:
        {
            "ok": False,
            "backend_unreachable": True,
            "error_type": "X" * 500,
            "error": "Y" * 1000,
        }

        Assert:
        - result["ok"] is False;
        - result["status"] == "unavailable";
        - result["rationale"] == "backend_request_failed";
        - result["backend_unreachable"] is True;
        - result["error_type"] == "X" * 120;
        - len(result["error_type"]) == 120;
        - result["error"] == "Y" * 500;
        - len(result["error"]) == 500;
        - metadata runtime autorevoli presenti.
        """
        result, _captured = _orientation_call(
            selector,
            lambda _url, _body, _timeout: {
                "ok": False,
                "backend_unreachable": True,
                "error_type": "X" * 500,
                "error": "Y" * 1000,
            },
        )

        assert result.get("ok") is False, result
        assert result.get("status") == "unavailable", result
        assert result.get("rationale") == "backend_request_failed", result
        assert result.get("backend_unreachable") is True, result
        assert result.get("error_type") == "X" * 120, result
        assert len(result.get("error_type")) == 120, result
        assert result.get("error") == "Y" * 500, result
        assert len(result.get("error")) == 500, result
        assert result.get("planner_model") == "Qwen_Qwen3.6-35B_v1:latest", result
        assert result.get("planner_url") == "http://127.0.0.1:11434/api/chat", result
        assert result.get("timeout_seconds") == 37, result
        assert result.get("keep_alive") == "30m", result

        return {
            "error_type": result.get("error_type"),
            "error": result.get("error"),
        }

    cases.append(_case("backend_errors_are_bounded", backend_errors_are_bounded))

    def semantic_intent_non_json_native() -> dict[str, Any]:
        semantic_intent = {"path": Path("services")}
        semantic_before = deepcopy(semantic_intent)
        candidates = [
            {
                "candidate_id": "root_doc:README.md",
                "path": "README.md",
                "kind": "file",
                "candidate_class": "root_doc",
                "static_rank": 0,
                "signals": [],
            }
        ]
        candidates_before = deepcopy(candidates)

        result, captured = _orientation_call(
            selector,
            lambda _url, _body, _timeout: {
                "decision": "select",
                "selected_candidate_ids": ["root_doc:README.md"],
            },
            semantic_intent=semantic_intent,
            candidates=candidates,
        )
        assert result.get("ok") is True, result
        body = captured["body"]
        request = json.loads(body["messages"][-1]["content"])
        assert request["semantic_intent"]["path"] == "services", request
        assert semantic_intent == semantic_before, (
            semantic_intent,
            semantic_before,
        )
        assert candidates == candidates_before, (
            candidates,
            candidates_before,
        )
        return {}

    cases.append(
        _case(
            "semantic_intent_json_safe_and_inputs_immutable",
            semantic_intent_non_json_native,
        )
    )

    passed = sum(1 for item in cases if item.get("ok") is True)
    failed = len(cases) - passed
    return {
        "ok": failed == 0,
        "engine": "deterministic",
        "case_count": len(cases),
        "passed": passed,
        "failed": failed,
        "cases": cases,
    }


def _hypothesis_orientation_profile(
    
    max_examples: int,
    seed_value: int,
) -> dict[str, Any]:
    info = _hypothesis_info()
    if not info.get("available"):
        return {
            "ok": False,
            "engine": "hypothesis",
            "error": info.get("error") or "hypothesis_unavailable",
            "hypothesis": info,
            "properties": [],
        }

#    from hypothesis import HealthCheck, given, seed, settings
#    from hypothesis import strategies as st

    module = importlib.import_module(
        "aicarmine_broker.application.controller.orientation_lane"
    )
    extractor = getattr(module, "_extract_orientation_response_object")
    sanitizer = getattr(module, "sanitize_orientation_selection")

    properties: list[dict[str, Any]] = []

    json_scalars = st.one_of(
        st.none(),
        st.booleans(),
        st.integers(),
        st.floats(allow_nan=False, allow_infinity=False),
        st.text(max_size=200),
    )
    json_values = st.recursive(
        json_scalars,
        lambda children: st.one_of(
            st.lists(children, max_size=8),
            st.dictionaries(
                st.text(min_size=0, max_size=40),
                children,
                max_size=8,
            ),
        ),
        max_leaves=30,
    )

    profile_settings = settings(
        max_examples=max_examples,
        database=None,
        derandomize=True,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )

    def run_property(
        name: str,
        callback: Callable[[], None],
    ) -> None:
        try:
            callback()
        except Exception as exc:
            properties.append(
                {
                    "name": name,
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:2000],
                }
            )
        else:
            properties.append(
                {
                    "name": name,
                    "ok": True,
                    "examples": max_examples,
                }
            )

    def property_extractor_never_raises() -> None:
        @seed(seed_value)
        @profile_settings
        @given(json_values)
        def check(value: Any) -> None:
            parsed, reason = extractor(value)
            assert parsed is None or isinstance(parsed, dict)
            assert isinstance(reason, str) and reason

        check()

    run_property(
        "extractor_never_raises_for_json_like_values",
        property_extractor_never_raises,
    )

    def property_sanitizer_preserves_allowlist() -> None:
        @seed(seed_value)
        @profile_settings
        @given(
            st.lists(st.text(max_size=80), max_size=20),
            st.sets(st.text(max_size=80), max_size=20),
            st.integers(min_value=0, max_value=20),
            st.one_of(
                st.none(),
                st.booleans(),
                st.integers(),
                st.floats(allow_nan=False, allow_infinity=False),
            ),
        )
        def check(
            selected: list[str],
            valid: set[str],
            max_selected: int,
            confidence: Any,
        ) -> None:
            response = {
                "decision": "select",
                "selected_candidate_ids": selected,
                "confidence": confidence,
            }
            response_before = deepcopy(response)
            result = sanitizer(
                response,
                valid_candidate_ids=valid,
                max_selected=max_selected,
            )
            returned = result.get("selected_candidate_ids")
            assert isinstance(returned, list)
            assert set(returned).issubset(valid)
            assert len(returned) <= max_selected
            assert len(returned) == len(set(returned))
            assert response == response_before
            if result.get("ok"):
                assert result.get("status") == "ready"
                assert returned
            else:
                assert result.get("status") == "invalid"

        check()

    run_property(
        "sanitizer_never_escapes_allowlist",
        property_sanitizer_preserves_allowlist,
    )

    ok_value = all(item.get("ok") is True for item in properties)
    return {
        "ok": ok_value,
        "engine": "hypothesis",
        "hypothesis": info,
        "max_examples": max_examples,
        "seed": seed_value,
        "property_count": len(properties),
        "properties": properties,
        "database_enabled": False,
        "source_writes_performed": False,
    }


def _required_callable(module: Any, name: str) -> Callable[..., Any]:
    """Helper per ottenere un callable da un modulo.

    Restituisce il callable se presente, altrimenti solleva AssertionError.
    """
    value = getattr(module, name, None)
    assert callable(value), f"missing_callable:{name}"
    return value


def _fixture_candidate_pool() -> list[dict[str, Any]]:
    """Fixture deterministica con candidati di prova."""
    return [
        {
            "candidate_id": "root_doc:AGENTS.md",
            "path": "AGENTS.md",
            "kind": "file",
            "candidate_class": "root_doc",
            "static_rank": 0,
            "signals": ["doc_or_config"],
        },
        {
            "candidate_id": "root_doc:README.md",
            "path": "README.md",
            "kind": "file",
            "candidate_class": "root_doc",
            "static_rank": 1,
            "signals": ["doc_or_config"],
        },
        {
            "candidate_id": "root_doc:pyproject.toml",
            "path": "pyproject.toml",
            "kind": "file",
            "candidate_class": "root_doc",
            "static_rank": 2,
            "signals": ["config"],
        },
        {
            "candidate_id": "root_area:services",
            "path": "services",
            "kind": "dir",
            "candidate_class": "root_area",
            "static_rank": 3,
            "signals": ["non_low_signal"],
        },
        {
            "candidate_id": "root_area:docs",
            "path": "docs",
            "kind": "dir",
            "candidate_class": "root_area",
            "static_rank": 4,
            "signals": [],
        },
        {
            "candidate_id": "root_area:scripts",
            "path": "scripts",
            "kind": "dir",
            "candidate_class": "root_area",
            "static_rank": 5,
            "signals": [],
        },
    ]


def _deterministic_orientation_shadow_helpers_profile() -> dict[str, Any]:
    """Deterministic profile per shadow helpers.

    Produce RED quando i tre helper sono assenti dal runtime.
    Produce GREEN quando gli helper sono implementati correttamente.
    """
    module = importlib.import_module(
        "aicarmine_broker.application.controller.orientation_lane"
    )

    # Fixture candidate pool con tutti gli ID attesi
    fixture_pool = _fixture_candidate_pool()

    cases: list[dict[str, Any]] = []

    def case_active_mode_fails_closed_to_legacy() -> dict[str, Any]:
        effective_mode = _required_callable(module, "orientation_shadow_effective_mode")
        assert effective_mode("active") == "legacy", \
            f"expected 'legacy', got '{effective_mode('active')}'"
        assert effective_mode(" ACTIVE ") == "legacy", \
            f"expected 'legacy' after normalization, got '{effective_mode(' ACTIVE ')}'"
        return {}

    cases.append(_case("active_mode_fails_closed_to_legacy", case_active_mode_fails_closed_to_legacy))

    def case_legacy_mode_never_requests_shadow() -> dict[str, Any]:
        effective_mode = _required_callable(module, "orientation_shadow_effective_mode")
        assert effective_mode("legacy") == "legacy"
        assert effective_mode(" LEGACY ") == "legacy"
        assert effective_mode("") == "legacy"
        assert effective_mode("unknown") == "legacy"
        assert effective_mode(None) == "legacy"
        assert effective_mode(123) == "legacy"
        assert effective_mode({}) == "legacy"
        return {}

    cases.append(_case("legacy_mode_never_requests_shadow", case_legacy_mode_never_requests_shadow))

    def case_shadow_mode_is_exact_only() -> dict[str, Any]:
        effective_mode = _required_callable(module, "orientation_shadow_effective_mode")
        assert effective_mode("shadow") == "shadow"
        assert effective_mode(" SHADOW ") == "shadow"
        assert effective_mode("shadowing") == "legacy"
        assert effective_mode("active-shadow") == "legacy"
        assert effective_mode(True) == "legacy"
        return {}

    cases.append(_case("shadow_mode_is_exact_match_only", case_shadow_mode_is_exact_only))

    doc_plan_ok = {
        "arguments": {
            "paths": ["README.md", "AGENTS.md"],
        },
    }
    area_plans_ok = [
        {
            "arguments": {
                "path": "services",
            },
        },
        {
            "arguments": {
                "path": "docs",
            },
        },
    ]

    # Order preservation case - candidate pool contains ALL expected IDs but in different order
    order_pool = [
        {
            "candidate_id": "root_area:docs",
            "path": "docs",
            "kind": "dir",
            "candidate_class": "root_area",
            "static_rank": 0,
            "signals": [],
        },
        {
            "candidate_id": "root_doc:AGENTS.md",
            "path": "AGENTS.md",
            "kind": "file",
            "candidate_class": "root_doc",
            "static_rank": 1,
            "signals": ["doc_or_config"],
        },
        {
            "candidate_id": "root_area:services",
            "path": "services",
            "kind": "dir",
            "candidate_class": "root_area",
            "static_rank": 2,
            "signals": ["non_low_signal"],
        },
        {
            "candidate_id": "root_doc:README.md",
            "path": "README.md",
            "kind": "file",
            "candidate_class": "root_doc",
            "static_rank": 3,
            "signals": ["doc_or_config"],
        },
    ]
    doc_plan_ordered = {
        "arguments": {
            "paths": ["README.md", "AGENTS.md"],
        },
    }
    area_plans_ordered = [
        {
            "arguments": {
                "path": "services",
            },
        },
        {
            "arguments": {
                "path": "docs",
            },
        },
    ]

    def case_legacy_selection_uses_executed_plans() -> dict[str, Any]:
        legacy_selected_ids = _required_callable(module, "orientation_legacy_selected_candidate_ids")
        result = legacy_selected_ids(candidates=order_pool, doc_plan=doc_plan_ok, area_plans=area_plans_ok)
        expected = [
            "root_doc:README.md",
            "root_doc:AGENTS.md",
            "root_area:services",
            "root_area:docs",
        ]
        assert result == expected, f"expected {expected!r}, got {result!r}"
        return {}

    cases.append(_case("legacy_selection_uses_executed_plans", case_legacy_selection_uses_executed_plans))

    def case_legacy_selection_ignores_unknown_paths() -> dict[str, Any]:
        legacy_selected_ids = _required_callable(module, "orientation_legacy_selected_candidate_ids")
        doc_plan_unknown = {
            "arguments": {
                "paths": ["UNKNOWN.md", "README.md"],
            },
        }
        result = legacy_selected_ids(candidates=order_pool, doc_plan=doc_plan_unknown, area_plans=[])
        # UNKNOWN.md non è nel pool, quindi non deve comparire nel risultato
        assert "root_doc:UNKNOWN.md" not in result, \
            f"unknown path should be ignored, got {result!r}"
        assert "root_doc:README.md" in result
        return {}

    cases.append(_case("legacy_selection_ignores_unknown_paths", case_legacy_selection_ignores_unknown_paths))

    def case_legacy_selection_preserves_doc_then_area_order() -> dict[str, Any]:
        legacy_selected_ids = _required_callable(module, "orientation_legacy_selected_candidate_ids")
        # Candidate pool con tutti gli ID attesi ma in ordine diverso dai plan
        candidates_different_order = order_pool
        doc_plan_ordered = {
            "arguments": {
                "paths": ["README.md", "AGENTS.md"],
            },
        }
        area_plans_ordered = [
            {
                "arguments": {
                    "path": "services",
                },
            },
            {
                "arguments": {
                    "path": "docs",
                },
            },
        ]
        result = legacy_selected_ids(candidates=candidates_different_order, doc_plan=doc_plan_ordered, area_plans=area_plans_ordered)
        # Ordine dei plan prevale su quello del pool
        assert result == ["root_doc:README.md", "root_doc:AGENTS.md", "root_area:services", "root_area:docs"], \
            f"plan order should prevail, got {result!r}"
        return {}

    cases.append(_case("legacy_selection_preserves_doc_then_area_order", case_legacy_selection_preserves_doc_then_area_order))

    def case_legacy_selection_deduplicates_candidate_ids() -> dict[str, Any]:
        legacy_selected_ids = _required_callable(module, "orientation_legacy_selected_candidate_ids")
        doc_plan_dup = {
            "arguments": {
                "paths": ["README.md", "README.md", "AGENTS.md"],
            },
        }
        area_plans_dup = [
            {
                "arguments": {
                    "path": "services",
                },
            },
            {
                "arguments": {
                    "path": "services",
                },
            },
        ]
        result = legacy_selected_ids(candidates=order_pool, doc_plan=doc_plan_dup, area_plans=area_plans_dup)
        assert len(result) == 3, f"expected 3 unique IDs, got {len(result)}: {result}"
        assert result.count("root_doc:README.md") == 1
        assert result.count("root_area:services") == 1
        return {}

    cases.append(_case("legacy_selection_deduplicates_candidate_ids", case_legacy_selection_deduplicates_candidate_ids))

    def case_legacy_selection_handles_missing_or_malformed_plans() -> dict[str, Any]:
        legacy_selected_ids = _required_callable(module, "orientation_legacy_selected_candidate_ids")
        # Usa sempre un candidate pool non vuoto per discriminare i casi malformed
        malformed_pool = order_pool

        # Caso A: Nessun plan
        assert legacy_selected_ids(candidates=malformed_pool, doc_plan=None, area_plans=[]) == []

        # Caso B: arguments document non-dict
        assert legacy_selected_ids(candidates=malformed_pool, doc_plan={"arguments": "bad"}, area_plans=[]) == []

        # Caso C: paths non-list
        assert legacy_selected_ids(candidates=malformed_pool, doc_plan={"arguments": {"paths": "README.md"}}, area_plans=[]) == []

        # Caso D: paths misti, con una parte valida
        mixed_document_paths = [None, 123, {}, "UNKNOWN.md", "README.md"]
        result = legacy_selected_ids(
            candidates=malformed_pool,
            doc_plan={"arguments": {"paths": mixed_document_paths}},
            area_plans=[],
        )
        assert result == ["root_doc:README.md"], \
            f"should filter to only valid, got {result!r}"

        # Caso E: area_plans non-list
        assert legacy_selected_ids(candidates=malformed_pool, doc_plan=None, area_plans="bad") == []

        # Caso F: area plans misti, con una parte valida
        mixed_area_plans = [
            "bad",
            {"arguments": "bad"},
            {"arguments": {"path": None}},
            {"arguments": {"path": 123}},
            {"arguments": {"path": "missing-area"}},
            {"arguments": {"path": "services"}},
        ]
        result = legacy_selected_ids(candidates=malformed_pool, doc_plan=None, area_plans=mixed_area_plans)
        assert result == ["root_area:services"], \
            f"should filter to only valid, got {result!r}"

        # Caso G: Documenti validi più aree parzialmente malformate
        doc_plan_valid = {"arguments": {"paths": ["README.md"]}}
        mixed_area_plans_partial = [
            {"arguments": "bad"},
            {"arguments": {"path": "services"}},
        ]
        result = legacy_selected_ids(
            candidates=malformed_pool,
            doc_plan=doc_plan_valid,
            area_plans=mixed_area_plans_partial,
        )
        assert result == ["root_doc:README.md", "root_area:services"], \
            f"valid sections should produce results despite malformed sections, got {result!r}"

        return {}

    cases.append(_case("legacy_selection_handles_missing_or_malformed_plans", case_legacy_selection_handles_missing_or_malformed_plans))

    def case_legacy_selection_handles_malformed_candidate_pool() -> dict[str, Any]:
        legacy_selected_ids = _required_callable(module, "orientation_legacy_selected_candidate_ids")

        # Caso A: Candidate pool None
        try:
            result = legacy_selected_ids(candidates=None, doc_plan=doc_plan_ok, area_plans=area_plans_ok)
            assert result == [], f"expected [], got {result!r}"
        except Exception as exc:
            raise AssertionError(f"helper_raised:{type(exc).__name__}") from exc

        # Caso B: Altri candidate pool non-list
        assert legacy_selected_ids(candidates=123, doc_plan=doc_plan_ok, area_plans=area_plans_ok) == []
        assert legacy_selected_ids(candidates="bad", doc_plan=doc_plan_ok, area_plans=area_plans_ok) == []
        assert legacy_selected_ids(candidates={"candidate_id": "not-a-list"}, doc_plan=doc_plan_ok, area_plans=area_plans_ok) == []

        # Caso C: Lista parzialmente malformata con un candidato valido
        partial_pool = [
            None,
            123,
            "bad",
            {},
            {
                "candidate_id": "root_doc:README.md",
                "path": "README.md",
                "kind": "file",
                "candidate_class": "root_doc",
                "static_rank": 0,
                "signals": [],
            },
        ]
        result = legacy_selected_ids(
            candidates=partial_pool,
            doc_plan={"arguments": {"paths": ["README.md"]}},
            area_plans=[],
        )
        assert result == ["root_doc:README.md"], \
            f"should extract valid candidate from malformed pool, got {result!r}"

        return {}

    cases.append(_case("legacy_selection_handles_malformed_candidate_pool", case_legacy_selection_handles_malformed_candidate_pool))

    def case_legacy_selection_distinguishes_doc_and_area_same_path() -> dict[str, Any]:
        legacy_selected_ids = _required_callable(module, "orientation_legacy_selected_candidate_ids")

        # Candidate pool con stesso path ma classi diverse
        same_path_pool = [
            {
                "candidate_id": "root_area:shared",
                "path": "shared",
                "kind": "dir",
                "candidate_class": "root_area",
                "static_rank": 0,
                "signals": [],
            },
            {
                "candidate_id": "root_doc:shared",
                "path": "shared",
                "kind": "file",
                "candidate_class": "root_doc",
                "static_rank": 1,
                "signals": [],
            },
        ]

        # Document plan prima
        doc_plan_shared = {
            "arguments": {
                "paths": ["shared"],
            },
        }

        # Area plans dopo
        area_plans_shared = [
            {
                "arguments": {
                    "path": "shared",
                },
            },
        ]

        result = legacy_selected_ids(
            candidates=same_path_pool,
            doc_plan=doc_plan_shared,
            area_plans=area_plans_shared,
        )

        # La classe deriva dalla sezione del plan
        # Ordine: documenti prima delle aree
        expected = ["root_doc:shared", "root_area:shared"]
        assert result == expected, \
            f"document then area order should prevail, got {result!r}"

        return {}

    cases.append(_case("legacy_selection_distinguishes_doc_and_area_same_path", case_legacy_selection_distinguishes_doc_and_area_same_path))

    def case_selection_metrics_exact_match() -> dict[str, Any]:
        selection_metrics = _required_callable(module, "orientation_shadow_selection_metrics")
        legacy = ["A", "B"]
        model = ["A", "B"]
        result = selection_metrics(legacy_selected_candidate_ids=legacy, model_selected_candidate_ids=model)
        assert result["legacy_count"] == 2
        assert result["model_count"] == 2
        assert result["selection_overlap"] == ["A", "B"]
        assert result["selection_overlap_count"] == 2
        assert result["top1_match"] is True
        assert result["exact_match"] is True
        assert result["would_change_selection"] is False
        return {}

    cases.append(_case("selection_metrics_exact_match", case_selection_metrics_exact_match))

    def case_selection_metrics_partial_overlap() -> dict[str, Any]:
        selection_metrics = _required_callable(module, "orientation_shadow_selection_metrics")
        legacy = ["A", "B", "C"]
        model = ["B", "D", "A"]
        result = selection_metrics(legacy_selected_candidate_ids=legacy, model_selected_candidate_ids=model)
        assert result["legacy_count"] == 3
        assert result["model_count"] == 3
        assert result["selection_overlap"] == ["A", "B"]
        assert result["selection_overlap_count"] == 2
        assert result["top1_match"] is False
        assert result["exact_match"] is False
        assert result["would_change_selection"] is True
        return {}

    cases.append(_case("selection_metrics_partial_overlap", case_selection_metrics_partial_overlap))

    def case_selection_metrics_empty_model_selection() -> dict[str, Any]:
        selection_metrics = _required_callable(module, "orientation_shadow_selection_metrics")
        legacy = ["A"]
        model = []
        result = selection_metrics(legacy_selected_candidate_ids=legacy, model_selected_candidate_ids=model)
        assert result["legacy_count"] == 1
        assert result["model_count"] == 0
        assert result["selection_overlap"] == []
        assert result["selection_overlap_count"] == 0
        assert result["top1_match"] is False
        assert result["exact_match"] is False
        assert result["would_change_selection"] is True
        return {}

    cases.append(_case("selection_metrics_empty_model_selection", case_selection_metrics_empty_model_selection))

    def case_selection_metrics_bounds_and_input_immutability() -> dict[str, Any]:
        selection_metrics = _required_callable(module, "orientation_shadow_selection_metrics")
        # Costruisci almeno 15 ID validi distinti per lato
        legacy_valid = [f"id:{index}" for index in range(15)]
        model_valid = [f"id:{index}" for index in range(5, 20)]

        # Aggiungi duplicati, vuoti, whitespace, None, integer, oversized
        legacy_with_invalid = legacy_valid + ["id:0", "", "   ", None, 123, "id:" * 501]
        model_with_invalid = model_valid + ["id:5", "", "   ", None, {}, "id:" * 501]

        legacy_before = deepcopy(legacy_with_invalid)
        model_before = deepcopy(model_with_invalid)

        result1 = selection_metrics(legacy_selected_candidate_ids=legacy_with_invalid, model_selected_candidate_ids=model_with_invalid)
        result2 = selection_metrics(legacy_selected_candidate_ids=legacy_with_invalid, model_selected_candidate_ids=model_with_invalid)

        assert result1 == result2, "results should be identical for same inputs"
        assert legacy_with_invalid == legacy_before, "legacy input should be unchanged"
        assert model_with_invalid == model_before, "model input should be unchanged"
        assert result1["legacy_count"] == 13, f"expected 13, got {result1['legacy_count']}"
        assert result1["model_count"] == 13, f"expected 13, got {result1['model_count']}"
        expected_overlap = ["id:5", "id:6", "id:7", "id:8", "id:9", "id:10", "id:11", "id:12"]
        assert result1["selection_overlap"] == expected_overlap, f"expected {expected_overlap!r}, got {result1['selection_overlap']!r}"
        assert result1["selection_overlap_count"] == 8
        assert result1["top1_match"] is False
        assert result1["exact_match"] is False
        assert result1["would_change_selection"] is True
        assert all(len(id_) <= 500 for id_ in result1.get("selection_overlap", []))
        return {}

    cases.append(_case("selection_metrics_bounds_and_input_immutability", case_selection_metrics_bounds_and_input_immutability))

    passed = sum(1 for item in cases if item.get("ok") is True)
    failed = len(cases) - passed
    return {
        "ok": failed == 0,
        "engine": "deterministic",
        "case_count": len(cases),
        "passed": passed,
        "failed": failed,
        "cases": cases,
    }


def _deterministic_orientation_shadow_evaluator_profile() -> dict[str, Any]:
    """Deterministic profile per initial orientation shadow evaluator.

    Profile only prepares input and mock → calls the callable runtime → observes and asserts output.

    The profile MUST NOT:
    - create results if the callable is missing;
    - correct output;
    - apply bounds;
    - perform redaction;
    - remove forbidden keys;
    - convert exceptions to fallbacks;
    - implement semantics of the evaluator.
    """
    module = importlib.import_module(
        "aicarmine_broker.application.planner.loop"
    )
    orientation_module = importlib.import_module(
        "aicarmine_broker.application.controller.orientation_lane"
    )

    effective_mode = _required_callable(
        orientation_module,
        "orientation_shadow_effective_mode",
    )
    legacy_selected_ids = _required_callable(
        orientation_module,
        "orientation_legacy_selected_candidate_ids",
    )
    selection_metrics = _required_callable(
        orientation_module,
        "orientation_shadow_selection_metrics",
    )

    cases: list[dict[str, Any]] = []

    def invoke(
        evaluator: Callable[..., dict[str, Any]],
        
        requested_mode: object,
        root_result: object,
        semantic_intent: object,
        doc_plan: object,
        area_plans: object,
        candidate_pool_fn: Callable[..., Any],
        selector_fn: Callable[..., Any],
        effective_mode_fn: Callable[[object], str] = effective_mode,
        legacy_selected_ids_fn: Callable[..., list[str]] = legacy_selected_ids,
        selection_metrics_fn: Callable[..., dict[str, Any]] = selection_metrics,
    ) -> dict[str, Any]:
        return evaluator(
            requested_mode=requested_mode,
            root_result=root_result,
            goal="Inspect the repository",
            semantic_intent=semantic_intent,
            doc_plan=doc_plan,
            area_plans=area_plans,
            candidate_pool_fn=candidate_pool_fn,
            selector_fn=selector_fn,
            effective_mode_fn=effective_mode_fn,
            legacy_selected_ids_fn=legacy_selected_ids_fn,
            selection_metrics_fn=selection_metrics_fn,
        )

    expected_legacy_ids = [
        "root_doc:README.md",
        "root_doc:AGENTS.md",
        "root_area:services",
        "root_area:docs",
    ]

    fixture_pool = [
        {
            "candidate_id": "root_doc:AGENTS.md",
            "path": "AGENTS.md",
            "kind": "file",
            "candidate_class": "root_doc",
            "static_rank": 0,
            "signals": ["doc_or_config"],
        },
        {
            "candidate_id": "root_doc:README.md",
            "path": "README.md",
            "kind": "file",
            "candidate_class": "root_doc",
            "static_rank": 1,
            "signals": ["doc_or_config"],
        },
        {
            "candidate_id": "root_doc:pyproject.toml",
            "path": "pyproject.toml",
            "kind": "file",
            "candidate_class": "root_doc",
            "static_rank": 2,
            "signals": ["config"],
        },
        {
            "candidate_id": "root_area:services",
            "path": "services",
            "kind": "dir",
            "candidate_class": "root_area",
            "static_rank": 3,
            "signals": ["non_low_signal"],
        },
        {
            "candidate_id": "root_area:docs",
            "path": "docs",
            "kind": "dir",
            "candidate_class": "root_area",
            "static_rank": 4,
            "signals": [],
        },
        {
            "candidate_id": "root_area:scripts",
            "path": "scripts",
            "kind": "dir",
            "candidate_class": "root_area",
            "static_rank": 5,
            "signals": [],
        },
    ]

    doc_plan_ok = {
        "arguments": {
            "paths": ["README.md", "AGENTS.md"],
        },
    }
    area_plans_ok = [
        {
            "arguments": {
                "path": "services",
            },
        },
        {
            "arguments": {
                "path": "docs",
            },
        },
    ]

    selector_ready_fixture = {
        "ok": True,
        "status": "ready",
        "selected_candidate_ids": [
            "root_doc:README.md",
            "root_area:services",
        ],
        "unknown_candidate_ids": [],
        "duplicate_candidate_ids": [],
        "duplicate_input_candidate_ids": [],
        "rationale": "bounded test rationale",
        "confidence": 0.75,
        "planner_model": "test-model",
        "planner_url": "http://127.0.0.1:11434/api/chat",
        "timeout_seconds": 30,
        "keep_alive": "5m",
    }

    def ready_selector(**_kwargs: Any) -> dict[str, Any]:
        return deepcopy(selector_ready_fixture)

    def _raise_assertion_error(message: str) -> NoReturn:
        raise AssertionError(message)

    def _raise_runtime_error(message: str) -> NoReturn:
        raise RuntimeError(message)

    def _raise_value_error(message: str) -> NoReturn:
        raise ValueError(message)

    def _raise_connection_error(message: str) -> NoReturn:
        raise ConnectionError(message)

    def case_legacy_mode_skips_shadow_callbacks() -> dict[str, Any]:
        evaluator = _required_callable(
            module,
            "evaluate_initial_orientation_shadow",
        )

        mock_candidates = lambda x: (_raise_assertion_error("candidate_pool_called"))
        mock_selector = lambda **kw: (_raise_assertion_error("selector_called"))

        result = invoke(
            evaluator=evaluator,
            requested_mode="legacy",
            root_result={"ok": True},
            semantic_intent={"target_kind": "repository"},
            doc_plan=doc_plan_ok,
            area_plans=area_plans_ok,
            candidate_pool_fn=mock_candidates,
            selector_fn=mock_selector,
        )

        assert result["status"] == "skipped", f"expected skipped, got {result['status']}"
        assert result["reason"] == "mode_not_shadow", f"expected mode_not_shadow, got {result['reason']}"
        assert result["effective_mode"] == "legacy", f"expected legacy, got {result['effective_mode']}"
        assert result["selector_called"] is False, f"expected False, got {result['selector_called']}"
        assert result["fallback_used"] is False, f"expected False, got {result['fallback_used']}"
        assert result["candidate_count"] == 0, f"expected 0, got {result['candidate_count']}"

        return {}
    cases.append(_case("legacy_mode_skips_shadow_callbacks", case_legacy_mode_skips_shadow_callbacks))

    def case_active_mode_fails_closed_to_legacy() -> dict[str, Any]:
        evaluator = _required_callable(
            module,
            "evaluate_initial_orientation_shadow",
        )

        mock_candidates = lambda x: (_raise_assertion_error("candidate_pool_called"))
        mock_selector = lambda **kw: (_raise_assertion_error("selector_called"))

        result = invoke(
            evaluator=evaluator,
            requested_mode=" ACTIVE ",
            root_result={"ok": True},
            semantic_intent={"target_kind": "repository"},
            doc_plan=doc_plan_ok,
            area_plans=area_plans_ok,
            candidate_pool_fn=mock_candidates,
            selector_fn=mock_selector,
        )

        assert result["effective_mode"] == "legacy", f"expected legacy, got {result['effective_mode']}"
        assert result["status"] == "skipped", f"expected skipped, got {result['status']}"
        assert result["reason"] == "mode_not_shadow", f"expected mode_not_shadow, got {result['reason']}"
        assert result["selector_called"] is False, f"expected False, got {result['selector_called']}"

        return {}
    cases.append(_case("active_mode_fails_closed_to_legacy", case_active_mode_fails_closed_to_legacy))

    def case_root_result_must_be_ok() -> dict[str, Any]:
        evaluator = _required_callable(
            module,
            "evaluate_initial_orientation_shadow",
        )

        def forbidden_candidate_pool(_root_result: object) -> list[dict[str, Any]]:
            raise AssertionError("candidate_pool_called")

        def forbidden_selector(**_kwargs: Any) -> dict[str, Any]:
            raise AssertionError("selector_called")

        def forbidden_legacy(**_kwargs: Any) -> list[str]:
            raise AssertionError("legacy_selection_called")

        def forbidden_metrics(**_kwargs: Any) -> dict[str, Any]:
            raise AssertionError("selection_metrics_called")

        scenarios = [
            None,
            {},
            {"ok": False},
            "bad",
        ]

        for scenario in scenarios:
            result = invoke(
                evaluator=evaluator,
                requested_mode="shadow",
                root_result=scenario,
                semantic_intent={"target_kind": "repository"},
                doc_plan=doc_plan_ok,
                area_plans=area_plans_ok,
                candidate_pool_fn=forbidden_candidate_pool,
                selector_fn=forbidden_selector,
                legacy_selected_ids_fn=forbidden_legacy,
                selection_metrics_fn=forbidden_metrics,
            )
            assert result["effective_mode"] == "shadow", f"expected shadow, got {result['effective_mode']}"
            assert result["status"] == "skipped", f"expected skipped, got {result['status']}"
            assert result["reason"] == "root_result_not_ok", f"expected root_result_not_ok, got {result['reason']}"
            assert result["selector_called"] is False, f"expected False, got {result['selector_called']}"
            assert result["fallback_used"] is False, f"expected False, got {result['fallback_used']}"

        return {}
    cases.append(_case("root_result_must_be_ok", case_root_result_must_be_ok))

    def case_empty_candidate_pool_skips_selector() -> dict[str, Any]:
        evaluator = _required_callable(
            module,
            "evaluate_initial_orientation_shadow",
        )

        counters = {"candidate_pool": 0, "selector": 0}

        def empty_pool(root_result: object) -> list[dict[str, Any]]:
            counters["candidate_pool"] += 1
            assert root_result == {"ok": True}
            return []

        def forbidden_selector(**_kwargs: Any) -> dict[str, Any]:
            counters["selector"] += 1
            raise AssertionError("selector_called")

        result = invoke(
            evaluator=evaluator,
            requested_mode="shadow",
            root_result={"ok": True},
            semantic_intent={"target_kind": "repository"},
            doc_plan=doc_plan_ok,
            area_plans=area_plans_ok,
            candidate_pool_fn=empty_pool,
            selector_fn=forbidden_selector,
        )

        assert result["status"] == "skipped", f"expected skipped, got {result['status']}"
        assert result["reason"] == "no_candidates", f"expected no_candidates, got {result['reason']}"
        assert result["candidate_count"] == 0, f"expected 0, got {result['candidate_count']}"
        assert result["candidate_ids"] == [], f"expected [], got {result['candidate_ids']}"
        assert result["selector_called"] is False, f"expected False, got {result['selector_called']}"
        assert result["fallback_used"] is False, f"expected False, got {result['fallback_used']}"
        assert counters["candidate_pool"] == 1, f"expected 1, got {counters['candidate_pool']}"
        assert counters["selector"] == 0, f"expected 0, got {counters['selector']}"

        return {}
    cases.append(_case("empty_candidate_pool_skips_selector", case_empty_candidate_pool_skips_selector))

    def case_successful_evaluation_calls_each_stage_once() -> dict[str, Any]:
        evaluator = _required_callable(
            module,
            "evaluate_initial_orientation_shadow",
        )

        stage_counts = {"effective_mode_fn": 0, "candidate_pool_fn": 0, "legacy_selected_ids_fn": 0,
                        "selector_fn": 0, "selection_metrics_fn": 0}

        def counting_effective_mode(mode):
            stage_counts["effective_mode_fn"] += 1
            return effective_mode(mode)

        def counting_candidate_pool(root_result: object) -> list[dict[str, Any]]:
            stage_counts["candidate_pool_fn"] += 1
            assert root_result == {"ok": True}
            return deepcopy(fixture_pool)

        def counting_selector(**kwargs):
            stage_counts["selector_fn"] += 1
            return deepcopy(selector_ready_fixture)

        def counting_legacy_selected_ids(**kwargs):
            stage_counts["legacy_selected_ids_fn"] += 1
            return deepcopy(legacy_selected_ids(**kwargs))

        def counting_selection_metrics(**kwargs):
            stage_counts["selection_metrics_fn"] += 1
            return deepcopy(selection_metrics(**kwargs))

        result = invoke(
            evaluator=evaluator,
            requested_mode="shadow",
            root_result={"ok": True},
            semantic_intent={"target_kind": "repository"},
            doc_plan=doc_plan_ok,
            area_plans=area_plans_ok,
            candidate_pool_fn=counting_candidate_pool,
            selector_fn=counting_selector,
            effective_mode_fn=counting_effective_mode,
            legacy_selected_ids_fn=counting_legacy_selected_ids,
            selection_metrics_fn=counting_selection_metrics,
        )

        assert stage_counts["effective_mode_fn"] == 1, f"expected 1 call, got {stage_counts['effective_mode_fn']}"
        assert stage_counts["candidate_pool_fn"] == 1, f"expected 1 call, got {stage_counts['candidate_pool_fn']}"
        assert stage_counts["legacy_selected_ids_fn"] == 1, f"expected 1 call, got {stage_counts['legacy_selected_ids_fn']}"
        assert stage_counts["selector_fn"] == 1, f"expected 1 call, got {stage_counts['selector_fn']}"
        assert stage_counts["selection_metrics_fn"] == 1, f"expected 1 call, got {stage_counts['selection_metrics_fn']}"

        assert result["status"] == "ready", f"expected ready, got {result['status']}"
        assert result["reason"] == "selector_ready", f"expected selector_ready, got {result['reason']}"
        assert result["selector_called"] is True, f"expected True, got {result['selector_called']}"
        assert result["fallback_used"] is False, f"expected False, got {result['fallback_used']}"
        assert result["diagnostic_only"] is True, f"expected True, got {result['diagnostic_only']}"
        assert result["legacy_authoritative"] is True, f"expected True, got {result['legacy_authoritative']}"
        assert result["candidate_count"] == len(fixture_pool), f"expected {len(fixture_pool)}, got {result['candidate_count']}"

        assert result["legacy_selected_candidate_ids"] == expected_legacy_ids, \
            f"expected {expected_legacy_ids!r}, got {result['legacy_selected_candidate_ids']!r}"

        expected_model = ["root_doc:README.md", "root_area:services"]
        assert result["model_selected_candidate_ids"] == expected_model, \
            f"expected {expected_model!r}, got {result['model_selected_candidate_ids']!r}"

        return {}
    cases.append(_case("successful_evaluation_calls_each_stage_once", case_successful_evaluation_calls_each_stage_once))

    def case_legacy_plan_order_drives_comparison() -> dict[str, Any]:
        evaluator = _required_callable(
            module,
            "evaluate_initial_orientation_shadow",
        )

        order_pool_different = [
            {
                "candidate_id": "root_area:docs",
                "path": "docs",
                "kind": "dir",
                "candidate_class": "root_area",
                "static_rank": 0,
                "signals": [],
            },
            {
                "candidate_id": "root_doc:AGENTS.md",
                "path": "AGENTS.md",
                "kind": "file",
                "candidate_class": "root_doc",
                "static_rank": 1,
                "signals": ["doc_or_config"],
            },
            {
                "candidate_id": "root_area:services",
                "path": "services",
                "kind": "dir",
                "candidate_class": "root_area",
                "static_rank": 2,
                "signals": ["non_low_signal"],
            },
            {
                "candidate_id": "root_doc:README.md",
                "path": "README.md",
                "kind": "file",
                "candidate_class": "root_doc",
                "static_rank": 3,
                "signals": ["doc_or_config"],
            },
        ]

        selector_mock_ready = {
            "ok": True,
            "status": "ready",
            "selected_candidate_ids": ["root_area:services", "root_doc:README.md"],
            "unknown_candidate_ids": [],
            "duplicate_candidate_ids": [],
            "duplicate_input_candidate_ids": [],
            "rationale": "bounded test rationale",
            "confidence": 0.75,
            "planner_model": "test-model",
            "planner_url": "http://127.0.0.1:11434/api/chat",
            "timeout_seconds": 30,
            "keep_alive": "5m",
        }

        pool = deepcopy(order_pool_different)
        doc_plan = deepcopy(doc_plan_ok)
        area_plans = deepcopy(area_plans_ok)

        pool_before = deepcopy(pool)
        doc_plan_before = deepcopy(doc_plan)
        area_plans_before = deepcopy(area_plans)

        def order_candidate_pool(root_result: object) -> list[dict[str, Any]]:
            assert root_result == {"ok": True}
            return deepcopy(pool)

        def order_selector(**_kwargs: Any) -> dict[str, Any]:
            return deepcopy(selector_mock_ready)

        result = invoke(
            evaluator=evaluator,
            requested_mode="shadow",
            root_result={"ok": True},
            semantic_intent={"target_kind": "repository"},
            doc_plan=doc_plan,
            area_plans=area_plans,
            candidate_pool_fn=order_candidate_pool,
            selector_fn=order_selector,
        )

        assert result["legacy_selected_candidate_ids"] == expected_legacy_ids, \
            f"plan order should drive comparison, got {result['legacy_selected_candidate_ids']!r}"

        overlap = ["root_doc:README.md", "root_area:services"]
        assert result["selection_metrics"]["selection_overlap"] == overlap, \
            f"expected {overlap!r}, got {result['selection_metrics']['selection_overlap']!r}"

        assert pool == pool_before, "pool should be unchanged"
        assert doc_plan == doc_plan_before, "doc_plan should be unchanged"
        assert area_plans == area_plans_before, "area_plans should be unchanged"

        return {}
    cases.append(_case("legacy_plan_order_drives_comparison", case_legacy_plan_order_drives_comparison))

    def case_candidate_pool_failure_fails_open() -> dict[str, Any]:
        evaluator = _required_callable(
            module,
            "evaluate_initial_orientation_shadow",
        )

        failing_pool = lambda x: (_raise_runtime_error("candidate boom"))

        result = invoke(
            evaluator=evaluator,
            requested_mode="shadow",
            root_result={"ok": True},
            semantic_intent={"target_kind": "repository"},
            doc_plan=doc_plan_ok,
            area_plans=area_plans_ok,
            candidate_pool_fn=failing_pool,
            selector_fn=ready_selector,
        )

        assert result["status"] == "unavailable", f"expected unavailable, got {result['status']}"
        assert result["reason"] == "candidate_pool_exception", f"expected candidate_pool_exception, got {result['reason']}"
        assert result["selector_called"] is False, f"expected False, got {result['selector_called']}"
        assert result["fallback_used"] is True, f"expected True, got {result['fallback_used']}"
        assert result["candidate_count"] == 0, f"expected 0, got {result['candidate_count']}"
        assert result["model_selected_candidate_ids"] == [], f"expected [], got {result['model_selected_candidate_ids']}"
        assert result["model_summary"]["error_type"] == "RuntimeError", \
            f"expected RuntimeError, got {result['model_summary']['error_type']}"

        return {}
    cases.append(_case("candidate_pool_failure_fails_open", case_candidate_pool_failure_fails_open))

    def case_legacy_selection_failure_fails_open() -> dict[str, Any]:
        evaluator = _required_callable(
            module,
            "evaluate_initial_orientation_shadow",
        )

        valid_pool = lambda x: fixture_pool

        def failing_legacy(**kwargs):
            _raise_value_error("legacy boom")

        result = invoke(
            evaluator=evaluator,
            requested_mode="shadow",
            root_result={"ok": True},
            semantic_intent={"target_kind": "repository"},
            doc_plan=doc_plan_ok,
            area_plans=area_plans_ok,
            candidate_pool_fn=valid_pool,
            selector_fn=ready_selector,
            legacy_selected_ids_fn=failing_legacy,
        )

        assert result["status"] == "unavailable", f"expected unavailable, got {result['status']}"
        assert result["reason"] == "legacy_selection_exception", f"expected legacy_selection_exception, got {result['reason']}"
        assert result["selector_called"] is False, f"expected False, got {result['selector_called']}"
        assert result["fallback_used"] is True, f"expected True, got {result['fallback_used']}"
        assert result["model_summary"]["error_type"] == "ValueError", \
            f"expected ValueError, got {result['model_summary']['error_type']}"

        return {}
    cases.append(_case("legacy_selection_failure_fails_open", case_legacy_selection_failure_fails_open))

    def case_selector_failure_fails_open() -> dict[str, Any]:
        evaluator = _required_callable(
            module,
            "evaluate_initial_orientation_shadow",
        )

        valid_pool = lambda x: fixture_pool
        valid_legacy = legacy_selected_ids

        def failing_selector(**kwargs):
            _raise_connection_error("selector boom")

        result = invoke(
            evaluator=evaluator,
            requested_mode="shadow",
            root_result={"ok": True},
            semantic_intent={"target_kind": "repository"},
            doc_plan=doc_plan_ok,
            area_plans=area_plans_ok,
            candidate_pool_fn=valid_pool,
            selector_fn=failing_selector,
        )

        assert result["status"] == "unavailable", f"expected unavailable, got {result['status']}"
        assert result["reason"] == "selector_exception", f"expected selector_exception, got {result['reason']}"
        assert result["selector_called"] is True, f"expected True, got {result['selector_called']}"
        assert result["fallback_used"] is True, f"expected True, got {result['fallback_used']}"
        assert result["model_selected_candidate_ids"] == [], f"expected [], got {result['model_selected_candidate_ids']}"
        assert result["model_summary"]["error_type"] == "ConnectionError", \
            f"expected ConnectionError, got {result['model_summary']['error_type']}"

        return {}
    cases.append(_case("selector_failure_fails_open", case_selector_failure_fails_open))

    def case_selector_not_ready_fails_open() -> dict[str, Any]:
        evaluator = _required_callable(
            module,
            "evaluate_initial_orientation_shadow",
        )

        valid_pool = lambda x: fixture_pool
        valid_legacy = legacy_selected_ids

        # Scenario A: selector returns "not-a-dict"
        def bad_selector_a(**kwargs):
            return "not-a-dict"

        result_a = invoke(
            evaluator=evaluator,
            requested_mode="shadow",
            root_result={"ok": True},
            semantic_intent={"target_kind": "repository"},
            doc_plan=doc_plan_ok,
            area_plans=area_plans_ok,
            candidate_pool_fn=valid_pool,
            selector_fn=bad_selector_a,
        )

        assert result_a["status"] == "invalid", f"expected invalid, got {result_a['status']}"
        assert result_a["reason"] == "selector_result_not_dict", f"expected selector_result_not_dict, got {result_a['reason']}"
        assert result_a["selector_called"] is True, f"expected True, got {result_a['selector_called']}"
        assert result_a["fallback_used"] is True, f"expected True, got {result_a['fallback_used']}"

        # Scenario B: selector returns unavailable dict
        def bad_selector_b(**kwargs):
            return {
                "ok": False,
                "status": "unavailable",
                "selected_candidate_ids": [],
                "rationale": "backend_unavailable",
            }

        result_b = invoke(
            evaluator=evaluator,
            requested_mode="shadow",
            root_result={"ok": True},
            semantic_intent={"target_kind": "repository"},
            doc_plan=doc_plan_ok,
            area_plans=area_plans_ok,
            candidate_pool_fn=valid_pool,
            selector_fn=bad_selector_b,
        )

        assert result_b["status"] == "unavailable", f"expected unavailable, got {result_b['status']}"
        assert result_b["reason"] == "backend_unavailable", f"expected backend_unavailable, got {result_b['reason']}"
        assert result_b["selector_called"] is True, f"expected True, got {result_b['selector_called']}"
        assert result_b["fallback_used"] is True, f"expected True, got {result_b['fallback_used']}"

        return {}
    cases.append(_case("selector_not_ready_fails_open", case_selector_not_ready_fails_open))

    def case_evaluation_output_is_bounded() -> dict[str, Any]:
        evaluator = _required_callable(
            module,
            "evaluate_initial_orientation_shadow",
        )

        bounded_pool = [
            {"candidate_id": f"id:{i}", "path": f"path{i}.md", "kind": "file",
             "candidate_class": "root_doc", "static_rank": i % 2, "signals": []}
            for i in range(45)
        ] + [{"candidate_id": "", "path": "", "kind": "", "candidate_class": None,
              "static_rank": -1, "signals": []}] * 3

        bounded_pool_with_oversized = bounded_pool + [
            {"candidate_id": "x" * 501, "path": "oversized", "kind": "file",
             "candidate_class": "root_doc", "static_rank": 0, "signals": []},
        ]

        oversized_selector_result = {
            "selected_candidate_ids": ["id:" + str(i) for i in range(20)] +
                                       ["unknown:" + str(i) for i in range(20)] +
                                       ["duplicate:" + str(i) for i in range(20)] +
                                       ["duplicate_input:" + str(i) for i in range(20)],
            "unknown_candidate_ids": ["unknown:" + str(i) for i in range(20)],
            "duplicate_candidate_ids": ["duplicate:" + str(i) for i in range(20)],
            "duplicate_input_candidate_ids": ["duplicate_input:" + str(i) for i in range(20)],
            "rationale": "x" * 1001,
            "error_type": "y" * 121,
            "error": "z" * 501,
            "diagnostics": [f"diag:{i}" for i in range(20)],
            "errors": [f"err:{i}" for i in range(20)],
            "warnings": [f"warn:{i}" for i in range(20)],
            "raw_response": "ignored",
            "message": "ignored",
            "messages": "ignored",
            "response": "ignored",
            "request_body": "ignored",
            "tools": "ignored",
        }

        result = invoke(
            evaluator=evaluator,
            requested_mode="shadow",
            root_result={"ok": True},
            semantic_intent={"target_kind": "repository"},
            doc_plan=doc_plan_ok,
            area_plans=area_plans_ok,
            candidate_pool_fn=lambda x: deepcopy(bounded_pool_with_oversized),
            selector_fn=lambda **kw: deepcopy(oversized_selector_result),
        )

        assert result["candidate_count"] == 45, \
            f"expected 45, got {result['candidate_count']}"
        assert len(result["candidate_ids"]) == 32, f"expected 32, got {len(result['candidate_ids'])}"
        assert len(result["candidate_ids"]) == len(set(result["candidate_ids"])), \
            "candidate_ids should be deduplicated"
        assert all(
            isinstance(candidate_id, str) and len(candidate_id) <= 500
            for candidate_id in result["candidate_ids"]
        ), "all candidate IDs should be strings <= 500 chars"
        assert len(result.get("model_selected_candidate_ids", [])) <= 13, \
            f"model IDs should be <= 13, got {len(result.get('model_selected_candidate_ids', []))}"

        forbidden_top_level_keys = {
            "state",
            "history",
            "evidence_contract",
            "required_next_tool_call",
            "tool",
            "arguments",
            "plan",
            "area_read_plan",
            "dispatch",
            "lifecycle_status",
            "raw_response",
            "message",
            "messages",
            "response",
            "request_body",
            "tools",
        }

        forbidden_model_summary_keys = {
            "raw_response",
            "message",
            "messages",
            "response",
            "request_body",
            "tools",
        }

        model_summary = result.get("model_summary", {})
        assert isinstance(model_summary, dict), "model_summary should be a dict"

        for key in forbidden_top_level_keys:
            assert key not in result, f"forbidden top-level key {key!r} found in result"

        for key in forbidden_model_summary_keys:
            assert key not in model_summary, f"forbidden model_summary key {key!r} found"

        diagnostic_id_fields = [
            "unknown_candidate_ids",
            "duplicate_candidate_ids",
            "duplicate_input_candidate_ids",
        ]

        for field_name in diagnostic_id_fields:
            values = model_summary.get(field_name, [])
            assert isinstance(values, list), f"{field_name} should be a list"
            assert len(values) <= 13, f"{field_name} should have <= 13 elements"
            assert len(values) == len(set(values)), f"{field_name} should be deduplicated"
            assert all(
                isinstance(value, str)
                and bool(value.strip())
                and len(value.strip()) <= 500
                for value in values
            ), f"{field_name} elements should be non-empty strings <= 500 chars"

        assert len(model_summary.get("rationale", "")) <= 1000, \
            f"rationale should be <= 1000, got {len(model_summary.get('rationale', ''))}"
        assert len(model_summary.get("error_type", "")) <= 120, \
            f"error_type should be <= 120, got {len(model_summary.get('error_type', ''))}"
        assert len(model_summary.get("error", "")) <= 500, \
            f"error should be <= 500, got {len(model_summary.get('error', ''))}"

        return {}
    cases.append(_case("evaluation_output_is_bounded", case_evaluation_output_is_bounded))

    def case_evaluation_is_deterministic_and_input_immutable() -> dict[str, Any]:
        evaluator = _required_callable(
            module,
            "evaluate_initial_orientation_shadow",
        )

        immutable_root_result = {"ok": True, "data": "test"}
        immutable_semantic_intent = {"target_kind": "repository", "query": "test query"}
        immutable_doc_plan = {"arguments": {"paths": ["README.md", "AGENTS.md"]}}
        immutable_area_plans = [{"arguments": {"path": "services"}}]
        immutable_candidates = deepcopy(fixture_pool)
        immutable_selector_fixture = deepcopy(selector_ready_fixture)

        root_before = deepcopy(immutable_root_result)
        intent_before = deepcopy(immutable_semantic_intent)
        doc_before = deepcopy(immutable_doc_plan)
        areas_before = deepcopy(immutable_area_plans)
        candidates_before = deepcopy(immutable_candidates)
        selector_before = deepcopy(immutable_selector_fixture)

        def immutable_candidate_pool(root_result: object) -> list[dict[str, Any]]:
            assert root_result == immutable_root_result
            return deepcopy(immutable_candidates)

        def immutable_selector(**_kwargs: Any) -> dict[str, Any]:
            return deepcopy(immutable_selector_fixture)

        result1 = invoke(
            evaluator=evaluator,
            requested_mode="shadow",
            root_result=immutable_root_result,
            semantic_intent=immutable_semantic_intent,
            doc_plan=immutable_doc_plan,
            area_plans=immutable_area_plans,
            candidate_pool_fn=immutable_candidate_pool,
            selector_fn=immutable_selector,
        )

        result2 = invoke(
            evaluator=evaluator,
            requested_mode="shadow",
            root_result=immutable_root_result,
            semantic_intent=immutable_semantic_intent,
            doc_plan=immutable_doc_plan,
            area_plans=immutable_area_plans,
            candidate_pool_fn=immutable_candidate_pool,
            selector_fn=immutable_selector,
        )

        assert result1 == result2, "results should be identical for same inputs"
        assert immutable_root_result == root_before, "root_result should be unchanged"
        assert immutable_semantic_intent == intent_before, "semantic_intent should be unchanged"
        assert immutable_doc_plan == doc_before, "doc_plan should be unchanged"
        assert immutable_area_plans == areas_before, "area_plans should be unchanged"
        assert immutable_candidates == candidates_before, "candidates should be unchanged"
        assert immutable_selector_fixture == selector_before, "selector_fixture should be unchanged"

        try:
            json.dumps(result1)
        except Exception as exc:
            raise AssertionError(f"result1 should be JSON-serializable") from exc

        return {}
    cases.append(_case("evaluation_is_deterministic_and_input_immutable", case_evaluation_is_deterministic_and_input_immutable))

    passed = sum(1 for item in cases if item.get("ok") is True)
    failed = len(cases) - passed
    return {
        "ok": failed == 0,
        "engine": "deterministic",
        "case_count": len(cases),
        "passed": passed,
        "failed": failed,
        "cases": cases,
    }


def repo_probe_run(args: dict[str, Any], root: Path) -> dict[str, Any]:
    profile_id = str(
        args.get("profile_id") or PROFILE_ORIENTATION_SELECTOR
    ).strip()
    engine = str(args.get("engine") or "deterministic").strip().lower()
    max_examples = _bounded_int(
        args,
        "max_examples",
        default=200,
        minimum=1,
        maximum=1000,
    )
    seed_value = _bounded_int(
        args,
        "seed",
        default=42,
        minimum=0,
        maximum=2_147_483_647,
    )

    known_ids = {
        str(item["profile_id"])
        for item in _PROFILE_SPECS
    }
    if profile_id not in known_ids:
        return {
            "ok": False,
            "tool": "repo_probe_run",
            "error": "unknown_probe_profile",
            "profile_id": profile_id,
            "known_profile_ids": sorted(known_ids),
            "source_writes_performed": False,
            "network_calls_performed": False,
        }

    # Select profile spec by exact profile_id
    profile_spec = next(
        item for item in _PROFILE_SPECS
        if item["profile_id"] == profile_id
    )

    # Validate engine against profile spec
    allowed_engines = profile_spec.get("engines", ["deterministic"])
    if engine not in allowed_engines:
        return {
            "ok": False,
            "tool": "repo_probe_run",
            "error": "unsupported_profile_engine",
            "profile_id": profile_id,
            "requested_engine": engine,
            "allowed_engines": allowed_engines,
            "source_writes_performed": False,
            "network_calls_performed": False,
        }

    # Get target module from selected spec
    target_module = profile_spec["target_module"]

    origin = _module_origin_status(root, target_module)
    if origin.get("ok") is not True:
        return {
            "ok": False,
            "tool": "repo_probe_run",
            "error": "probe_target_origin_invalid",
            "profile_id": profile_id,
            "target_module_origin": origin,
            "source_writes_performed": False,
            "network_calls_performed": False,
        }

    runs: list[dict[str, Any]] = []

    # Dispatch exact routing
    if profile_id == PROFILE_ORIENTATION_SELECTOR:
        if engine in {"deterministic", "both"}:
            runs.append(_deterministic_orientation_profile())
    elif profile_id == PROFILE_ORIENTATION_SHADOW_HELPERS:
        runs.append(_deterministic_orientation_shadow_helpers_profile())
    elif profile_id == PROFILE_ORIENTATION_SHADOW_EVALUATOR:
        runs.append(_deterministic_orientation_shadow_evaluator_profile())

    if (
        profile_id == PROFILE_ORIENTATION_SELECTOR
        and engine in {"hypothesis", "both"}
    ):
        runs.append(
            _hypothesis_orientation_profile(
                max_examples=max_examples,
                seed_value=seed_value,
            )
        )

    ok_value = bool(runs) and all(
        item.get("ok") is True
        for item in runs
    )
    return {
        "ok": ok_value,
        "tool": "repo_probe_run",
        "profile_id": profile_id,
        "engine": engine,
        "repo_root": str(root),
        "python_executable": sys.executable,
        "target_module_origin": origin,
        "max_examples": max_examples,
        "seed": seed_value,
        "runs": runs,
        "source_writes_performed": False,
        "network_calls_performed": False,
        "subprocesses_started": False,
        "arbitrary_python_allowed": False,
    }