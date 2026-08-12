"""Text metrics for AI workload quality validation."""
from __future__ import annotations

import string
from typing import Any

from .constants import HEXISH_CHARS

PRINTABLE = set(string.printable)


def text_metrics(text: str) -> dict[str, Any]:
    total = len(text)
    alpha = sum(1 for char in text if char.isalpha())
    digits = sum(1 for char in text if char.isdigit())
    printable = sum(1 for char in text if char in PRINTABLE or char.isprintable())
    hexish = sum(1 for char in text if char in HEXISH_CHARS)
    words = [
        word
        for word in text.replace("`", " ").replace("#", " ").split()
        if any(ch.isalpha() for ch in word)
    ]
    headings = sum(1 for line in text.splitlines() if line.strip().startswith("#"))
    markers = sum(text.count(item) for item in (". ", ":", ";", "\n- ", "\n1."))
    return {
        "chars": total,
        "alpha_chars": alpha,
        "digit_chars": digits,
        "printable_chars": printable,
        "hexish_chars": hexish,
        "word_count": len(words),
        "markdown_heading_count": headings,
        "sentence_marker_count": markers,
        "alpha_ratio": round(alpha / total, 4) if total else 0.0,
        "digit_ratio": round(digits / total, 4) if total else 0.0,
        "hexish_ratio": round(hexish / total, 4) if total else 0.0,
        "printable_ratio": round(printable / total, 4) if total else 0.0,
    }
