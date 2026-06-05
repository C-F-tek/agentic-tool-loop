from __future__ import annotations

import json
import os
import time
from pathlib import Path


class BlobBuildLock:
    def __init__(self, path: Path, *, stale_after_s: int = 1200) -> None:
        self.path = path
        self.stale_after_s = stale_after_s
        self._fd: int | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            age = time.time() - self.path.stat().st_mtime
            if age > self.stale_after_s:
                self.path.unlink(missing_ok=True)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            self._fd = os.open(str(self.path), flags)
        except FileExistsError:
            return False
        payload = {"pid": os.getpid(), "ts": time.time()}
        os.write(self._fd, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        return True

    def release(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        self.path.unlink(missing_ok=True)

    def __enter__(self) -> "BlobBuildLock":
        if not self.acquire():
            raise RuntimeError(f"NPU Phi blob build lock already held: {self.path}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
