from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_port_contract_contains_expected_runtime_ports() -> None:
    contract = _read_json("services/launch/contracts/ports_contract.json")

    assert set(contract["ports"]) >= {"3550", "3551", "3560", "3571", "3572", "8080", "11434", "11435"}
    assert contract["ports"]["3550"]["role"] == "openvino_external_reranker"
    assert contract["ports"]["3551"]["role"] == "npu_phi_diagnostic_sidecar"
    assert contract["ports"]["3551"]["enabled_default"] is False
    assert contract["ports"]["3551"]["distinct_from"] == 3550
    assert contract["ports"]["3571"]["public_to_openwebui"] is True
    assert contract["ports"]["3572"]["public_to_openwebui"] is False


def test_env_contract_keeps_venv_boundaries_distinct() -> None:
    contract = _read_json("services/launch/contracts/env_contract.json")

    assert contract["venvs"]["bridge_and_broker"] == "venvs/labtools"
    assert contract["venvs"]["openwebui"] == "venvs/openwebui"
    assert contract["venvs"]["openvino"] == "venvs/openvino"
    assert contract["venvs"]["bridge_and_broker"] != contract["venvs"]["openwebui"]
    assert contract["venvs"]["openvino"] != contract["venvs"]["bridge_and_broker"]
    assert contract["venvs"]["openvino"] != contract["venvs"]["openwebui"]


def test_npu_phi_launcher_contract_uses_openvino_venv_and_3551() -> None:
    text = (ROOT / "services/launch/openwebui_runtime.ps1").read_text(encoding="utf-8")
    env_contract = _read_json("services/launch/contracts/env_contract.json")
    ports_contract = _read_json("services/launch/contracts/ports_contract.json")

    assert "NPU_PHI_PORT = 3551" in text
    assert '$NPU_PHI_PYTHON_EXE = Set-UserEnvValue "NPU_PHI_PYTHON_EXE" $OPENVINO_PYTHON_EXE' in text
    assert '$NPU_PHI_ENV_SCRIPT = Set-UserEnvValue "NPU_PHI_ENV_SCRIPT" $OPENVINO_ENV_SCRIPT' in text
    assert 'Set-UserEnvDefault "ENABLE_NPU_PHI_SERVICE" "0"' in text
    assert "Start-NpuPhiServiceIfEnabled" in text
    assert "venvs\\labtools" not in text[text.find("$NPU_PHI_PYTHON_EXE") : text.find("$NPU_PHI_ENV_SCRIPT")]
    assert env_contract["npu_phi_service"]["python_env"] == "openvino"
    assert env_contract["npu_phi_service"]["enabled_default"] == "0"
    assert env_contract["npu_phi_service"]["provider_port"] == 3551
    assert ports_contract["ports"]["3551"]["public_to_openwebui"] is False


def test_npu_phi_does_not_change_openvino_reranker_contract() -> None:
    text = (ROOT / "services/launch/openwebui_runtime.ps1").read_text(encoding="utf-8")
    env_contract = _read_json("services/launch/contracts/env_contract.json")
    ports_contract = _read_json("services/launch/contracts/ports_contract.json")

    assert "OPENVINO_PORT = 3550" in text
    assert 'Set-UserEnvValue "OPENVINO_PROVIDER_DEVICE" "GPU.0"' in text
    assert 'Set-UserEnvValue "RAG_EXTERNAL_RERANKER_URL" "http://$($config.HOSTNAME):$($config.OPENVINO_PORT)/v3/rerank"' in text
    assert env_contract["openvino_provider"]["provider_port"] == 3550
    assert env_contract["npu_phi_service"]["must_not_change_openvino_provider_port"] == 3550
    assert ports_contract["ports"]["3550"]["role"] == "openvino_external_reranker"
    assert ports_contract["ports"]["3551"]["distinct_from"] == 3550


def test_launch_order_registers_only_3571_openapi() -> None:
    text = (ROOT / "services/launch/contracts/launch_order.md").read_text(encoding="utf-8")

    assert "http://127.0.0.1:3571/openapi.json" in text
    assert "3572/openapi" not in text


def test_launcher_comment_matches_openvino_default_on() -> None:
    text = (ROOT / "services/launch/openwebui_runtime.ps1").read_text(encoding="utf-8")
    contract = _read_json("services/launch/contracts/env_contract.json")

    assert 'Set-UserEnvValue "ENABLE_OPENVINO_PROVIDER" "1"' in text
    assert 'Set-UserEnvValue "ENABLE_EXTERNAL_RERANKER" "1"' in text
    assert "Default ON" in text
    assert "Default OFF" not in text
    assert contract["openvino_provider"]["enabled_default"] == "1"
    assert contract["openvino_provider"]["external_reranker_default"] == "1"
