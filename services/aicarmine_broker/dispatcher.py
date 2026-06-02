"""
aicarmine_broker.dispatcher
===========================
Compatibility facade for broker dispatch and public agent entrypoints.

Implementation lives in focused modules: ``agent_entry``, ``tool_dispatch``,
``tool_selection``, ``public_wrapper`` and ``job_html``.
"""
from __future__ import annotations

from .agent_entry import agent, agent_job_worker, start_agent_job
from .job_html import agent_job_html
from .tool_dispatch import dispatch_tool

__all__ = ["agent", "agent_job_html", "agent_job_worker", "dispatch_tool", "start_agent_job"]
