from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    recovery_sec: float = 60.0
    _failures: int = 0
    _opened_at: float | None = None

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if (time.time() - self._opened_at) >= self.recovery_sec:
            return "half_open"
        return "open"

    def allow_request(self) -> bool:
        return self.state in {"closed", "half_open"}

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = time.time()

    def reset(self) -> None:
        self._failures = 0
        self._opened_at = None

    def snapshot(self) -> dict[str, object]:
        return {
            "state": self.state,
            "failures": self._failures,
            "failure_threshold": self.failure_threshold,
            "recovery_sec": self.recovery_sec,
            "opened_at": self._opened_at,
        }
