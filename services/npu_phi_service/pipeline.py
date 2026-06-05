from __future__ import annotations

import asyncio
import importlib.util
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .blob_lock import BlobBuildLock
from .settings import NpuPhiSettings


PipelineFactory = Callable[[str, str, dict[str, object]], Any]


class PipelineManager:
    def __init__(
        self,
        settings: NpuPhiSettings,
        *,
        pipeline_factory: PipelineFactory | None = None,
    ) -> None:
        self.settings = settings
        self._pipeline_factory = pipeline_factory
        self._pipeline: Any | None = None
        self._lock = asyncio.Lock()
        self._build_count = 0
        self._last_build_seconds: float | None = None
        self._last_error: str = ""
        self._last_blob_lock_path: str = ""

    @property
    def build_count(self) -> int:
        return self._build_count

    def dependency_status(self) -> dict[str, object]:
        genai_spec = importlib.util.find_spec("openvino_genai")
        ov_spec = importlib.util.find_spec("openvino")
        return {
            "openvino_available": ov_spec is not None,
            "openvino_genai_available": genai_spec is not None,
        }

    def pipeline_config(self) -> dict[str, object]:
        config: dict[str, object] = {
            "CACHE_DIR": str(self.settings.cache_dir),
            "GENERATE_HINT": self.settings.generate_hint,
        }
        if self.settings.enable_aot_blob:
            config["EXPORT_BLOB"] = "YES"
            config["BLOB_PATH"] = str(self.settings.blob_path)
        return config

    @property
    def blob_lock_path(self) -> str:
        if not self.settings.enable_aot_blob:
            return ""
        return str(self.settings.cache_dir / "phi35_npu.blob.lock")

    async def get_pipeline(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        async with self._lock:
            if self._pipeline is not None:
                return self._pipeline
            status = self.settings.model_status()
            if not status["model_ready"]:
                self._last_error = "model_files_missing"
                raise RuntimeError("NPU Phi model files are missing")
            self.settings.ensure_runtime_dirs()
            start = time.perf_counter()
            try:
                self._pipeline = await asyncio.to_thread(self._build_pipeline_with_optional_lock)
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {str(exc)[:1000]}"
                raise
            self._build_count += 1
            self._last_build_seconds = time.perf_counter() - start
            self._last_error = ""
            return self._pipeline

    def _build_pipeline_with_optional_lock(self) -> Any:
        if not self.settings.enable_aot_blob:
            self._last_blob_lock_path = ""
            return self._build_pipeline()
        lock = BlobBuildLock(Path(self.blob_lock_path))
        self._last_blob_lock_path = str(lock.path)
        with lock:
            return self._build_pipeline()

    def _build_pipeline(self) -> Any:
        if self._pipeline_factory is not None:
            return self._pipeline_factory(
                str(self.settings.model_dir),
                self.settings.device,
                self.pipeline_config(),
            )
        import openvino_genai as ov_genai

        return ov_genai.LLMPipeline(
            str(self.settings.model_dir),
            self.settings.device,
            self.pipeline_config(),
        )

    async def generate_structured(
        self,
        *,
        prompt: str,
        json_schema: dict[str, Any] | None,
        max_new_tokens: int,
        timeout_s: float,
    ) -> dict[str, Any]:
        pipe = await self.get_pipeline()
        result_text = await asyncio.wait_for(
            asyncio.to_thread(
                self._generate_blocking,
                pipe,
                prompt,
                json_schema,
                max_new_tokens,
            ),
            timeout=timeout_s,
        )
        parsed: Any | None = None
        parse_error = ""
        try:
            parsed = json.loads(result_text)
        except Exception as exc:
            parse_error = f"{type(exc).__name__}: {str(exc)[:500]}"
        return {
            "text": result_text,
            "json": parsed,
            "json_parse_ok": parse_error == "",
            "json_parse_error": parse_error,
        }

    def _generate_blocking(
        self,
        pipe: Any,
        prompt: str,
        json_schema: dict[str, Any] | None,
        max_new_tokens: int,
    ) -> str:
        if self._pipeline_factory is not None:
            return str(pipe.generate(prompt))
        import openvino_genai as ov_genai

        generation_config = ov_genai.GenerationConfig()
        generation_config.max_new_tokens = max_new_tokens
        generation_config.temperature = 0.0
        generation_config.do_sample = False
        if json_schema:
            structured = ov_genai.StructuredOutputConfig()
            structured.json_schema = json.dumps(json_schema, ensure_ascii=False, sort_keys=True)
            generation_config.structured_output_config = structured
        return str(pipe.generate(prompt, generation_config))

    def readiness(self) -> dict[str, object]:
        status = {
            "schema": "npu_phi_readiness.v1",
            "warmed": self._pipeline is not None,
            "build_count": self._build_count,
            "last_build_seconds": self._last_build_seconds,
            "last_error": self._last_error,
            "blob_lock_path": self._last_blob_lock_path,
        }
        status.update(self.settings.model_status())
        status.update(self.dependency_status())
        return status
