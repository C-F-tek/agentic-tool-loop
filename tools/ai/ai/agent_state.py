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
            summary=compact_text(content, 900),
            content=content,
            tags=stable_tag_tuple(tags),
            confidence=clamp_confidence(confidence),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_mapping(cls, payload: Any) -> "MemoryRecord | None":
        """Load a memory record from a mapping, tolerating older shapes."""
        if not isinstance(payload, dict):
            return None
        content = str(payload.get("content") or payload.get("summary") or "")
        source = str(payload.get("source") or payload.get("path") or "unknown")
        kind = str(payload.get("kind") or "memory")
        scope = str(payload.get("scope") or "project")
        tags = payload.get("tags") if isinstance(payload.get("tags"), list) else []
        record_id = str(payload.get("record_id") or sha256_text(f"{kind}:{scope}:{source}:{content}")[:20])
        return cls(
            record_id=record_id,
            kind=kind,
            scope=scope,
            source=source,
            summary=str(payload.get("summary") or compact_text(content, 900)),
            content=content,
            tags=tuple(str(tag) for tag in tags),
            confidence=clamp_confidence(payload.get("confidence", 1.0)),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=payload.get("updated_at"),
            expires_at=payload.get("expires_at"),
            metadata=dict(payload.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        data = asdict(self)
        data["tags"] = list(self.tags)
        return data


@dataclass(frozen=True)
class AgentMicroTask:
    """A planned unit of work for an app or specialized agent lane."""

    task_id: str
    title: str
    lane: str
    purpose: str
    priority: int = 5
    blocking: bool = False
    status: str = "planned"
    inputs: tuple[str, ...] = ()
    expected_outputs: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        data = asdict(self)
        data["inputs"] = list(self.inputs)
        data["expected_outputs"] = list(self.expected_outputs)
        data["depends_on"] = list(self.depends_on)
        return data


def load_memory_jsonl(path: Path) -> list[MemoryRecord]:
    """Load persistent memory records from JSONL."""
    if not path.exists():
        return []
    records: list[MemoryRecord] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            record = MemoryRecord.from_mapping(json.loads(line))
        except json.JSONDecodeError:
            record = None
        if record is not None:
            records.append(record)
    return records


def append_memory_jsonl(path: Path, record: MemoryRecord) -> None:
    """Append one persistent memory record to JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


def ensure_memory_db(path: Path) -> None:
    """Create or upgrade a lightweight SQLite memory database."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_records (
                record_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                scope TEXT NOT NULL,
                source TEXT NOT NULL,
                summary TEXT NOT NULL,
                content TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                expires_at TEXT,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_kind ON memory_records(kind)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_scope ON memory_records(scope)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_source ON memory_records(source)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO memory_meta(key, value) VALUES('schema_version', ?)",
            (str(MEMORY_DB_SCHEMA_VERSION),),
        )


def upsert_memory_db(path: Path, records: Iterable[MemoryRecord]) -> int:
    """Insert or update records in the SQLite memory database."""
    ensure_memory_db(path)
    count = 0
    with sqlite3.connect(path) as conn:
        for record in records:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_records (
                    record_id, kind, scope, source, summary, content, tags_json,
                    confidence, created_at, updated_at, expires_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    record.kind,
                    record.scope,
                    record.source,
                    record.summary,
                    record.content,
                    json.dumps(list(record.tags), ensure_ascii=False),
                    record.confidence,
                    record.created_at,
                    record.updated_at,
                    record.expires_at,
                    json.dumps(record.metadata, ensure_ascii=False),
                ),
            )
            count += 1
    return count


def load_memory_db(path: Path, *, limit: int = 1000) -> list[MemoryRecord]:
    """Load records from the SQLite memory database."""
    if not path.exists():
        return []
    records: list[MemoryRecord] = []
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            """
            SELECT record_id, kind, scope, source, summary, content, tags_json,
                   confidence, created_at, updated_at, expires_at, metadata_json
            FROM memory_records
            ORDER BY COALESCE(updated_at, created_at) DESC
            LIMIT ?
            """,
            (int(limit),),
        ):
            tags = json_or_default(row["tags_json"], [])
            metadata = json_or_default(row["metadata_json"], {})
            records.append(
                MemoryRecord(
                    record_id=row["record_id"],
                    kind=row["kind"],
                    scope=row["scope"],
                    source=row["source"],
                    summary=row["summary"],
                    content=row["content"],
                    tags=tuple(str(tag) for tag in tags if str(tag).strip()),
                    confidence=float(row["confidence"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    expires_at=row["expires_at"],
                    metadata=dict(metadata),
                )
            )
    return records


def records_from_files(paths: Iterable[Path], repo_root: Path, max_record_chars: int) -> list[MemoryRecord]:
    """Create file-backed memory records for included source files."""
    records: list[MemoryRecord] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        rel = relative_path(path, repo_root)
        text = read_text(path)
        tags = ("source_file", path.suffix.lower().lstrip(".") or "text")
        records.append(
            MemoryRecord.from_text(
                kind="source_file",
                scope="project",
                source=rel,
                text=text,
                tags=tags,
                max_record_chars=max_record_chars,
                metadata={
                    "path": rel,
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_text(text),
                },
            )
        )
    return records


def score_record(record: MemoryRecord, objective: str) -> float:
    """Score a memory record against the current objective."""
    objective_terms = set(keywords(objective, 80))
    record_terms = set(record.tags) | set(keywords(record.summary + " " + record.source, 80))
    overlap = len(objective_terms & record_terms)
    tag_bonus = 0.7 if {"guardrail", "memory", "pipeline", "blender", "audio"} & set(record.tags) else 0.0
    return round(overlap * 4.0 + record.confidence * 2.0 + tag_bonus, 4)


def select_memory(records: Iterable[MemoryRecord], objective: str, max_chars: int) -> list[dict[str, Any]]:
    """Rank and select memory records under a character budget."""
    ranked = sorted(records, key=lambda item: score_record(item, objective), reverse=True)
    selected: list[dict[str, Any]] = []
    used = 0
    for record in ranked:
        cost = len(record.content) + 320
        if selected and used + cost > max_chars:
            continue
        payload = record.to_dict()
        payload["rank_score"] = score_record(record, objective)
        selected.append(payload)
        used += cost
        if used >= max_chars:
            break
    return selected


def default_microtasks(objective: str, selected_memory: list[dict[str, Any]]) -> list[AgentMicroTask]:
    """Create a generic first-pass microtask graph."""
    source_paths = tuple(str(item.get("source")) for item in selected_memory if item.get("source"))
    objective_slug = slugify(objective, "objective")[:48]
    return [
        AgentMicroTask(
            task_id=f"{objective_slug}_context_read",
            title="Read selected context and constraints",
            lane="CPU",
            purpose="Build the immediate working context without loading unrelated files.",
            priority=9,
            blocking=True,
            inputs=source_paths,
            expected_outputs=("agent_state_packet.json",),
        ),
        AgentMicroTask(
            task_id=f"{objective_slug}_npu_guardrail",
            title="Run non-blocking NPU-light guardrail",
            lane="NPU",
            purpose="Score packet risks, missing assumptions, stale context and blocked patterns.",
            priority=8,
            blocking=False,
            inputs=("agent_state_packet.json",),
            expected_outputs=("agent_guardrail_report.json", "agent_guardrail_action_queue.json"),
            depends_on=(f"{objective_slug}_context_read",),
            metadata={"soft_fail": True, "recommended_workers_max": 4},
        ),
        AgentMicroTask(
            task_id=f"{objective_slug}_gpu_optional_planner",
            title="Optional GPU heavy planning lane",
            lane="GPU",
            purpose="Use only when explicitly requested or app policy allows heavy generation.",
            priority=4,
            blocking=False,
            status="opt_in_required",
            inputs=("agent_state_packet.json",),
            expected_outputs=("gpu_planner_output.json",),
            depends_on=(f"{objective_slug}_context_read",),
            metadata={"heavy": True, "do_not_run_with_heavy_blender_render": True},
        ),
        AgentMicroTask(
            task_id=f"{objective_slug}_validate",
            title="Validate artifacts and update memory",
            lane="VALIDATION",
            purpose="Run focused validators, summarize results and append durable lessons.",
            priority=9,
            blocking=True,
            inputs=("agent_state_packet.json", "agent_guardrail_report.json"),
            expected_outputs=("validation_report.json", "persistent_memory.jsonl"),
            depends_on=(f"{objective_slug}_context_read",),
        ),
    ]


def build_agent_state_packet(
    *,
    repo_root: Path,
    objective: str,
    records: Iterable[MemoryRecord],
    max_memory_chars: int = DEFAULT_MAX_MEMORY_CHARS,
    packet_name: str = "agent_state_packet",
) -> dict[str, Any]:
    """Build a task-specific agent state packet."""
    record_list = list(records)
    selected = select_memory(record_list, objective, max_memory_chars)
    microtasks = default_microtasks(objective, selected)
    manifest = [
        {
            "record_id": item.record_id,
            "kind": item.kind,
            "scope": item.scope,
            "source": item.source,
            "tags": list(item.tags),
            "confidence": item.confidence,
            "rank_score": score_record(item, objective),
        }
        for item in record_list
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "agent_state_packet",
        "packet_name": packet_name,
        "generated_at": utc_now_iso(),
        "repo_root": str(repo_root),
        "objective": objective,
        "policy": {
            "token_strategy": "Select ranked memory records under budget; expand by source path or record_id only when needed.",
            "recent_memory": "Use included files and conversation-derived records for the immediate task.",
            "persistent_memory": "Use JSONL records for durable constraints, known fixes and prior validation results.",
            "hardware_lanes": "CPU is deterministic orchestration, NPU is non-blocking light review, GPU is explicit opt-in heavy generation.",
            "runtime_safety": "This packet does not execute Blender, GPU, NPU, FFmpeg or source-code modifications.",
        },
        "budgets": {
            "max_memory_chars": max_memory_chars,
            "selected_memory_chars": sum(len(str(item.get("content") or "")) for item in selected),
        },
        "selected_memory": selected,
        "memory_manifest": sorted(manifest, key=lambda item: item["rank_score"], reverse=True),
        "microtasks": [item.to_dict() for item in microtasks],
        "assumptions": [
            "Operational self-awareness means structured state, constraints, memory and validation status.",
            "Hardware lanes are declared as planned work only; execution is controlled by the app or pipeline policy.",
            "Future file types should be represented as memory records with kind, scope, source, tags and metadata.",
        ],
    }


def write_agent_state_markdown(packet: dict[str, Any], path: Path) -> None:
    """Write a compact Markdown companion for human review."""
    lines = [
        "# Agent State Packet",
        "",
        f"Generated: `{packet.get('generated_at')}`",
        f"Objective: `{packet.get('objective')}`",
        "",
        "## Selected Memory",
    ]
    for item in packet.get("selected_memory", []):
        lines.extend(
            [
                "",
                f"### {item.get('record_id')} - {item.get('source')}",
                f"- Kind: `{item.get('kind')}`",
                f"- Tags: `{', '.join(item.get('tags') or [])}`",
                f"- Score: `{item.get('rank_score')}`",
                "",
                str(item.get("summary") or ""),
            ]
        )
    lines.extend(["", "## Microtasks"])
    for item in packet.get("microtasks", []):
        lines.append(
            f"- `{item.get('task_id')}` [{item.get('lane')}] blocking={item.get('blocking')} status={item.get('status')}: {item.get('purpose')}"
        )
    lines.extend(["", "## Policy"])
    for key, value in (packet.get("policy") or {}).items():
        lines.append(f"- `{key}`: {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
