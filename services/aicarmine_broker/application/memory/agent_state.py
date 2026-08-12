#!/usr/bin/env python3
"""Generic agent memory and microtask packet helpers.

This module is intentionally pure Python and non-invasive. It does not launch
models, Blender, FFmpeg, NPU or GPU work. It creates structured packets that an
app, agent, or later pipeline stage can consume.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
DEFAULT_MAX_MEMORY_CHARS = 24000
DEFAULT_MAX_RECORD_CHARS = 4200
MEMORY_DB_SCHEMA_VERSION = 1

WORD_RE = re.compile(r"[A-Za-z0-9_]{3,}")
STOP_WORDS = {
    "and",
    "are",
    "but",
    "con",
    "del",
    "dei",
    "della",
    "delle",
    "for",
    "from",
    "gli",
    "json",
    "non",
    "not",
    "per",
    "the",
    "una",
    "uno",
    "with",
}


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def sha256_text(text: str) -> str:
    """Return the SHA-256 hash for text."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def clamp_confidence(value: Any) -> float:
    """Return confidence bounded to the supported 0.0-1.0 interval."""
    return max(0.0, min(1.0, float(value)))


def stable_tag_tuple(tags: Iterable[Any]) -> tuple[str, ...]:
    """Return non-empty tags while preserving first-seen order."""
    return tuple(dict.fromkeys(str(tag) for tag in tags if str(tag).strip()))


def json_or_default(raw: str, default: Any) -> Any:
    """Parse a JSON field, returning the fallback for malformed payloads."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def compact_text(text: str, limit: int = 900) -> str:
    """Collapse whitespace and trim text to a predictable size."""
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)].rstrip() + "..."


def slugify(value: str, fallback: str = "agent_state") -> str:
    """Return a filesystem-friendly slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return re.sub(r"_+", "_", slug) or fallback


def keywords(text: str, limit: int = 32) -> tuple[str, ...]:
    """Extract simple deterministic keywords for local ranking."""
    counts: dict[str, int] = {}
    for match in WORD_RE.finditer(text.lower()):
        word = match.group(0)
        if word in STOP_WORDS or word.isdigit():
            continue
        counts[word] = counts.get(word, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return tuple(word for word, _count in ranked[:limit])


def read_text(path: Path, limit: int = 240000) -> str:
    """Read text defensively for packet construction."""
    return path.read_text(encoding="utf-8", errors="replace")[:limit]


def relative_path(path: Path, repo_root: Path) -> str:
    """Return a stable repository-relative path where possible."""
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path)


@dataclass(frozen=True)
class MemoryRecord:
    """A generic memory item selected into an agent state packet."""

    record_id: str
    kind: str
    scope: str
    source: str
    summary: str
    content: str
    tags: tuple[str, ...] = ()
    confidence: float = 1.0
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str | None = None
    expires_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_text(
        cls,
        *,
        kind: str,
        scope: str,
        source: str,
        text: str,
        tags: Iterable[str] = (),
        confidence: float = 1.0,
        max_record_chars: int = DEFAULT_MAX_RECORD_CHARS,
        metadata: dict[str, Any] | None = None,
    ) -> "MemoryRecord":
        """Create a memory record from raw text."""
        content = text[:max_record_chars].rstrip()
        identity = f"{kind}:{scope}:{source}:{sha256_text(content)[:16]}"
        return cls(
            record_id=sha256_text(identity)[:20],
            kind=kind,
            scope=scope,
            source=source,
            summary=compact_text(text, 900),
            content=content,
            tags=tuple(str(t).strip() for t in tags if str(t).strip()),
            confidence=clamp_confidence(confidence),
            metadata=metadata or {},
        )

    @classmethod
    def from_json(cls, raw: str) -> "MemoryRecord":
        """Parse a JSON string into a MemoryRecord."""
        data = json_or_default(raw, {})
        if not isinstance(data, dict):
            raise ValueError("malformed JSON")
        tags_raw = data.get("tags", [])
        tags = tuple(str(t).strip() for t in tags_raw if str(t).strip())
        return cls(
            record_id=str(data.get("record_id", ""))[:40],
            kind=str(data.get("kind", "memory"))[:40],
            scope=str(data.get("scope", "repo"))[:40],
            source=str(data.get("source", ""))[:200],
            summary=str(data.get("summary", ""))[:1500],
            content=str(data.get("content", ""))[:DEFAULT_MAX_RECORD_CHARS],
            tags=tags,
            confidence=clamp_confidence(data.get("confidence", 1.0)),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at")) if data.get("updated_at") else None,
            expires_at=str(data.get("expires_at")) if data.get("expires_at") else None,
            metadata=data.get("metadata", {}),
        )


def load_memory_jsonl(path: Path) -> list[MemoryRecord]:
    """Load MemoryRecord items from a JSONL file."""
    records: list[MemoryRecord] = []
    if not path.exists() or not path.is_file():
        return records
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(cls.from_json(line))
        except Exception:
            continue
    return records


def _connect_db(db_path: Path) -> sqlite3.Connection:
    """Open a read-only SQLite connection with row factory."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def load_memory_db(
    db_path: Path,
    limit: int = 1000,
) -> list[MemoryRecord]:
    """Load memory records from an SQLite database file."""
    if not db_path.exists() or not db_path.is_file():
        return []
    conn = _connect_db(db_path)
    try:
        cursor = conn.execute(
            "SELECT record_id, kind, scope, source, summary, content, tags, confidence, created_at, updated_at, expires_at, metadata FROM agent_memory LIMIT ?",
            (int(limit),),
        )
        records: list[MemoryRecord] = []
        for row in cursor:
            raw = {
                "record_id": row[0],
                "kind": row[1],
                "scope": row[2],
                "source": row[3],
                "summary": row[4],
                "content": row[5],
                "tags": row[6],
                "confidence": row[7],
                "created_at": row[8],
                "updated_at": row[9],
                "expires_at": row[10],
                "metadata": row[11],
            }
            try:
                records.append(cls.from_json(json.dumps(raw)))
            except Exception:
                continue
        return records
    except Exception:
        return []
    finally:
        conn.close()


def build_state_packet(
    *,
    objective: str,
    memory_records: list[MemoryRecord],
    repo_root: Path,
    max_chars: int = DEFAULT_MAX_MEMORY_CHARS,
) -> dict[str, Any]:
    """Build a compact state packet from memory records."""
    sorted_records = sorted(memory_records, key=lambda r: (-r.confidence, r.created_at))
    selected: list[dict[str, Any]] = []
    used = 0
    for record in sorted_records:
        chunk = {
            "record_id": record.record_id,
            "kind": record.kind,
            "scope": record.scope,
            "source": relative_path(Path(record.source), repo_root) if record.source else record.source,
            "summary": record.summary,
            "content": record.content,
            "tags": list(record.tags),
            "confidence": record.confidence,
        }
        chunk_text = json.dumps(chunk, ensure_ascii=False)
        if used + len(chunk_text) > max_chars:
            break
        selected.append(chunk)
        used += len(chunk_text)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "agent_state_packet",
        "objective": objective,
        "generated_at": utc_now_iso(),
        "max_chars": max_chars,
        "used_chars": used,
        "record_count": len(selected),
        "records": selected,
    }


def build_keywords_index(
    records: list[MemoryRecord],
    limit: int = 32,
) -> dict[str, tuple[str, ...]]:
    """Build a simple keyword index for local ranking."""
    index: dict[str, tuple[str, ...]] = {}
    for record in records:
        text = f"{record.kind} {record.scope} {record.source} {record.summary} {record.content}"
        index[record.record_id] = keywords(text, limit)
    return index


def select_memory(
    records: list[MemoryRecord],
    *,
    objective: str,
    kind_filter: str | None = None,
    scope_filter: str | None = None,
    tag_filter: str | None = None,
    min_confidence: float = 0.0,
    limit: int = 100,
) -> list[MemoryRecord]:
    """Select and rank memory records against an objective."""
    filtered: list[MemoryRecord] = []
    for record in records:
        if kind_filter and record.kind != kind_filter:
            continue
        if scope_filter and record.scope != scope_filter:
            continue
        if tag_filter and tag_filter not in record.tags:
            continue
        if record.confidence < min_confidence:
            continue
        filtered.append(record)
    keywords_obj = keywords(objective, limit=64)
    scored: list[tuple[int, str, MemoryRecord]] = []
    for record in filtered:
        score = 0
        if record.kind in keywords_obj:
            score += 10
        if record.scope in keywords_obj:
            score += 8
        for tag in record.tags:
            if tag.lower() in keywords_obj:
                score += 5
        if record.summary:
            for kw in keywords_obj:
                if kw in record.summary.lower():
                    score += 3
        if record.content:
            for kw in keywords_obj:
                if kw in record.content.lower():
                    score += 2
        scored.append((score, record.record_id, record))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [r for _, _, r in scored[:limit]]


def build_memory_index_jsonl(
    records: list[MemoryRecord],
    output_path: Path,
) -> None:
    """Write one JSONL file with all memory records."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for record in records:
        lines.append(json.dumps(record.__dict__, ensure_ascii=False))
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_tags(raw: Any) -> tuple[str, ...]:
    """Parse tags from various formats into a stable tuple."""
    if isinstance(raw, (list, tuple)):
        return tuple(str(t).strip() for t in raw if str(t).strip())
    if isinstance(raw, str):
        return tuple(str(t).strip() for t in raw.split(",") if str(t).strip())
    return ()


def build_memory_delta(
    old_records: list[MemoryRecord],
    new_records: list[MemoryRecord],
) -> dict[str, Any]:
    """Compute delta between two sets of memory records."""
    old_ids = {r.record_id for r in old_records}
    new_ids = {r.record_id for r in new_records}
    added = sorted(new_ids - old_ids)
    removed = sorted(old_ids - new_ids)
    unchanged = sorted(old_ids & new_ids)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "memory_delta",
        "added": added,
        "removed": removed,
        "unchanged": unchanged,
        "added_count": len(added),
        "removed_count": len(removed),
        "unchanged_count": len(unchanged),
    }