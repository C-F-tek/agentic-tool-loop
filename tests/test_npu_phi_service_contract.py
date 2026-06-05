from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from npu_phi_service.app import create_app  # noqa: E402
from npu_phi_service.job_queue import NpuPhiJobQueue  # noqa: E402
from npu_phi_service.pipeline import PipelineManager  # noqa: E402
from npu_phi_service.settings import NpuPhiSettings  # noqa: E402


class FakePipeline:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        return '{"title":"ok","summary":"done","scene_elements":[],"camera":"static","lighting":"soft","risks":[]}'


class FailingPipeline:
    def generate(self, prompt: str) -> str:
        raise RuntimeError("npu failure")


def _settings(tmp_path: Path) -> NpuPhiSettings:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "openvino_model.xml").write_text("<xml />", encoding="utf-8")
    (model_dir / "openvino_model.bin").write_bytes(b"bin")
    return NpuPhiSettings(
        ai_root=tmp_path,
        host="127.0.0.1",
        port=3551,
        model_dir=model_dir,
        cache_dir=tmp_path / "cache",
        spool_dir=tmp_path / "spool",
        queue_maxsize=1,
        exec_timeout_sec=2.0,
        generate_hint="FAST_COMPILE",
        enable_aot_blob=False,
    )


def test_npu_phi_settings_reports_model_files(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    status = settings.model_status()

    assert status["model_ready"] is True
    assert status["openvino_model_xml_exists"] is True
    assert status["openvino_model_bin_exists"] is True


def test_npu_phi_pipeline_singleton_builds_once(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    calls: list[tuple[str, str, dict[str, object]]] = []

    def factory(model_dir: str, device: str, config: dict[str, object]) -> FakePipeline:
        calls.append((model_dir, device, config))
        return FakePipeline()

    manager = PipelineManager(settings, pipeline_factory=factory)

    first = asyncio.run(manager.get_pipeline())
    second = asyncio.run(manager.get_pipeline())

    assert first is second
    assert len(calls) == 1
    assert calls[0][1] == "NPU"
    assert calls[0][2]["CACHE_DIR"] == str(settings.cache_dir)


def test_npu_phi_queue_drops_when_full(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    manager = PipelineManager(settings, pipeline_factory=lambda *_: FakePipeline())
    queue = NpuPhiJobQueue(pipeline_manager=manager, spool_dir=settings.spool_dir, maxsize=1)

    async def run() -> tuple[dict, dict]:
        first = await queue.enqueue(
            prompt="a",
            json_schema=None,
            max_new_tokens=64,
            timeout_s=1,
            dedup_payload={"prompt": "a"},
        )
        second = await queue.enqueue(
            prompt="b",
            json_schema=None,
            max_new_tokens=64,
            timeout_s=1,
            dedup_payload={"prompt": "b"},
        )
        return first, second

    first, second = asyncio.run(run())

    assert first["accepted"] is True
    assert second["accepted"] is False
    assert second["reason"] == "queue_full"
    assert queue.snapshot_metrics()["jobs_dropped_total"] == 1


def test_npu_phi_app_health_ready_and_job_flow(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    manager = PipelineManager(settings, pipeline_factory=lambda *_: FakePipeline())
    app = create_app(settings=settings, pipeline_manager=manager)

    with TestClient(app) as client:
        health = client.get("/healthz").json()
        ready = client.get("/readyz").json()
        accepted = client.post("/v1/jobs/scene-spec", json={"goal": "make a scene"}).json()

        assert health["ok"] is True
        assert ready["model_ready"] is True
        assert ready["ok"] is bool(ready["openvino_genai_available"])
        assert ready["runtime_python"]["executable"]
        assert ready["runtime_python"]["prefix"]
        assert ready["config"]["port"] == 3551
        assert accepted["accepted"] is True
        assert accepted["job_id"].startswith("npu-")


def test_npu_phi_app_opens_breaker_after_job_failures(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    manager = PipelineManager(settings, pipeline_factory=lambda *_: FailingPipeline())
    app = create_app(settings=settings, pipeline_manager=manager)

    with TestClient(app) as client:
        for index in range(3):
            response = client.post("/v1/jobs/scene-spec", json={"goal": f"fail {index}"}).json()
            assert response["accepted"] is True
            job_id = response["job_id"]
            for _ in range(20):
                job = client.get(f"/v1/jobs/{job_id}").json()
                if job["status"] == "failed":
                    break
            assert job["status"] == "failed"

        blocked = client.post("/v1/jobs/scene-spec", json={"goal": "blocked"}).json()

        assert blocked["accepted"] is False
        assert blocked["reason"] == "breaker_open"
        assert blocked["circuit_breaker"]["state"] == "open"


def test_npu_phi_service_wrapper_uses_openvino_runtime() -> None:
    text = (ROOT / "services" / "npu-phi-service.ps1").read_text(encoding="utf-8")

    assert "venvs\\openvino\\Scripts\\python.exe" in text
    assert "services\\openvino-env.ps1" in text
    assert "openvino_model.xml" in text
    assert "openvino_model.bin" in text
    assert "-m npu_phi_service" in text
    assert "venvs\\labtools" not in text
