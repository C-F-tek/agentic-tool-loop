from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from collections.abc import Callable
from typing import Any

from .pipeline import PipelineManager


logger = logging.getLogger(__name__)


def _stable_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


@dataclass
class NpuPhiJob:
    job_id: str
    dedup_key: str
    prompt: str
    json_schema: dict[str, Any] | None
    max_new_tokens: int
    timeout_s: float
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    result: dict[str, Any] | None = None
    error: str = ""
    error_type: str = ""

    def snapshot(self) -> dict[str, Any]:
        out = asdict(self)
        out["schema"] = "npu_phi_job.v1"
        out["prompt_chars"] = len(self.prompt)
        out.pop("prompt", None)
        return out


class NpuPhiJobQueue:
    def __init__(
        self,
        *,
        pipeline_manager: PipelineManager,
        spool_dir: Path,
        maxsize: int = 1,
        on_job_success: Callable[[], None] | None = None,
        on_job_failure: Callable[[], None] | None = None,
    ) -> None:
        self.pipeline_manager = pipeline_manager
        self.spool_dir = spool_dir
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=max(1, maxsize))
        self.jobs: dict[str, NpuPhiJob] = {}
        self.dedup: dict[str, str] = {}
        self.worker_task: asyncio.Task[None] | None = None
        self.on_job_success = on_job_success
        self.on_job_failure = on_job_failure
        self.metrics = {
            "jobs_enqueued_total": 0,
            "jobs_dropped_total": 0,
            "jobs_completed_total": 0,
            "jobs_failed_total": 0,
        }

    async def start(self) -> None:
        self.spool_dir.mkdir(parents=True, exist_ok=True)
        if self.worker_task is None or self.worker_task.done():
            self.worker_task = asyncio.create_task(self._worker(), name="npu_phi_worker")

    async def stop(self) -> None:
        if self.worker_task is None:
            return
        if not self.queue.empty():
            try:
                await asyncio.wait_for(self.queue.join(), timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning("NPU Phi worker shutdown with queued jobs still pending: queue_depth=%s", self.queue.qsize())
        self.worker_task.cancel()
        try:
            await asyncio.wait_for(self.worker_task, timeout=5.0)
        except asyncio.CancelledError:
            logger.debug("NPU Phi worker task cancelled during shutdown")
        except asyncio.TimeoutError:
            logger.warning("NPU Phi worker did not stop within shutdown timeout")
        except Exception as exc:
            logger.error("NPU Phi worker shutdown failed: %s", exc)
        self.worker_task = None

    def make_dedup_key(self, payload: dict[str, Any]) -> str:
        return _stable_hash(payload)[:32]

    async def enqueue(
        self,
        *,
        prompt: str,
        json_schema: dict[str, Any] | None,
        max_new_tokens: int,
        timeout_s: float,
        dedup_payload: dict[str, Any],
    ) -> dict[str, Any]:
        dedup_key = self.make_dedup_key(dedup_payload)
        existing_id = self.dedup.get(dedup_key)
        if existing_id and existing_id in self.jobs:
            existing = self.jobs[existing_id]
            return {
                "accepted": True,
                "duplicate": True,
                "job_id": existing.job_id,
                "dedup_key": dedup_key,
                "status": existing.status,
                "queue_depth": self.queue.qsize(),
            }
        if self.queue.full():
            self.metrics["jobs_dropped_total"] += 1
            return {
                "accepted": False,
                "duplicate": False,
                "reason": "queue_full",
                "dedup_key": dedup_key,
                "queue_depth": self.queue.qsize(),
            }
        job = NpuPhiJob(
            job_id=f"npu-{uuid.uuid4().hex[:12]}",
            dedup_key=dedup_key,
            prompt=prompt,
            json_schema=json_schema,
            max_new_tokens=max_new_tokens,
            timeout_s=timeout_s,
        )
        self.jobs[job.job_id] = job
        self.dedup[dedup_key] = job.job_id
        await self.queue.put(job.job_id)
        self.metrics["jobs_enqueued_total"] += 1
        self._write_job(job)
        return {
            "accepted": True,
            "duplicate": False,
            "job_id": job.job_id,
            "dedup_key": dedup_key,
            "status": job.status,
            "queue_depth": self.queue.qsize(),
        }

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        job = self.jobs.get(job_id)
        if job is not None:
            return job.snapshot()
        path = self.spool_dir / f"{job_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def snapshot_metrics(self) -> dict[str, Any]:
        return {
            "schema": "npu_phi_metrics.v1",
            **self.metrics,
            "queue_depth": self.queue.qsize(),
            "jobs_known": len(self.jobs),
            "worker_running": self.worker_task is not None and not self.worker_task.done(),
        }

    async def _worker(self) -> None:
        while True:
            job_id = await self.queue.get()
            try:
                await self._run_job(job_id)
            finally:
                self.queue.task_done()

    async def _run_job(self, job_id: str) -> None:
        job = self.jobs[job_id]
        job.status = "running"
        job.started_at = time.time()
        job.updated_at = job.started_at
        self._write_job(job)
        try:
            result = await self.pipeline_manager.generate_structured(
                prompt=job.prompt,
                json_schema=job.json_schema,
                max_new_tokens=job.max_new_tokens,
                timeout_s=job.timeout_s,
            )
        except asyncio.TimeoutError:
            job.status = "expired"
            job.error_type = "TimeoutError"
            job.error = f"NPU Phi job exceeded timeout_s={job.timeout_s}"
            self.metrics["jobs_failed_total"] += 1
            if self.on_job_failure is not None:
                self.on_job_failure()
        except Exception as exc:
            job.status = "failed"
            job.error_type = type(exc).__name__
            job.error = str(exc)[:1000]
            self.metrics["jobs_failed_total"] += 1
            if self.on_job_failure is not None:
                self.on_job_failure()
        else:
            job.status = "completed"
            job.result = result
            self.metrics["jobs_completed_total"] += 1
            if self.on_job_success is not None:
                self.on_job_success()
        finally:
            job.finished_at = time.time()
            job.updated_at = job.finished_at
            self._write_job(job)

    def _write_job(self, job: NpuPhiJob) -> None:
        _atomic_write_json(self.spool_dir / f"{job.job_id}.json", job.snapshot())
