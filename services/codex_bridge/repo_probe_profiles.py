from __future__ import annotations

from copy import deepcopy
import importlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Callable

PROFILE_ORIENTATION_SELECTOR = "orientation.selector.contract.v1"

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
    *,
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
    *,
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
        planner_model="qwen3.5:9b-coding-v5-1",
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
        assert result.get("planner_model") == "qwen3.5:9b-coding-v5-1", result
        assert result.get("planner_url") == (
            "http://127.0.0.1:11434/api/chat"
        ), result
        assert result.get("timeout_seconds") == 37, result
        assert result.get("keep_alive") == "30m", result

        body = captured.get("body")
        assert isinstance(body, dict), captured
        assert body.get("model") == "qwen3.5:9b-coding-v5-1", body
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
        assert result.get("planner_model") == "qwen3.5:9b-coding-v5-1", (
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
        assert result.get("planner_model") == "qwen3.5:9b-coding-v5-1", (
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
                "model": "qwen3.5:9b-coding-v5-1",
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

        def capture_request(url, body, timeout):
            return {
                "model": "qwen3.5:9b-coding-v5-1",
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
        assert len(signals) == 3, f"Expected 3 signals, got {len(signals)}"
        assert signals[0] == "x", f"Expected 'x', got {signals[0]!r}"
        assert signals[1] == "aaa", f"Expected 'aaa', got {signals[1]!r}"
        assert signals[2] == "normal", f"Expected 'normal', got {signals[2]!r}"
        assert all(len(s) <= 80 for s in signals), signals
        assert not any(s == "" for s in signals), signals

        candidates_before = deepcopy(candidates)
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
    *,
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

    from hypothesis import HealthCheck, given, seed, settings
    from hypothesis import strategies as st

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
    if engine not in {"deterministic", "hypothesis", "both"}:
        return {
            "ok": False,
            "tool": "repo_probe_run",
            "error": "invalid_probe_engine",
            "engine": engine,
            "allowed_engines": [
                "deterministic",
                "hypothesis",
                "both",
            ],
            "source_writes_performed": False,
            "network_calls_performed": False,
        }

    target_module = str(_PROFILE_SPECS[0]["target_module"])
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
    if engine in {"deterministic", "both"}:
        runs.append(_deterministic_orientation_profile())
    if engine in {"hypothesis", "both"}:
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
