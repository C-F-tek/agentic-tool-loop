from __future__ import annotations

from pydantic import BaseModel

from vulkan_bridge.application.request_payload import (
    first_dict,
    first_text,
    payload_to_dict,
    public_agent_arguments,
)


def test_public_agent_arguments_filters_existing_allowed_keys() -> None:
    payload = {
        "request": "analyze",
        "path": "AGENTS.md",
        "job_id": "",
        "allow_command": False,
        "unknown": "x",
        "files": [],
    }

    assert public_agent_arguments(payload) == {
        "request": "analyze",
        "path": "AGENTS.md",
        "allow_command": False,
    }


def test_payload_to_dict_handles_dict_model_and_scalar() -> None:
    class DemoModel(BaseModel):
        request: str = ""
        empty: str = ""
        values: list[str] = []

    assert payload_to_dict(None) == {}
    assert payload_to_dict({"a": 1, "b": "", "c": []}) == {"a": 1}
    assert payload_to_dict(DemoModel(request="go")) == {"request": "go"}
    assert payload_to_dict("raw") == {"value": "raw"}


def test_first_text_and_first_dict_match_existing_semantics() -> None:
    payload = {
        "a": "  ",
        "b": " value ",
        "c": {"x": 1},
        "d": {},
    }

    assert first_text(payload, "a", "b") == "value"
    assert first_text(payload, "missing") == ""
    assert first_dict(payload, "d", "c") == {"x": 1}
    assert first_dict(payload, "missing") == {}


def test_app_facades_delegate_to_request_payload_helpers() -> None:
    from vulkan_bridge import app

    payload = {"request": "analyze", "unknown": "x", "parameters": {"a": 1}}

    assert app._public_agent_arguments(payload) == public_agent_arguments(payload)
    assert app._payload_to_dict(payload) == payload_to_dict(payload)
    assert app._first_text({"x": " y "}, "x") == "y"
    assert app._first_dict({"x": {"a": 1}}, "x") == {"a": 1}
