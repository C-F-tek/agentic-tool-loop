from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path


logger = logging.getLogger(__name__)


class BlobBuildLock:
    def __init__(self, path: Path, *, stale_after_s: int = 1200) -> None:
        self.path = path
        self.stale_after_s = stale_after_s
        self._fd: int | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                age = time.time() - self.path.stat().st_mtime
            except OSError as exc:
                logger.warning("Unable to stat NPU Phi blob lock %s: %s", self.path, exc)
                age = 0.0
            if age > self.stale_after_s:
                try:
                    logger.info("Removing stale NPU Phi blob lock: %s age_s=%.1f", self.path, age)
                    self.path.unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning("Unable to remove stale NPU Phi blob lock %s: %s", self.path, exc)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            self._fd = os.open(str(self.path), flags)
        except FileExistsError:
            logger.debug("NPU Phi blob lock already held: %s", self.path)
            return False
        except OSError as exc:
            logger.error("Unable to acquire NPU Phi blob lock %s: %s", self.path, exc)
            raise
        payload = {"pid": os.getpid(), "ts": time.time()}
        try:
            os.write(self._fd, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        except OSError:
            os.close(self._fd)
            self._fd = None
            try:
                self.path.unlink(missing_ok=True)
            except OSError as cleanup_exc:
                logger.warning("Unable to clean failed NPU Phi blob lock %s: %s", self.path, cleanup_exc)
            raise
        return True

    def release(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Unable to remove NPU Phi blob lock %s during release: %s", self.path, exc)

    def __enter__(self) -> "BlobBuildLock":
        if not self.acquire():
            raise RuntimeError(f"NPU Phi blob build lock already held: {self.path}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
