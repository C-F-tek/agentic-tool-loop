from __future__ import annotations

from services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


def _preview(value: Any, *, limit: int = 500) -> str:
    try:
        return str(value)[:limit]
    except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}:
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )
        return f"<unstringifiable:{type(exc).__name__}>"


class JsonFileStore:
    """Small JSON file adapter with atomic replace writes."""

    def __init__(
        self,
        *,
        replace_retries: int = 5,
        replace_retry_delay_seconds: float = 0.05,
    ) -> None:
        self._replace_retries = max(0, int(replace_retries))
        self._replace_retry_delay_seconds = max(0.0, float(replace_retry_delay_seconds))

    def read(self, path: Path, default: Any = None) -> Any:
        target = Path(path)
        try:
            raw = target.read_text(encoding="utf-8")
            return json.loads(raw)
        except FileNotFoundError:
            logger.debug("JSON file missing. path=%s", target)
            return default
        except PermissionError:
            logger.warning("Permission denied reading JSON file. path=%s", target)
            return default
        except json.JSONDecodeError as exc:
            logger.debug(
                "Invalid JSON file. path=%s line=%s column=%s error=%s preview=%s",
                target,
                exc.lineno,
                exc.colno,
                _preview(exc.msg, limit=200),
                _preview(raw if "raw" in locals() else ""),
            )
            return default
        except OSError as exc:
            logger.debug("OS error reading JSON file. path=%s error_type=%s", target, type(exc).__name__)
            return default

    def write(self, path: Path, payload: Any) -> Path:
        target = Path(path)
        tmp_path: Path | None = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{target.name}.",
                suffix=".tmp",
                dir=str(target.parent),
                text=True,
            )
            tmp_path = Path(tmp_name)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                try:
                    json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
                except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}:
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )
                    logger.warning(
                        "JSON serialization failed before atomic replace. path=%s payload_type=%s error_type=%s",
                        target,
                        type(payload).__name__,
                        type(exc).__name__,
                    )
                    raise
            last_error: PermissionError | None = None
            for attempt in range(self._replace_retries + 1):
                try:
                    tmp_path.replace(target)
                    last_error = None
                    break
                except PermissionError as exc:
                    last_error = exc
                    if attempt >= self._replace_retries:
                        raise
                    if self._replace_retry_delay_seconds:
                        time.sleep(self._replace_retry_delay_seconds * (attempt + 1))
            if last_error is not None:
                raise last_error
        except PermissionError:
            logger.warning("Permission denied writing JSON file. path=%s", target)
            raise
        except OSError as exc:
            logger.debug("OS error writing JSON file. path=%s error_type=%s", target, type(exc).__name__)
            raise
        finally:
            if tmp_path is not None:
                try:
                    if tmp_path.exists():
                        tmp_path.unlink()
                except PermissionError:
                    logger.warning("Permission denied cleaning temporary JSON file. path=%s", tmp_path)
                except OSError as exc:
                    logger.debug(
                        "OS error cleaning temporary JSON file. path=%s error_type=%s",
                        tmp_path,
                        type(exc).__name__,
                    )
        return target


def same_tool_artifact_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Load the full JSON only for the same successful tool result."""
    if not isinstance(result, dict) or not result.get("ok"):
        return result if isinstance(result, dict) else {}
    artifact = str(result.get("artifact") or "")
    if not artifact:
        return result
    try:
        artifact_path = Path(artifact)
        if not artifact_path.exists():
            logger.debug("Tool artifact JSON missing. artifact=%s", artifact_path)
            return result
        if not artifact_path.is_file():
            logger.debug("Tool artifact path is not a file. artifact=%s", artifact_path)
            return result
        loaded = json.loads(artifact_path.read_text(encoding="utf-8", errors="replace"))
    except PermissionError:
        logger.warning("Permission denied reading tool artifact JSON. artifact=%s", artifact)
        return result
    except json.JSONDecodeError as exc:
        logger.debug(
            "Invalid tool artifact JSON. artifact=%s line=%s column=%s error=%s",
            artifact,
            exc.lineno,
            exc.colno,
            _preview(exc.msg, limit=200),
        )
        return result
    except OSError as exc:
        logger.debug("OS error reading tool artifact JSON. artifact=%s error_type=%s", artifact, type(exc).__name__)
        return result
    if not isinstance(loaded, dict):
        logger.debug("Tool artifact JSON is not an object. artifact=%s loaded_type=%s", artifact, type(loaded).__name__)
        return result
    expected_tool = str(result.get("tool") or "")
    loaded_tool = str(loaded.get("tool") or "")
    if expected_tool and loaded_tool and expected_tool != loaded_tool:
        logger.debug(
            "Tool artifact JSON tool mismatch. artifact=%s expected_tool=%s loaded_tool=%s",
            artifact,
            expected_tool,
            loaded_tool,
        )
        return result
    return loaded
