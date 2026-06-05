from __future__ import annotations

import time


class TimeProvider:
    """Time boundary for job lifecycle tests."""

    def time(self) -> float:
        return time.time()

    def now_seconds(self) -> int:
        return int(self.time())
