"""Chunk summary generation."""

from __future__ import annotations

import time
from typing import Any

from ia_carmine.providers.ollama.sdk_client import OllamaSdkClient, OllamaSdkError

from .common import compact_text

def deterministic_summary(text: str, titles: list[str]) -> str:
    title_part = "; ".join(titles[:5]) if titles else "no explicit section title"
    preview = compact_text(text, 260)
    return f"Chunk deterministico. Sezioni: {title_part}. Preview: {preview}"

def call_ollama_summary(
    *,
    host: str,
    model: str,
    text: str,
    titles: list[str],
    timeout: int,
    max_input_chars: int,
    keep_alive: str,
) -> tuple[str | None, str | None, float]:
    prompt = (
        "Sei un summarizer locale per evidence bundle tecnici. "
        "Riassumi questo chunk in italiano tecnico in massimo 5 righe. "
        "Indica: scopo, segnali principali, eventuali guardrail o errori, perché serve a una AI cloud. "
        "Non inventare.\n\n"
        f"Titoli sezioni: {titles[:8]}\n\n"
        f"Chunk:\n{text[:max_input_chars]}"
    )
    started = time.perf_counter()
    try:
        text_out = OllamaSdkClient(host).generate(
            model=model,
            prompt=prompt,
            keep_alive=keep_alive,
            temperature=0.1,
            num_predict=220,
            num_thread=None,
            num_ctx=None,
        )
    except (OllamaSdkError, TimeoutError, OSError) as exc:
        return None, str(exc), round(time.perf_counter() - started, 3)
    elapsed = round(time.perf_counter() - started, 3)
    text_out = str(text_out or "").strip()
    if not text_out:
        return None, "empty ollama response", elapsed
    return text_out, None, elapsed
