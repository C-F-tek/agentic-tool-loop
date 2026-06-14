from __future__ import annotations

import logging
import time


logger = logging.getLogger(__name__)


class TimeProvider:
    """Time boundary for job lifecycle tests."""

    def time(self) -> float:
        try:
            return time.time()
        except (OSError, OverflowError) as exc:
            logger.warning("Failed to read system time. error_type=%s", type(exc).__name__)
            raise

    def now_seconds(self) -> int:
        try:
            return int(self.time())
        except (TypeError, ValueError, OverflowError) as exc:
            logger.warning("Failed to convert system time to seconds. error_type=%s", type(exc).__name__)
            raise
