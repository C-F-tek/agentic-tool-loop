#!/usr/bin/env python3
"""Retention, review and promotion policy for generic agent memory records.

The policy is intentionally local and deterministic. It never deletes memory
records or promotes them into documentation by itself; it only produces review
reports and promotion candidates for humans or higher-level app workflows.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:  # Support both direct script execution and namespace-package imports.
    from .agent_state import MemoryRecord, compact_text, load_memory_db, load_memory_jsonl, sha256_text, utc_now_iso
except ImportError:  # pragma: no cover - direct execution fallback.
    from .agent_state import MemoryRecord, compact_text, load_memory_db, load_memory_jsonl, sha256_text, utc_now_iso


POLICY_SCHEMA_VERSION = 1

DEFAULT_RETENTION_POLICY: dict[str, Any] = {
    "schema_version": POLICY_SCHEMA_VERSION,
    "max_records_per_scope": 500,
    "max_content_chars": 4200,
    "review_after_days": {
        "operator_note": 14,
        "task_summary": 30,
        "validation_result": 45,
        "source_file": 30,
        "durable_constraint": 180,
        "memory": 45,
    },
    "expire_after_days": {
        "operator_note": 60,
        "task_summary": 180,
        "validation_result": 180,
        "source_file": 90,
        "durable_constraint": 365,
        "memory": 120,
    },
    "promotion_tags": [
        "architecture",
        "audio",
        "blender",
        "durable",
        "guardrail",
        "retention_candidate",
        "validated",
    ],
    "promotable_kinds": [
        "durable_constraint",
        "task_summary",
        "validation_result",
    ],
    "protected_tags": [
        "pinned",
        "project_contract",
    ],
    "blocked_secret_patterns": [
        r"(?i)\b(api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*\S+",
        r"(?i)\bsk-[A-Za-z0-9_\-]{16,}\b",
        r"(?i)\bghp_[A-Za-z0-9_]{20,}\b",
        r"(?i)\baws_access_key_id\b\s*[:=]\s*\S+",
        r"(?i)\baws_secret_access_key\b\s*[:=]\s*\S+",
    ],
}


@dataclass(frozen=True)
class MemoryReview:
    """Review decision for one memory record."""

    record_id: str
    kind: str
    scope: str
    source: str
    tags: tuple[str, ...]
    age_days: int | None
    content_chars: int
    confidence: float
    action: str
    promotion_candidate: bool
    promotion_reason: str | None
    issues: tuple[str, ...]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tags"] = list(self.tags)
        data["issues"] = list(self.issues)
        return data


def parse_datetime(value: str | None) -> datetime | None:
    """Parse an ISO timestamp and normalize it to UTC."""
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def days_since(value: str | None, now: datetime) -> int | None:
    """Return elapsed full days from an ISO timestamp."""
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    return max(0, int((now - parsed).total_seconds() // 86400))


def kind_threshold(policy: dict[str, Any], section: str, kind: str) -> int:
    """Return a threshold for a record kind with fallback to `memory`."""
    table = policy.get(section) if isinstance(policy.get(section), dict) else {}
    return int(table.get(kind, table.get("memory", 45)))


def detect_secret_patterns(record: MemoryRecord, policy: dict[str, Any]) -> list[str]:
    """Return blocked secret-pattern labels detected in record text."""
    haystack = "\n".join([record.source, record.summary, record.content])
    matches: list[str] = []
    for pattern in policy.get("blocked_secret_patterns", []):
        if re.search(str(pattern), haystack):
            matches.append("blocked_secret_pattern")
    return matches


def promotion_reason(record: MemoryRecord, policy: dict[str, Any]) -> str | None:
    """Return a reason when a record is eligible for manual promotion."""
    tags = {tag.lower() for tag in record.tags}
    promotion_tags = {str(tag).lower() for tag in policy.get("promotion_tags", [])}
    promotable_kinds = {str(kind) for kind in policy.get("promotable_kinds", [])}
    if record.kind in promotable_kinds:
        return f"kind:{record.kind}"
    matched = sorted(tags & promotion_tags)
    if matched and "recent" not in tags:
        return f"tag:{matched[0]}"
    return None


def review_record(record: MemoryRecord, now: datetime, policy: dict[str, Any] | None = None) -> MemoryReview:
    """Evaluate one memory record against retention and promotion policy."""
    active_policy = dict(DEFAULT_RETENTION_POLICY)
    if policy:
        active_policy.update(policy)

    issues: list[str] = []
    tags = tuple(tag.lower() for tag in record.tags)
    tag_set = set(tags)
    age_days = days_since(record.updated_at or record.created_at, now)
    expires_at = parse_datetime(record.expires_at)
    review_after = kind_threshold(active_policy, "review_after_days", record.kind)
    expire_after = kind_threshold(active_policy, "expire_after_days", record.kind)
    protected = bool(tag_set & {str(tag).lower() for tag in active_policy.get("protected_tags", [])})

    if record.confidence < 0.5:
        issues.append("low_confidence")
    if len(record.content) > int(active_policy.get("max_content_chars", 4200)):
        issues.append("oversized_content")
    if not record.content.strip():
        issues.append("empty_content")
    issues.extend(detect_secret_patterns(record, active_policy))
    if expires_at is not None and expires_at <= now:
        issues.append("explicitly_expired")
    if age_days is None:
        issues.append("missing_or_invalid_timestamp")
    elif age_days >= expire_after and not protected:
        issues.append("stale_by_age")
    elif age_days >= review_after:
        issues.append("review_due")

    reason = promotion_reason(record, active_policy)
    has_blocker = any(issue in {"blocked_secret_pattern", "empty_content", "explicitly_expired", "stale_by_age"} for issue in issues)
    candidate = bool(reason and not has_blocker and record.confidence >= 0.75)

    if "blocked_secret_pattern" in issues:
        action = "quarantine"
    elif "explicitly_expired" in issues or "stale_by_age" in issues:
        action = "expire_review"
    elif "oversized_content" in issues:
        action = "trim_review"
    elif "review_due" in issues or "low_confidence" in issues:
        action = "human_review"
    elif candidate:
        action = "promote_candidate"
    else:
        action = "keep"

    return MemoryReview(
        record_id=record.record_id,
        kind=record.kind,
        scope=record.scope,
        source=record.source,
        tags=tags,
        age_days=age_days,
        content_chars=len(record.content),
        confidence=record.confidence,
        action=action,
        promotion_candidate=candidate,
        promotion_reason=reason,
        issues=tuple(dict.fromkeys(issues)),
        summary=compact_text(record.summary or record.content, 500),
    )


def load_records(memory_jsonl: Iterable[Path] = (), memory_db: Path | None = None, limit: int = 1000) -> list[MemoryRecord]:
    """Load memory records from JSONL files and an optional SQLite DB."""
    records: list[MemoryRecord] = []
    for path in memory_jsonl:
        records.extend(load_memory_jsonl(path))
    if memory_db is not None and memory_db.exists():
        records.extend(load_memory_db(memory_db, limit=limit))
    return records


def evaluate_memory_records(
    records: Iterable[MemoryRecord],
    policy: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a machine-readable retention and promotion report."""
    active_now = now or datetime.now(timezone.utc)
    reviews = [review_record(record, active_now, policy) for record in records]
    duplicates: dict[str, list[str]] = {}
    for record in records:
        key = sha256_text(f"{record.kind}:{record.scope}:{record.source}:{record.content}")[:20]
        duplicates.setdefault(key, []).append(record.record_id)
    duplicate_groups = [ids for ids in duplicates.values() if len(set(ids)) > 1]
    action_counts: dict[str, int] = {}
    for review in reviews:
        action_counts[review.action] = action_counts.get(review.action, 0) + 1
    risk_count = sum(1 for review in reviews if review.action == "quarantine")
    report = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "kind": "agent_memory_policy_report",
        "generated_at": utc_now_iso(),
        "passed": risk_count == 0,
        "record_count": len(reviews),
        "promotion_candidate_count": sum(1 for review in reviews if review.promotion_candidate),
        "review_count": sum(1 for review in reviews if review.action in {"human_review", "trim_review", "expire_review"}),
        "risk_count": risk_count,
        "duplicate_group_count": len(duplicate_groups),
        "action_counts": action_counts,
        "policy": policy or DEFAULT_RETENTION_POLICY,
        "duplicate_groups": duplicate_groups,
        "reviews": [review.to_dict() for review in reviews],
        "promotion_candidates": [review.to_dict() for review in reviews if review.promotion_candidate],
        "notes": [
            "This report is non-destructive and never deletes or promotes records by itself.",
            "Promotion means a human or app workflow may distill a record into stable docs or a reviewed JSONL store.",
            "Quarantine means a record should not be selected into agent context until manually inspected.",
        ],
    }
    return report


def write_memory_policy_markdown(report: dict[str, Any], path: Path) -> None:
    """Write a compact Markdown review report."""
    lines = [
        "# Agent Memory Policy Report",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Passed: `{report.get('passed')}`",
        f"- Records: `{report.get('record_count')}`",
        f"- Promotion candidates: `{report.get('promotion_candidate_count')}`",
        f"- Review count: `{report.get('review_count')}`",
        f"- Risk count: `{report.get('risk_count')}`",
        "",
        "## Action Counts",
        "",
    ]
    for action, count in sorted((report.get("action_counts") or {}).items()):
        lines.append(f"- `{action}`: {count}")
    lines.extend(["", "## Promotion Candidates", ""])
    candidates = report.get("promotion_candidates") or []
    if not candidates:
        lines.append("None.")
    for item in candidates:
        lines.extend(
            [
                f"### {item.get('record_id')}",
                "",
                f"- Source: `{item.get('source')}`",
                f"- Kind: `{item.get('kind')}`",
                f"- Reason: `{item.get('promotion_reason')}`",
                "",
                str(item.get("summary") or ""),
                "",
            ]
        )
    lines.extend(["", "## Risks", ""])
    risks = [item for item in report.get("reviews", []) if item.get("action") == "quarantine"]
    if not risks:
        lines.append("None.")
    for item in risks:
        lines.append(f"- `{item.get('record_id')}` from `{item.get('source')}`: {', '.join(item.get('issues') or [])}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")