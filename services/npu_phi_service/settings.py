from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path


logger = logging.getLogger(__name__)


def _bool_env(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class NpuPhiSettings:
    ai_root: Path
    host: str
    port: int
    model_dir: Path
    cache_dir: Path
    spool_dir: Path
    queue_maxsize: int
    exec_timeout_sec: float
    generate_hint: str
    enable_aot_blob: bool
    device: str = "NPU"

    @classmethod
    def from_env(cls) -> "NpuPhiSettings":
        ai_root = Path(os.environ.get("AI_ROOT") or Path.cwd()).resolve()
        model_dir = Path(
            os.environ.get("NPU_PHI_MODEL_DIR")
            or ai_root / "npu-models" / "Phi-3.5-mini-instruct-int4-cw-ov"
        ).resolve()
        cache_dir = Path(os.environ.get("NPU_PHI_CACHE_DIR") or ai_root / "cache" / "openvino" / "npu_phi").resolve()
        spool_dir = Path(os.environ.get("NPU_PHI_SPOOL_DIR") or ai_root / "state" / "npu_phi" / "spool").resolve()
        return cls(
            ai_root=ai_root,
            host=os.environ.get("NPU_PHI_HOST") or "127.0.0.1",
            port=int(os.environ.get("NPU_PHI_PORT") or "3551"),
            model_dir=model_dir,
            cache_dir=cache_dir,
            spool_dir=spool_dir,
            queue_maxsize=max(1, int(os.environ.get("NPU_PHI_QUEUE_MAXSIZE") or "1")),
            exec_timeout_sec=max(1.0, float(os.environ.get("NPU_PHI_EXEC_TIMEOUT_SEC") or "12")),
            generate_hint=os.environ.get("NPU_PHI_GENERATE_HINT") or "FAST_COMPILE",
            enable_aot_blob=_bool_env(os.environ.get("NPU_PHI_ENABLE_AOT_BLOB"), default=True),
        )

    @property
    def model_xml(self) -> Path:
        return self.model_dir / "openvino_model.xml"

    @property
    def model_bin(self) -> Path:
        return self.model_dir / "openvino_model.bin"

    @property
    def blob_path(self) -> Path:
        return self.cache_dir / "phi35_npu.blob"

    def ensure_runtime_dirs(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.spool_dir.mkdir(parents=True, exist_ok=True)
        if not self.model_dir.exists():
            logger.warning("NPU Phi model directory does not exist: %s", self.model_dir)
        for dir_path in (self.cache_dir, self.spool_dir):
            if not os.access(dir_path, os.W_OK):
                logger.warning("NPU Phi runtime directory is not writable: %s", dir_path)

    def model_status(self) -> dict[str, object]:
        xml_exists = self.model_xml.exists()
        bin_exists = self.model_bin.exists()
        return {
            "model_dir": str(self.model_dir),
            "openvino_model_xml_exists": xml_exists,
            "openvino_model_bin_exists": bin_exists,
            "model_ready": xml_exists and bin_exists,
        }

    def public_config(self) -> dict[str, object]:
        return {
            "host": self.host,
            "port": self.port,
            "device": self.device,
            "model_dir": str(self.model_dir),
            "cache_dir": str(self.cache_dir),
            "spool_dir": str(self.spool_dir),
            "queue_maxsize": self.queue_maxsize,
            "exec_timeout_sec": self.exec_timeout_sec,
            "generate_hint": self.generate_hint,
            "enable_aot_blob": self.enable_aot_blob,
        }
