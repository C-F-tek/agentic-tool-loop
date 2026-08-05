# services/public_payload/payload_shaper - Public payload shaping for OpenWebUI
#
# This module provides the canonical public payload shaper for terminal payloads
# returned via the vulkan bridge (port 3571) to OpenWebUI. It replaces the scattered
# payload assembly logic in vulkan_bridge/app.py.

from __future__ import annotations

import json
import os
from typing import Optional, Dict, Any


class PublicPayloadShaper:
    """Public Payload Shaper.
    
    Shapes terminal payloads for the OpenWebUI public surface.
    Builds payload_index_for_30b, priority_evidence_for_30b, tool_context_for_30b,
    openwebui_usage, and result fields.
    """
    
    def __init__(self):
        self._max_response_chars = int(os.getenv("BRIDGE_MAX_OPENWEBUI_RESPONSE_CHARS", "4000"))
        self._max_summary_chars = int(os.getenv("BRIDGE_MAX_OPENWEBUI_SUMMARY_CHARS", "2000"))
        self._max_answer_chars = int(os.getenv("BRIDGE_MAX_OPENWEBUI_ANSWER_CHARS", "3000"))
        self._inline_file_chars = int(os.getenv("BRIDGE_OPENWEBUI_INLINE_FILE_CHARS", "8000"))
        self._inline_evidence_chars = int(os.getenv("BRIDGE_OPENWEBUI_INLINE_EVIDENCE_CHARS", "6000"))
    
    def shape_terminal_payload(self, job_id: str, job_store=None) -> dict:
        """Shape terminal payload for a given job_id.
        
        Returns a dict with:
        - payload_index_for_30b: list of field names indicating which fields contain concrete results
        - priority_evidence_for_30b: prioritized evidence material
        - tool_context_for_30b: tool context summary
        - openwebui_usage: usage metadata
        - result: the final result
        
        In production, this reads from job_store or filesystem artifacts.
        """
        # Build payload index - fields containing concrete results vs descriptions
        payload_index_for_30b = []
        priority_evidence_for_30b = ""
        tool_context_for_30b = ""
        openwebui_usage = ""
        result = ""
        
        if job_store and hasattr(job_store, 'get_job'):
            job_data = job_store.get_job(job_id)
            if job_data:
                # Extract concrete evidence from job data
                if 'terminal_result' in job_data:
                    payload_index_for_30b.append('terminal_result')
                    priority_evidence_for_30b = job_data['terminal_result']
                if 'tool_context' in job_data:
                    payload_index_for_30b.append('tool_context')
                    tool_context_for_30b = job_data['tool_context']
                if 'result' in job_data:
                    payload_index_for_30b.append('result')
                    result = job_data['result']
        
        # Truncate to configured limits
        if len(priority_evidence_for_30b) > self._max_response_chars:
            priority_evidence_for_30b = priority_evidence_for_30b[:self._max_response_chars]
        if len(tool_context_for_30b) > self._max_answer_chars:
            tool_context_for_30b = tool_context_for_30b[:self._max_answer_chars]
        if len(result) > self._max_summary_chars:
            result = result[:self._max_summary_chars]
        
        return {
            "payload_index_for_30b": payload_index_for_30b,
            "priority_evidence_for_30b": priority_evidence_for_30b,
            "tool_context_for_30b": tool_context_for_30b,
            "openwebui_usage": openwebui_usage,
            "result": result,
        }
    
    def shape_terminal_payload_from_filesystem(self, job_id: str, job_root: str = None) -> dict:
        """Shape terminal payload by reading from filesystem artifacts.
        
        Reads from tool-results/*.json and final/{job_id}.json.
        """
        if job_root is None:
            job_root = os.getenv("AICARMINE_AGENT_JOB_ROOT", "state/codex_bridge/agentic_loop_client/port-3579/workspace/agent-jobs")
        
        final_path = os.path.join(job_root, f"job-{job_id}", "final", f"{job_id}.json")
        
        try:
            with open(final_path, 'r', encoding='utf-8') as f:
                job_data = json.load(f)
            
            payload_index_for_30b = []
            priority_evidence_for_30b = ""
            tool_context_for_30b = ""
            result = ""
            
            for key in ['terminal_result', 'tool_context', 'result']:
                if key in job_data:
                    payload_index_for_30b.append(key)
                    value = job_data[key]
                    if isinstance(value, str):
                        if key == 'terminal_result':
                            priority_evidence_for_30b = value
                        elif key == 'tool_context':
                            tool_context_for_30b = value
                        else:
                            result = value
        
        except (FileNotFoundError, json.JSONDecodeError):
            # Fallback: return empty payload
            pass
        
        return {
            "payload_index_for_30b": payload_index_for_30b,
            "priority_evidence_for_30b": priority_evidence_for_30b,
            "tool_context_for_30b": tool_context_for_30b,
            "openwebui_usage": "",
            "result": result,
        }


# Module-level singleton
_payload_shaper: Optional[PublicPayloadShaper] = None

def get_payload_shaper() -> PublicPayloadShaper:
    """Get the global PublicPayloadShaper singleton."""
    global _payload_shaper
    if _payload_shaper is None:
        _payload_shaper = PublicPayloadShaper()
    return _payload_shaper

def shape_terminal_payload(job_id: str, job_store=None) -> dict:
    """Convenience function to shape a terminal payload."""
    return get_payload_shaper().shape_terminal_payload(job_id, job_store)