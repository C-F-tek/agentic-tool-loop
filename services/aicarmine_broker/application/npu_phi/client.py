from __future__ import annotations

from aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from aicarmine_broker.config.env_loader import EnvMapping, env_bool, env_float, env_str


HttpPost = Callable[[str, dict[str, Any], float], dict[str, Any]]
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NpuPhiClientConfig:
    enabled: bool
    base_url: str = "http://127.0.0.1:3551"
    mode: str = "best_effort"
    timeout_s: float = 1.0

    @classmethod
    def from_env(cls, env: EnvMapping | None = None) -> "NpuPhiClientConfig":
        return cls(
            enabled=env_bool("ENABLE_NPU_PHI_BROKER_DIAGNOSTICS", False, env),
            base_url=env_str("NPU_PHI_BASE_URL", "http://127.0.0.1:3551", env).rstrip("/"),
            mode=env_str("NPU_PHI_BROKER_MODE", "best_effort", env),
            timeout_s=max(0.5, env_float("NPU_PHI_CLIENT_TIMEOUT_SEC", 1.0, env)),
        )


def _httpx_post(url: str, payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    timeout = httpx.Timeout(timeout_s, connect=min(timeout_s, 0.5))
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("NPU Phi response is not a JSON object")
        return data


def enqueue_scene_spec_best_effort(
    *,
    goal: str,
    evidence_hash: str = "",
    prompt: str | None = None,
    json_schema: dict[str, Any] | None = None,
    config: NpuPhiClientConfig | None = None,
    http_post: HttpPost | None = None,
) -> dict[str, Any]:
    resolved = config or NpuPhiClientConfig.from_env()
    start = time.perf_counter()
    base = {
        "schema": "npu_phi_broker_enqueue_attempt.v1",
        "attempted": False,
        "enabled": resolved.enabled,
        "mode": resolved.mode,
        "base_url": resolved.base_url,
        "timeout_s": resolved.timeout_s,
        "elapsed_ms": 0,
    }
    if not resolved.enabled:
        return {**base, "status": "disabled"}
    if resolved.mode != "best_effort":
        return {
            **base,
            "attempted": False,
            "status": "unsupported_mode",
            "error": "NPU Phi broker diagnostics currently supports only best_effort mode.",
        }
    payload: dict[str, Any] = {
        "goal": goal,
        "evidence_hash": evidence_hash,
    }
    if prompt:
        payload["prompt"] = prompt
    if json_schema is not None:
        payload["json_schema"] = json_schema
    try:
        post = http_post or _httpx_post
        response = post(f"{resolved.base_url}/v1/jobs/scene-spec", payload, resolved.timeout_s)
        if not isinstance(response, dict):
            raise ValueError("NPU Phi response is not a JSON object")
    except httpx.TimeoutException as exc:
        logger.warning(
            "NPU Phi broker call timed out after %.3fs error_type=%s",
            resolved.timeout_s,
            type(exc).__name__,
        )
        return {
            **base,
            "attempted": True,
            "status": "timeout",
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
            "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
        }
    except httpx.HTTPStatusError as exc:
        response_preview = ""
        status_code = None
        reason = ""
        if exc.response is not None:
            status_code = exc.response.status_code
            reason = exc.response.reason_phrase
            response_preview = exc.response.text[:500]
        return {
            **base,
            "attempted": True,
            "status": "http_error",
            "ok": False,
            "error_type": type(exc).__name__,
            "http_status": status_code,
            "http_reason": reason,
            "response_preview": response_preview,
            "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
        }
    except httpx.RequestError as exc:
        return {
            **base,
            "attempted": True,
            "status": "network_error",
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
            "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
        }
    except json.JSONDecodeError as exc:
        return {
            **base,
            "attempted": True,
            "status": "invalid_json",
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
            "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
        }
    except ValueError as exc:
        return {
            **base,
            "attempted": True,
            "status": "response_shape_error",
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
            "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
        }
    except Exception as exc:
        return {
            **base,
            "attempted": True,
            "status": "enqueue_failed",
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
            "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
        }
    return {
        **base,
        "attempted": True,
        "status": "enqueue_returned",
        "ok": bool(response.get("accepted")),
        "accepted": bool(response.get("accepted")),
        "job_id": response.get("job_id"),
        "dedup_key": response.get("dedup_key"),
        "queue_depth": response.get("queue_depth"),
        "reason": response.get("reason", ""),
        "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
    }
