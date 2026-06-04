from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.text_windows import diff_chunks, window_text  # noqa: E402


def test_window_text_returns_complete_small_text() -> None:
    window = window_text("abc", max_chars=500)

    assert window["complete"] is True
    assert window["text"] == "abc"
    assert window["window_start"] == 0
    assert window["window_end"] == 3
    assert window["sha256"] == window["window_sha256"]


def test_window_text_centers_large_text() -> None:
    text = "a" * 1000 + "CENTER" + "b" * 1000
    window = window_text(text, center="CENTER", max_chars=500)

    assert window["complete"] is False
    assert "CENTER" in window["text"]
    assert window["has_more_before"] is True
    assert window["has_more_after"] is True
    assert window["window_chars"] == len(window["text"])


def test_diff_chunks_split_on_newline_when_possible() -> None:
    text = "\n".join(f"line-{idx}" for idx in range(300))
    chunks = diff_chunks(text, chunk_chars=1000)

    assert len(chunks) > 1
    assert chunks[0]["index"] == 1
    assert chunks[0]["text"].endswith("\n")
    assert chunks[-1]["end"] == len(text)
