"""
Diagnostics - Bug and error tracking for the orchestrator.

This module provides diagnostic capabilities for tracking bugs, errors,
and issues encountered during agentic loop execution.

Usage:
    python orchestrator/diagnostics.py --action log --error "Failed to connect to database" --step 3
    python orchestrator/diagnostics.py --action list --status pending
    python orchestrator/diagnostics.py --action resolve --id BUG-001
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DiagnosticRecord:
    """A diagnostic record representing a bug or error."""
    id: str
    timestamp: str
    severity: str  # "info", "warning", "error", "critical"
    category: str  # "connection", "parsing", "search", "query", "tool", "other"
    message: str
    step_number: int | None = None
    action: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # "pending", "investigating", "resolved", "closed"
    resolution: str | None = None
    resolved_at: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "step_number": self.step_number,
            "action": self.action,
            "context": self.context,
            "status": self.status,
            "resolution": self.resolution,
            "resolved_at": self.resolved_at,
        }


class DiagnosticsTracker:
    """Tracks bugs and errors during orchestrator execution."""
    
    def __init__(self, log_file: str | None = None) -> None:
        """Initialize the diagnostics tracker."""
        self.log_file = Path(log_file) if log_file else Path(__file__).parent.parent / "logs" / "diagnostics.ndjson"
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.records: list[DiagnosticRecord] = []
        self.next_id = 1
    
    def _generate_id(self) -> str:
        """Generate a unique diagnostic ID."""
        record_id = f"BUG-{self.next_id:03d}"
        self.next_id += 1
        return record_id
    
    def log_error(
        self,
        message: str,
        severity: str = "error",
        category: str = "tool",
        step_number: int | None = None,
        action: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> DiagnosticRecord:
        """Log a new error or bug."""
        record = DiagnosticRecord(
            id=self._generate_id(),
            timestamp=datetime.now().isoformat(),
            severity=severity,
            category=category,
            message=message,
            step_number=step_number,
            action=action,
            context=context or {},
        )
        
        self.records.append(record)
        logger.info(f"[{record.id}] {severity.upper()}: {message}")
        
        # Write to log file
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Failed to write diagnostic log: {e}")
        
        return record
    
    def get_record(self, record_id: str) -> DiagnosticRecord | None:
        """Get a diagnostic record by ID."""
        for record in self.records:
            if record.id == record_id:
                return record
        return None
    
    def list_records(
        self,
        status: str | None = None,
        severity: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> list[DiagnosticRecord]:
        """List diagnostic records with optional filters."""
        records = self.records
        
        if status:
            records = [r for r in records if r.status == status]
        if severity:
            records = [r for r in records if r.severity == severity]
        if category:
            records = [r for r in records if r.category == category]
        
        return records[:limit]
    
    def resolve_record(self, record_id: str, resolution: str) -> bool:
        """Mark a record as resolved."""
        for record in self.records:
            if record.id == record_id:
                record.status = "resolved"
                record.resolution = resolution
                record.resolved_at = datetime.now().isoformat()
                logger.info(f"[{record.id}] Resolved: {resolution}")
                return True
        return False
    
    def get_summary(self) -> dict[str, Any]:
        """Get a summary of all diagnostics."""
        total = len(self.records)
        pending = len([r for r in self.records if r.status == "pending"])
        resolving = len([r for r in self.records if r.status == "investigating"])
        resolved = len([r for r in self.records if r.status == "resolved"])
        closed = len([r for r in self.records if r.status == "closed"])
        
        by_severity = {}
        for r in self.records:
            by_severity[r.severity] = by_severity.get(r.severity, 0) + 1
        
        by_category = {}
        for r in self.records:
            by_category[r.category] = by_category.get(r.category, 0) + 1
        
        return {
            "total": total,
            "pending": pending,
            "investigating": resolving,
            "resolved": resolved,
            "closed": closed,
            "by_severity": by_severity,
            "by_category": by_category,
        }


def main() -> int:
    """Main entry point for the diagnostics CLI."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Data RAG Agent - Diagnostics Tracker")
    parser.add_argument("--action", choices=["log", "list", "resolve", "summary"], required=True)
    parser.add_argument("--error", type=str, help="Error message (for 'log' action)")
    parser.add_argument("--severity", type=str, default="error", help="Severity level")
    parser.add_argument("--category", type=str, default="tool", help="Category")
    parser.add_argument("--step", type=int, help="Step number")
    parser.add_argument("--action-name", type=str, help="Action name")
    parser.add_argument("--id", type=str, help="Record ID (for 'resolve' action)")
    parser.add_argument("--resolution", type=str, help="Resolution text (for 'resolve' action)")
    parser.add_argument("--status-filter", type=str, help="Filter by status (for 'list' action)")
    parser.add_argument("--limit", type=int, default=50, help="Limit results")
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.action == "log" else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s", force=True)
    
    tracker = DiagnosticsTracker()
    
    try:
        if args.action == "log":
            if not args.error:
                print("Error: --error is required for 'log' action", file=sys.stderr)
                return 1
            
            record = tracker.log_error(
                message=args.error,
                severity=args.severity,
                category=args.category,
                step_number=args.step,
                action=args.action_name,
            )
            print(json.dumps(record.to_dict(), indent=2))
            return 0
        
        elif args.action == "list":
            records = tracker.list_records(
                status=args.status_filter,
                limit=args.limit,
            )
            result = {
                "count": len(records),
                "records": [r.to_dict() for r in records],
            }
            print(json.dumps(result, indent=2))
            return 0
        
        elif args.action == "resolve":
            if not args.id or not args.resolution:
                print("Error: --id and --resolution are required for 'resolve' action", file=sys.stderr)
                return 1
            
            success = tracker.resolve_record(args.id, args.resolution)
            if success:
                print(f"Record {args.id} resolved successfully")
                return 0
            else:
                print(f"Record {args.id} not found", file=sys.stderr)
                return 1
        
        elif args.action == "summary":
            summary = tracker.get_summary()
            print(json.dumps(summary, indent=2))
            return 0
    
    except Exception as e:
        logger.error(f"Diagnostics failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())