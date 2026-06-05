from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from npu_phi_service.app import create_app  # noqa: E402
from npu_phi_service.blob_lock import BlobBuildLock  # noqa: E402
from npu_phi_service.diagnostics import build_npu_phi_doctor  # noqa: E402
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


def test_npu_phi_blob_lock_prevents_parallel_export(tmp_path: Path) -> None:
    lock_path = tmp_path / "cache" / "phi35_npu.blob.lock"
    first = BlobBuildLock(lock_path)
    second = BlobBuildLock(lock_path)

    assert first.acquire() is True
    try:
        assert second.acquire() is False
    finally:
        first.release()

    assert not lock_path.exists()


def test_npu_phi_blob_lock_recovers_stale_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / "cache" / "phi35_npu.blob.lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text('{"pid": 0}', encoding="utf-8")
    old = 1
    import os

    os.utime(lock_path, (old, old))
    lock = BlobBuildLock(lock_path, stale_after_s=1)

    assert lock.acquire() is True
    lock.release()
    assert not lock_path.exists()


def test_npu_phi_pipeline_uses_blob_lock_when_aot_enabled(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings = NpuPhiSettings(
        ai_root=settings.ai_root,
        host=settings.host,
        port=settings.port,
        model_dir=settings.model_dir,
        cache_dir=settings.cache_dir,
        spool_dir=settings.spool_dir,
        queue_maxsize=settings.queue_maxsize,
        exec_timeout_sec=settings.exec_timeout_sec,
        generate_hint=settings.generate_hint,
        enable_aot_blob=True,
    )
    manager = PipelineManager(settings, pipeline_factory=lambda *_: FakePipeline())

    asyncio.run(manager.get_pipeline())
    readiness = manager.readiness()

    assert readiness["blob_lock_path"].endswith("phi35_npu.blob.lock")
    assert not Path(str(readiness["blob_lock_path"])).exists()


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

    assert "[switch]$Doctor" in text
    assert "venvs\\openvino\\Scripts\\python.exe" in text
    assert "services\\openvino-env.ps1" in text
    assert "openvino_model.xml" in text
    assert "openvino_model.bin" in text
    assert "-m npu_phi_service" in text
    assert "--doctor --pretty" in text
    assert "venvs\\labtools" not in text


def test_npu_phi_doctor_reports_ready_without_creating_runtime_dirs(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    cache_dir = settings.cache_dir
    spool_dir = settings.spool_dir
    dependencies = {
        "openvino_available": True,
        "openvino_genai_available": True,
        "fastapi_available": True,
        "uvicorn_available": True,
        "pydantic_available": True,
        "packages": {},
    }

    result = build_npu_phi_doctor(settings, dependencies=dependencies)

    assert result["schema"] == "npu_phi_doctor.v1"
    assert result["ok"] is True
    assert result["diagnostic_only"] is True
    assert result["side_effects"] == "none"
    assert result["model"]["model_ready"] is True
    assert result["contract"]["port"] == 3551
    assert result["contract"]["distinct_from_openvino_reranker_port"] is True
    assert result["runtime_paths"]["cache_dir"]["exists"] is False
    assert result["runtime_paths"]["spool_dir"]["exists"] is False
    assert not cache_dir.exists()
    assert not spool_dir.exists()


def test_npu_phi_doctor_warns_when_port_collides_with_reranker(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings = NpuPhiSettings(
        ai_root=settings.ai_root,
        host=settings.host,
        port=3550,
        model_dir=settings.model_dir,
        cache_dir=settings.cache_dir,
        spool_dir=settings.spool_dir,
        queue_maxsize=settings.queue_maxsize,
        exec_timeout_sec=settings.exec_timeout_sec,
        generate_hint=settings.generate_hint,
        enable_aot_blob=settings.enable_aot_blob,
    )

    result = build_npu_phi_doctor(
        settings,
        dependencies={
            "openvino_available": True,
            "openvino_genai_available": True,
            "fastapi_available": True,
            "uvicorn_available": True,
            "pydantic_available": True,
            "packages": {},
        },
    )

    assert result["ok"] is False
    assert result["contract"]["distinct_from_openvino_reranker_port"] is False
    assert result["warnings"][0]["rule"] == "port_collides_with_openvino_reranker"


def test_npu_phi_doctor_requires_openvino_runtime_dependency(tmp_path: Path) -> None:
    result = build_npu_phi_doctor(
        _settings(tmp_path),
        dependencies={
            "openvino_available": False,
            "openvino_genai_available": True,
            "fastapi_available": True,
            "uvicorn_available": True,
            "pydantic_available": True,
            "packages": {},
        },
    )

    assert result["ok"] is False
    missing = next(w for w in result["warnings"] if w["rule"] == "missing_runtime_dependencies")
    assert "openvino" in missing["packages"]


def test_npu_phi_main_exposes_doctor_cli() -> None:
    text = (ROOT / "services" / "npu_phi_service" / "__main__.py").read_text(encoding="utf-8")

    assert "--doctor" in text
    assert "doctor_json" in text
    assert "replace(settings, host=args.host, port=args.port)" in text
