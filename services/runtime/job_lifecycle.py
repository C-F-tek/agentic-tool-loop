# services/runtime/job_lifecycle - Job state machine and persistence
#
# This module provides the job lifecycle state machine and job store for
# persistence. It replaces the scattered job management in job_store.py
# and application/job/*.py files.
#
# All job lifecycle management must use this module instead of direct
# filesystem operations or ad-hoc state tracking.

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any
from pathlib import Path


class JobState(str, Enum):
    """Job lifecycle states."""
    QUEUED = "queued"
    RUNNING = "running"
    TERMINAL_COMPLETED = "terminal_completed"
    TERMINAL_BLOCKED = "terminal_blocked"
    TERMINAL_MAX_STEPS = "terminal_max_steps"
    TERMINAL_FAILED = "terminal_failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """Represents an agentic job."""
    job_id: str
    goal: str
    lab_repo: str
    state: JobState = JobState.QUEUED
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    current_step: int = 0
    max_steps: int = 50
    final_answer: Optional[str] = None
    error_message: Optional[str] = None
    events: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.job_id:
            self.job_id = str(uuid.uuid4())[:8]
    
    def transition_to(self, new_state: JobState):
        """Transition to a new state."""
        self.state = new_state
        self.updated_at = datetime.now().isoformat()
        
        # Record the transition event
        self.events.append({
            "event": "state_transition",
            "from": self.state.value if hasattr(self, 'state') and 
                    hasattr(self.__class__, 'state') else "unknown",
            "to": new_state.value,
            "timestamp": self.updated_at,
        })
    
    def add_event(self, event_type: str, details: Optional[dict] = None):
        """Add an event to the job."""
        event = {
            "event": event_type,
            "timestamp": datetime.now().isoformat(),
        }
        if details:
            event.update(details)
        self.events.append(event)
        self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "job_id": self.job_id,
            "goal": self.goal,
            "lab_repo": self.lab_repo,
            "state": self.state.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "current_step": self.current_step,
            "max_steps": self.max_steps,
            "final_answer": self.final_answer,
            "error_message": self.error_message,
            "events_count": len(self.events),
            "metadata": self.metadata,
        }


class JobStore:
    """Job Store.
    
    Job persistence with filesystem JSON as primary and SQLite as secondary index.
    """
    
    def __init__(self, job_root: Optional[str] = None, sqlite_path: Optional[str] = None):
        self.job_root = Path(job_root) if job_root else Path(r"C:\Users\sanit\agentic-tool-loop\state\jobs")
        self.sqlite_path = sqlite_path or str(self.job_root / "jobs.db")
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Ensure required directories exist."""
        self.job_root.mkdir(parents=True, exist_ok=True)
        (self.job_root / "jobs").mkdir(exist_ok=True)
        (self.job_root / "events").mkdir(exist_ok=True)
        (self.job_root / "final").mkdir(exist_ok=True)
        (self.job_root / "tool-results").mkdir(exist_ok=True)
    
    def create_job(self, goal: str, lab_repo: str, max_steps: int = 50) -> Job:
        """Create a new job with initial state."""
        job = Job(
            job_id=str(uuid.uuid4())[:8],
            goal=goal,
            lab_repo=lab_repo,
            max_steps=max_steps,
            state=JobState.QUEUED,
        )
        job.add_event("job_created", {"goal": goal, "lab_repo": lab_repo})
        
        # Write to filesystem (primary)
        self._write_job_json(job)
        
        # Update SQLite index (secondary)
        self._update_sqlite_index(job)
        
        return job
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        # Try filesystem first
        job_file = self.job_root / "jobs" / f"{job_id}.json"
        if job_file.exists():
            try:
                with open(job_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return self._dict_to_job(data)
            except (json.JSONDecodeError, IOError):
                pass
        
        # Fallback to SQLite
        return self._get_job_from_sqlite(job_id)
    
    def list_jobs(self, limit: int = 50, state_filter: Optional[JobState] = None) -> list[Job]:
        """List all jobs, optionally filtered by state."""
        jobs = []
        
        for job_file in (self.job_root / "jobs").glob("*.json"):
            try:
                with open(job_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    job = self._dict_to_job(data)
                    if state_filter is None or job.state == state_filter:
                        jobs.append(job)
            except (json.JSONDecodeError, IOError):
                continue
        
        # Sort by created_at descending
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        
        return jobs[:limit]
    
    def transition_job(self, job_id: str, new_state: JobState, 
                       final_answer: Optional[str] = None,
                       error_message: Optional[str] = None) -> bool:
        """Transition a job to a new state."""
        job = self.get_job(job_id)
        if not job:
            return False
        
        old_state = job.state
        job.transition_to(new_state)
        job.final_answer = final_answer
        job.error_message = error_message
        
        if new_state == JobState.TERMINAL_COMPLETED:
            job.add_event("job_completed", {"final_answer": final_answer})
        elif new_state == JobState.TERMINAL_BLOCKED:
            job.add_event("job_blocked", {"error": error_message})
        elif new_state == JobState.TERMINAL_MAX_STEPS:
            job.add_event("job_max_steps_reached")
        elif new_state == JobState.TERMINAL_FAILED:
            job.add_event("job_failed", {"error": error_message})
        elif new_state == JobState.CANCELLED:
            job.add_event("job_cancelled")
        
        # Write updated state to filesystem
        self._write_job_json(job)
        
        # Update SQLite index
        self._update_sqlite_index(job)
        
        return True
    
    def get_terminal_response(self, job_id: str) -> Optional[dict]:
        """Get the terminal response for a completed/blocked job."""
        final_file = self.job_root / "final" / f"{job_id}.json"
        if final_file.exists():
            try:
                with open(final_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        
        job = self.get_job(job_id)
        if job and job.state in (JobState.TERMINAL_COMPLETED, JobState.TERMINAL_BLOCKED,
                                  JobState.TERMINAL_MAX_STEPS, JobState.TERMINAL_FAILED):
            return {
                "job_id": job.job_id,
                "state": job.state.value,
                "final_answer": job.final_answer,
                "error_message": job.error_message,
                "events_count": len(job.events),
            }
        
        return None
    
    def _write_job_json(self, job: Job):
        """Write job state to filesystem JSON."""
        job_file = self.job_root / "jobs" / f"{job.job_id}.json"
        data = job.to_dict()
        with open(job_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _update_sqlite_index(self, job: Job):
        """Update SQLite secondary index."""
        try:
            conn = sqlite3.connect(self.sqlite_path)
            cursor = conn.cursor()
            
            # Create table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    goal TEXT,
                    lab_repo TEXT,
                    state TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    current_step INTEGER,
                    max_steps INTEGER,
                    final_answer TEXT,
                    error_message TEXT
                )
            """)
            
            # Upsert
            cursor.execute("""
                INSERT OR REPLACE INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.job_id, job.goal, job.lab_repo, job.state.value,
                job.created_at, job.updated_at, job.current_step,
                job.max_steps, job.final_answer, job.error_message
            ))
            
            conn.commit()
            conn.close()
        except sqlite3.Error:
            pass  # SQLite failure is non-fatal; filesystem is primary
    
    def _get_job_from_sqlite(self, job_id: str) -> Optional[Job]:
        """Get job from SQLite index."""
        try:
            conn = sqlite3.connect(self.sqlite_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                data = dict(row)
                return self._dict_to_job(data)
        except sqlite3.Error:
            pass
        
        return None
    
    def _dict_to_job(self, data: dict) -> Job:
        """Convert dictionary to Job object."""
        return Job(
            job_id=data.get("job_id", ""),
            goal=data.get("goal", ""),
            lab_repo=data.get("lab_repo", ""),
            state=JobState(data.get("state", "queued")),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            current_step=data.get("current_step", 0),
            max_steps=data.get("max_steps", 50),
            final_answer=data.get("final_answer"),
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {}),
        )


# Module-level singleton
_job_store: Optional[JobStore] = None

def get_job_store(job_root: Optional[str] = None, 
                  sqlite_path: Optional[str] = None) -> JobStore:
    """Get the global JobStore singleton."""
    global _job_store
    if _job_store is None:
        _job_store = JobStore(job_root=job_root, sqlite_path=sqlite_path)
    return _job_store


def create_job(goal: str, lab_repo: str, max_steps: int = 50) -> Job:
    """Convenience function to create a new job."""
    return get_job_store().create_job(goal, lab_repo, max_steps)


def get_job(job_id: str) -> Optional[Job]:
    """Convenience function to get a job by ID."""
    return get_job_store().get_job(job_id)


def transition_job(job_id: str, new_state: JobState,
                   final_answer: Optional[str] = None,
                   error_message: Optional[str] = None) -> bool:
    """Convenience function to transition a job state."""
    return get_job_store().transition_job(job_id, new_state, final_answer, error_message)