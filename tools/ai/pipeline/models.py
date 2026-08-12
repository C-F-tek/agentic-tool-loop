"""Dataclasses for reusable AI artifact pipeline orchestration."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class PipelineLane(str, Enum):
    """Execution lane for a pipeline step.

    This intentionally uses ``str, Enum`` instead of ``StrEnum`` so the module
    remains compatible with Python 3.10+.
    """

    CPU = "CPU"
    NPU = "NPU"
    GPU = "GPU"
    IO = "IO"
    VALIDATION = "VALIDATION"


@dataclass(frozen=True)
class PipelineStep:
    """A command-backed pipeline step.

    The command is represented as an argv-style list to avoid shell quoting
    ambiguity. Use a dedicated formatting helper when a copy-pasteable command
    preview is required.
    """

    name: str
    command: tuple[str, ...]
    lane: PipelineLane = PipelineLane.CPU
    purpose: str = ""
    expected_outputs: tuple[str, ...] = ()
    pass_index: int = 0
    allow_failure: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_command(
        cls,
        *,
        name: str,
        command: list[str] | tuple[str, ...],
        lane: PipelineLane | str = PipelineLane.CPU,
        purpose: str = "",
        expected_outputs: list[str] | tuple[str, ...] = (),
        pass_index: int = 0,
        allow_failure: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> "PipelineStep":
        """Build a step from a list-like command."""
        return cls(
            name=name,
            command=tuple(str(part) for part in command),
            lane=PipelineLane(lane),
            purpose=purpose,
            expected_outputs=tuple(str(item) for item in expected_outputs),
            pass_index=pass_index,
            allow_failure=allow_failure,
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        data = asdict(self)
        data["lane"] = self.lane.value
        data["command"] = list(self.command)
        data["expected_outputs"] = list(self.expected_outputs)
        return data


@dataclass(frozen=True)
class PipelineResult:
    """Execution result for a pipeline step."""

    step: PipelineStep
    returncode: int
    duration_sec: float
    stdout: str = ""
    stderr: str = ""
    dry_run: bool = False
    planned_only: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        """Return True when the result is successful or explicitly allowed."""
        return self.returncode == 0 or self.step.allow_failure

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "name": self.step.name,
            "lane": self.step.lane.value,
            "purpose": self.step.purpose,
            "expected_outputs": list(self.step.expected_outputs),
            "pass_index": self.step.pass_index,
            "allow_failure": self.step.allow_failure,
            "metadata": self.step.metadata,
            "command": list(self.step.command),
            "returncode": self.returncode,
            "duration_sec": self.duration_sec,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "dry_run": self.dry_run,
            "planned_only": self.planned_only,
            "error": self.error,
            "ok": self.ok,
        }


@dataclass(frozen=True)
class PipelineReport:
    """Serializable report for an artifact pipeline run."""

    schema_version: int
    generated_at: str
    repo_root: Path
    output_dir: Path
    dry_run: bool
    passed: bool
    preflight: dict[str, Any]
    results: tuple[PipelineResult, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "repo_root": str(self.repo_root),
            "output_dir": str(self.output_dir),
            "dry_run": self.dry_run,
            "passed": self.passed,
            "preflight": self.preflight,
            "step_count": len(self.results),
            "lanes": self.lanes,
            "steps": [item.to_dict() for item in self.results],
            "metadata": self.metadata,
        }

    @property
    def lanes(self) -> dict[str, list[str]]:
        """Return step names grouped by execution lane."""
        grouped: dict[str, list[str]] = {}
        for result in self.results:
            grouped.setdefault(result.step.lane.value, []).append(result.step.name)
        return grouped
