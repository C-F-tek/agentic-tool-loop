from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.public_terminal_sanitizer import (  # noqa: E402
    public_terminal_content_key,
    public_terminal_sanitize_text,
    public_terminal_sanitize_value,
)


def test_public_terminal_content_key_preserves_payload_text_fields() -> None:
    for key in ("content", "unified_diff", "stdout_tail", "text"):
        assert public_terminal_content_key(key)
    assert not public_terminal_content_key("summary")


def test_public_terminal_sanitize_text_preserves_content_verbatim() -> None:
    text = r"C:\Users\carmi\AI\agent-jobs\x\file.sqlite"
    assert public_terminal_sanitize_text(text, content=True) == text


def test_public_terminal_sanitize_text_omits_local_paths_and_internal_urls() -> None:
    text = (
        r' artifact=reads/a.json {"document_id":"abc"} '
        r"C:\Users\carmi\AI\qwen-agent-workspace\vulkan-broker\agent-jobs\job "
        r"http://127.0.0.1:3572/jobs/job-x "
        r"tool-results\1.json rag.sqlite"
    )

    cleaned = public_terminal_sanitize_text(text)

    assert "reads/a.json" not in cleaned
    assert "document_id" not in cleaned
    assert "C:\\Users" not in cleaned
    assert "127.0.0.1" not in cleaned
    assert "tool-results\\1.json" not in cleaned
    assert "rag.sqlite" not in cleaned
    assert "[local_path_omitted]" in cleaned
    assert "[local_url_omitted]" in cleaned


def test_public_terminal_sanitize_value_drops_pointer_keys_but_keeps_content() -> None:
    cleaned = public_terminal_sanitize_value({
        "artifact_path": "reads/a.json",
        "document_id": "doc",
        "summary": r"C:\Users\carmi\AI\job",
        "content": r"C:\Users\carmi\AI\visible.txt",
        "items": [{"db_path": "x.sqlite", "text": "real text"}],
    })

    assert cleaned == {
        "summary": "[local_path_omitted]",
        "content": r"C:\Users\carmi\AI\visible.txt",
        "items": [{"text": "real text"}],
    }
