"""Deterministic character chunking for RAG ingest."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .common import sha256_text


@dataclass(frozen=True)
class ChunkPolicy:
    min_chars: int = 1500
    max_chars: int = 4000
    overlap_chars: int = 300

    def normalized(self) -> "ChunkPolicy":
        max_chars = max(400, int(self.max_chars))
        min_chars = max(1, min(int(self.min_chars), max_chars))
        overlap = max(0, min(int(self.overlap_chars), max_chars // 2))
        return ChunkPolicy(min_chars=min_chars, max_chars=max_chars, overlap_chars=overlap)

    def policy_hash(self) -> str:
        text = json.dumps(self.__dict__, sort_keys=True)
        return sha256_text(text)[:16]


def _break_at_boundary(text: str, start: int, hard_end: int, min_end: int) -> int:
    if hard_end >= len(text):
        return len(text)
    window = text[min_end:hard_end]
    for marker in ("\n\n", "\nclass ", "\ndef ", "\n# ", "\n## "):
        index = window.rfind(marker)
        if index > 0:
            return min_end + index + len(marker)
    return hard_end


def build_chunks(
    *,
    source_path: str,
    text: str,
    content_hash: str,
    policy: ChunkPolicy,
    metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    policy = policy.normalized()
    chunks: list[dict[str, Any]] = []
    cursor = 0
    index = 0
    total = len(text)
    metadata = dict(metadata or {})
    while cursor < total:
        hard_end = min(total, cursor + policy.max_chars)
        min_end = min(total, cursor + policy.min_chars)
        end = _break_at_boundary(text, cursor, hard_end, min_end)
        if end <= cursor:
            end = hard_end
        chunk_text = text[cursor:end]
        text_hash = sha256_text(chunk_text)
        chunk_id = sha256_text(f"{source_path}:{content_hash}:{policy.policy_hash()}:{index}:{text_hash}")[:32]
        chunks.append(
            {
                "chunk_id": chunk_id,
                "source_path": source_path,
                "chunk_index": index,
                "char_start": cursor,
                "char_end": end,
                "text": chunk_text,
                "text_hash": text_hash,
                "content_hash": content_hash,
                "chunk_policy_hash": policy.policy_hash(),
                "metadata": metadata,
            }
        )
        index += 1
        if end >= total:
            break
        cursor = max(end - policy.overlap_chars, cursor + 1)
    return chunks

