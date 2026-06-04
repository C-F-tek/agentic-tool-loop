from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_port_contract_contains_expected_runtime_ports() -> None:
    contract = _read_json("services/launch/contracts/ports_contract.json")

    assert set(contract["ports"]) >= {"3560", "3571", "3572", "8080", "11434", "11435"}
    assert contract["ports"]["3571"]["public_to_openwebui"] is True
    assert contract["ports"]["3572"]["public_to_openwebui"] is False


def test_env_contract_keeps_venv_boundaries_distinct() -> None:
    contract = _read_json("services/launch/contracts/env_contract.json")

    assert contract["venvs"]["bridge_and_broker"] == "venvs/labtools"
    assert contract["venvs"]["openwebui"] == "venvs/openwebui"
    assert contract["venvs"]["bridge_and_broker"] != contract["venvs"]["openwebui"]


def test_launch_order_registers_only_3571_openapi() -> None:
    text = (ROOT / "services/launch/contracts/launch_order.md").read_text(encoding="utf-8")

    assert "http://127.0.0.1:3571/openapi.json" in text
    assert "3572/openapi" not in text
