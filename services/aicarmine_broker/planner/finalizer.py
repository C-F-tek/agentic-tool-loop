"""Job finalization."""
from pathlib import Path
from typing import Any


class Finalizer:
    """Handles job finalization operations."""

    def __init__(self, config):
        self.config = config

    def finalize(
        self,
        job_id: str,
        state: dict[str, Any],
        status: str,
        final_summary: str,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Finalize an agentic job.

        Delegates to application/job/lifecycle.finalize_agentic_job.
        """
        from ..application.job.lifecycle import (
            finalize_agentic_job as _impl,
        )
        return _impl(
            job_id=job_id,
            state=state,
            status=status,
            final_summary=final_summary,
            result=result,
        )

    def judge_blocked(
        self,
        job_id: str,
        root: Path,
        state: dict[str, Any],
        status: str,
        final_summary: str,
        result: dict[str, Any],
        tool_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Judge a blocked job.

        Delegates to application/job/blocked_judge.BlockedJobJudge.judge().
        """
        from ..application.job.blocked_judge import (
            BlockedJobJudge,
        )
        judge = BlockedJobJudge()
        return judge.judge(
            job_id=job_id,
            root=root,
            state=state,
            status=status,
            final_summary=final_summary,
            result=result,
            tool_context=tool_context,
        )