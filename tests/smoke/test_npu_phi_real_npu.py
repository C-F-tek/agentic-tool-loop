from __future__ import annotations

import json
import os
import time
import urllib.request

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("NPU_PHI_REAL_NPU_SMOKE") != "1",
    reason="Set NPU_PHI_REAL_NPU_SMOKE=1 to run the real NPU Phi sidecar smoke test.",
)


def _request_json(method: str, url: str, payload: dict | None = None) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        decoded = response.read().decode("utf-8", errors="replace")
    return json.loads(decoded)


def test_npu_phi_sidecar_generates_structured_scene_spec_on_real_npu() -> None:
    base_url = os.environ.get("NPU_PHI_BASE_URL", "http://127.0.0.1:3551").rstrip("/")
    timeout_s = float(os.environ.get("NPU_PHI_REAL_NPU_SMOKE_TIMEOUT_SEC", "45"))

    ready = _request_json("GET", f"{base_url}/readyz")
    assert ready["ok"] is True
    assert ready["model_ready"] is True
    assert ready["config"]["device"] == "NPU"
    assert ready["config"]["port"] == 3551

    accepted = _request_json(
        "POST",
        f"{base_url}/v1/jobs/scene-spec",
        {
            "goal": "Generate a compact diagnostic Blender scene spec for a neon logo reveal.",
            "max_new_tokens": 160,
            "timeout_s": timeout_s,
        },
    )
    assert accepted["accepted"] is True, accepted
    job_id = accepted["job_id"]

    deadline = time.time() + timeout_s + 10
    job = {}
    while time.time() < deadline:
        job = _request_json("GET", f"{base_url}/v1/jobs/{job_id}")
        if job.get("status") in {"completed", "failed", "expired"}:
            break
        time.sleep(0.5)

    assert job.get("status") == "completed", job
    result = job.get("result") or {}
    assert result.get("json_parse_ok") is True
    assert isinstance(result.get("json"), dict)
    assert result["json"].get("title")
