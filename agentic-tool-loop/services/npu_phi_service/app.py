from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException

from . import __version__
from .circuit_breaker import CircuitBreaker
from .job_queue import NpuPhiJobQueue
from .pipeline import PipelineManager
from .schemas import DEFAULT_SCENE_SPEC_SCHEMA, SceneSpecRequest, WarmupRequest, build_scene_prompt
from .settings import NpuPhiSettings


def create_app(
    *,
    settings: NpuPhiSettings | None = None,
    pipeline_manager: PipelineManager | None = None,
    circuit_breaker: CircuitBreaker | None = None,
) -> FastAPI:
    resolved_settings = settings or NpuPhiSettings.from_env()
    resolved_settings.ensure_runtime_dirs()
    manager = pipeline_manager or PipelineManager(resolved_settings)
    breaker = circuit_breaker or CircuitBreaker()
    queue = NpuPhiJobQueue(
        pipeline_manager=manager,
        spool_dir=resolved_settings.spool_dir,
        maxsize=resolved_settings.queue_maxsize,
        on_job_success=breaker.record_success,
        on_job_failure=breaker.record_failure,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await queue.start()
        try:
            yield
        finally:
            await queue.stop()

    app = FastAPI(
        title="AI-Carmine NPU Phi Diagnostic Sidecar",
        version=__version__,
        lifespan=lifespan,
    )

    app.state.settings = resolved_settings
    app.state.pipeline_manager = manager
    app.state.queue = queue
    app.state.circuit_breaker = breaker

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {
            "schema": "npu_phi_health.v1",
            "ok": True,
            "service": "npu_phi_service",
            "version": __version__,
            "port": resolved_settings.port,
        }

    @app.get("/readyz")
    async def readyz() -> dict[str, Any]:
        ready = manager.readiness()
        return {
            **ready,
            "ok": bool(ready.get("model_ready")) and bool(ready.get("openvino_genai_available")),
            "runtime_python": {
                "executable": sys.executable,
                "prefix": sys.prefix,
            },
            "config": resolved_settings.public_config(),
            "queue": queue.snapshot_metrics(),
            "circuit_breaker": breaker.snapshot(),
        }

    @app.get("/metrics")
    async def metrics() -> dict[str, Any]:
        return {
            **queue.snapshot_metrics(),
            "pipeline_build_count": manager.build_count,
            "circuit_breaker": breaker.snapshot(),
        }

    @app.post("/v1/jobs/scene-spec", status_code=202)
    async def enqueue_scene_spec(request: SceneSpecRequest) -> dict[str, Any]:
        if not breaker.allow_request():
            return {
                "schema": "npu_phi_enqueue.v1",
                "accepted": False,
                "reason": "breaker_open",
                "circuit_breaker": breaker.snapshot(),
            }
        schema = request.json_schema or DEFAULT_SCENE_SPEC_SCHEMA
        prompt = build_scene_prompt(request)
        response = await queue.enqueue(
            prompt=prompt,
            json_schema=schema,
            max_new_tokens=request.max_new_tokens,
            timeout_s=request.timeout_s or resolved_settings.exec_timeout_sec,
            dedup_payload={
                "goal": request.goal,
                "prompt": prompt,
                "schema_version": request.schema_version,
                "json_schema": schema,
                "evidence_hash": request.evidence_hash,
            },
        )
        return {
            "schema": "npu_phi_enqueue.v1",
            **response,
            "circuit_breaker": breaker.snapshot(),
        }

    @app.get("/v1/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, Any]:
        job = queue.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="NPU Phi job not found")
        return job

    @app.post("/v1/admin/warmup")
    async def warmup(_: WarmupRequest) -> dict[str, Any]:
        try:
            await manager.get_pipeline()
        except Exception as exc:
            breaker.record_failure()
            return {
                "schema": "npu_phi_warmup.v1",
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc)[:1000],
                "circuit_breaker": breaker.snapshot(),
            }
        breaker.record_success()
        return {
            "schema": "npu_phi_warmup.v1",
            "ok": True,
            "readiness": manager.readiness(),
            "circuit_breaker": breaker.snapshot(),
        }

    @app.post("/v1/admin/reset-circuit")
    async def reset_circuit() -> dict[str, Any]:
        breaker.reset()
        return {
            "schema": "npu_phi_circuit_reset.v1",
            "ok": True,
            "circuit_breaker": breaker.snapshot(),
        }

    return app
