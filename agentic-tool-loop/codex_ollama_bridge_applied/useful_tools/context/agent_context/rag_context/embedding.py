"""Ollama embedding client and vector helpers."""

from __future__ import annotations

import json
import math
import struct
import time
import urllib.error
import urllib.request
from typing import Any


CHAT_MODEL_MARKERS = ("coder", "chat", "instruct", "llama", "mistral", "qwen")


def embedding_model_error(model: str) -> str:
    lowered = str(model or "").lower()
    if not lowered:
        return "embedding model is required"
    if lowered == "bge-m3" or "embed" in lowered or "bge" in lowered:
        return ""
    if any(marker in lowered for marker in CHAT_MODEL_MARKERS):
        return f"chat/coder model is not allowed as embedding model: {model}"
    return ""


def validate_vector(vector: list[Any]) -> tuple[list[float], float, str]:
    values: list[float] = []
    for item in vector:
        try:
            value = float(item)
        except (TypeError, ValueError):
            return [], 0.0, "embedding contains non-numeric value"
        if not math.isfinite(value):
            return [], 0.0, "embedding contains non-finite value"
        values.append(value)
    norm = math.sqrt(sum(value * value for value in values))
    if not values:
        return [], 0.0, "embedding is empty"
    if norm <= 0:
        return [], 0.0, "embedding norm is zero"
    return values, norm, ""


def pack_vector(vector: list[float]) -> bytes:
    return struct.pack("<" + "f" * len(vector), *vector)


def unpack_vector(blob: bytes, dimension: int) -> list[float]:
    if dimension <= 0:
        return []
    return list(struct.unpack("<" + "f" * dimension, blob))


def cosine_from_norms(a: list[float], a_norm: float, b: list[float], b_norm: float) -> float:
    if not a or not b or a_norm <= 0 or b_norm <= 0 or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (a_norm * b_norm)


def _endpoint_url(endpoint: str) -> str:
    base = endpoint.rstrip("/")
    return base if base.endswith("/api/embed") else f"{base}/api/embed"


def embed_batch(
    *,
    endpoint: str,
    model: str,
    texts: list[str],
    timeout_seconds: float = 60.0,
    retries: int = 1,
) -> tuple[list[list[float]], list[str]]:
    errors: list[str] = []
    model_error = embedding_model_error(model)
    if model_error:
        return [], [model_error]
    payload = json.dumps({"model": model, "input": texts}).encode("utf-8")
    request = urllib.request.Request(
        _endpoint_url(endpoint),
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    last_error = ""
    for attempt in range(max(1, retries + 1)):
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
            raw = data.get("embeddings")
            if not isinstance(raw, list):
                return [], ["Ollama /api/embed response missing embeddings list"]
            vectors: list[list[float]] = []
            for index, item in enumerate(raw):
                values, _norm, error = validate_vector(item if isinstance(item, list) else [])
                if error:
                    return [], [f"embedding[{index}]: {error}"]
                vectors.append(values)
            if len(vectors) != len(texts):
                return [], [f"embedding count mismatch: got {len(vectors)}, expected {len(texts)}"]
            return vectors, []
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(0.2 * (attempt + 1))
    errors.append(last_error or "embedding request failed")
    return [], errors

