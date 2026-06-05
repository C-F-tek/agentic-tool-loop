from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.npu_phi import NpuPhiClientConfig, enqueue_scene_spec_best_effort  # noqa: E402


def test_npu_phi_client_disabled_does_not_attempt_http() -> None:
    called = False

    def post(_: str, __: dict, ___: float) -> dict:
        nonlocal called
        called = True
        return {}

    result = enqueue_scene_spec_best_effort(
        goal="scene",
        config=NpuPhiClientConfig(enabled=False),
        http_post=post,
    )

    assert result["attempted"] is False
    assert result["status"] == "disabled"
    assert called is False


def test_npu_phi_client_config_loads_from_env_mapping() -> None:
    config = NpuPhiClientConfig.from_env(
        {
            "ENABLE_NPU_PHI_BROKER_DIAGNOSTICS": "1",
            "NPU_PHI_BASE_URL": "http://127.0.0.1:3551/",
            "NPU_PHI_BROKER_MODE": "best_effort",
            "NPU_PHI_CLIENT_TIMEOUT_SEC": "0.05",
        }
    )

    assert config.enabled is True
    assert config.base_url == "http://127.0.0.1:3551"
    assert config.timeout_s == 0.05


def test_npu_phi_client_best_effort_returns_enqueue_metadata() -> None:
    def post(url: str, payload: dict, timeout_s: float) -> dict:
        assert url == "http://127.0.0.1:3551/v1/jobs/scene-spec"
        assert payload["goal"] == "scene"
        assert timeout_s == 0.15
        return {"accepted": True, "job_id": "npu-abc", "dedup_key": "k", "queue_depth": 1}

    result = enqueue_scene_spec_best_effort(
        goal="scene",
        config=NpuPhiClientConfig(enabled=True, base_url="http://127.0.0.1:3551"),
        http_post=post,
    )

    assert result["attempted"] is True
    assert result["ok"] is True
    assert result["accepted"] is True
    assert result["job_id"] == "npu-abc"
    assert result["queue_depth"] == 1


def test_npu_phi_client_best_effort_swallow_errors() -> None:
    def post(_: str, __: dict, ___: float) -> dict:
        raise TimeoutError("slow sidecar")

    result = enqueue_scene_spec_best_effort(
        goal="scene",
        config=NpuPhiClientConfig(enabled=True),
        http_post=post,
    )

    assert result["attempted"] is True
    assert result["ok"] is False
    assert result["status"] == "enqueue_failed"
    assert result["error_type"] == "TimeoutError"


def test_npu_phi_client_rejects_non_best_effort_mode_without_http() -> None:
    called = False

    def post(_: str, __: dict, ___: float) -> dict:
        nonlocal called
        called = True
        return {}

    result = enqueue_scene_spec_best_effort(
        goal="scene",
        config=NpuPhiClientConfig(enabled=True, mode="blocking"),
        http_post=post,
    )

    assert result["attempted"] is False
    assert result["status"] == "unsupported_mode"
    assert called is False
