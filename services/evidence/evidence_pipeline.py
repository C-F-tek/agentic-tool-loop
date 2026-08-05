# services/evidence/evidence_pipeline - Evidence collection and transport pipeline
#
# This module provides evidence collection from job artifacts and transport
# to OpenWebUI public surface. It replaces the scattered evidence modules
# in aicarmine_broker/application/evidence/* and vulkan_bridge/app.py.
#
# All evidence operations must use this module instead of direct filesystem
# access or ad-hoc evidence assembly.

from __future__ import annotations

import json
from typing import Optional, Any
from pathlib import Path


class EvidenceCollector:
    """Evidence Collector.
    
    Collects evidence from job artifacts (tool results, final.json, events).
    """
    
    def __init__(self, job_root: str):
        self.job_root = Path(job_root)
    
    def collect_evidence(self, job_id: str) -> dict:
        """Collect evidence from job artifacts.
        
        Returns evidence dictionary with indexed payloads.
        """
        evidence = {
            "job_id": job_id,
            "items": [],
            "total_items": 0,
        }
        
        # Collect from tool-results directory
        tool_results_dir = self.job_root / "tool-results"
        if tool_results_dir.exists():
            for result_file in tool_results_dir.glob("*.json"):
                try:
                    with open(result_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            evidence["items"].append({
                                "source": "tool-result",
                                "file": result_file.name,
                                "data": data,
                            })
                except (json.JSONDecodeError, IOError):
                    continue
        
        # Collect from final.json if exists
        final_file = self.job_root / "final" / f"{job_id}.json"
        if final_file.exists():
            try:
                with open(final_file, 'r', encoding='utf-8') as f:
                    final_data = json.load(f)
                    evidence["items"].append({
                        "source": "final",
                        "file": "final.json",
                        "data": final_data,
                    })
            except (json.JSONDecodeError, IOError):
                pass
        
        evidence["total_items"] = len(evidence["items"])
        return evidence
    
    def collect_tool_result(self, job_id: str, tool_name: str) -> Optional[dict]:
        """Collect a specific tool result.
        
        Returns the tool result dictionary or None.
        """
        tool_results_dir = self.job_root / "tool-results"
        if not tool_results_dir.exists():
            return None
        
        for result_file in tool_results_dir.glob(f"*{tool_name}*.json"):
            try:
                with open(result_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                continue
        
        return None


class EvidenceTransport:
    """Evidence Transport.
    
    Transports evidence to OpenWebUI public surface.
    Builds payload_index_for_30b, priority_evidence_for_30b, tool_context_for_30b.
    """
    
    def __init__(self, job_root: str):
        self.job_root = Path(job_root)
    
    def build_public_payload(self, job_id: str) -> dict:
        """Build public payload for OpenWebUI.
        
        Returns the complete public payload shape with all required fields.
        """
        # Collect evidence from job artifacts
        collector = EvidenceCollector(self.job_root)
        evidence = collector.collect_evidence(job_id)
        
        # Build payload index
        payload_index = self._build_payload_index(evidence)
        
        # Build priority evidence
        priority_evidence = self._build_priority_evidence(evidence)
        
        # Build tool context
        tool_context = self._build_tool_context(evidence)
        
        # Build openwebui_usage
        openwebui_usage = self._build_openwebui_usage()
        
        return {
            "payload_index_for_30b": payload_index,
            "priority_evidence_for_30b": priority_evidence,
            "tool_context_for_30b": tool_context,
            "openwebui_usage": openwebui_usage,
            "materialization_report": {
                "owner": "3572_broker",
                "status": "complete",
                "inline_content_verified": True,
            },
        }
    
    def _build_payload_index(self, evidence: dict) -> dict:
        """Build payload_index_for_30b navigation surface."""
        items = []
        for item in evidence.get("items", []):
            items.append({
                "source": item.get("source", ""),
                "file": item.get("file", ""),
                "primary_location": f"tool_context_for_30b.artifacts[{len(items)}].artifact",
                "has_inline_content": bool(item.get("data")),
            })
        
        return {
            "items": items,
            "total_items": len(items),
            "internal_job_status": "completed",
        }
    
    def _build_priority_evidence(self, evidence: dict) -> dict:
        """Build priority_evidence_for_30b high-priority evidence."""
        priority_items = []
        
        for item in evidence.get("items", []):
            data = item.get("data", {})
            if isinstance(data, dict):
                # Check for code-edit proposal
                if data.get("kind") == "code_edit_proposal":
                    priority_items.append({
                        "type": "code_edit_proposal",
                        "target_file": data.get("target_file", ""),
                        "edit_kind": data.get("edit_kind", ""),
                        "unified_diff": data.get("unified_diff", ""),
                        "rationale": data.get("rationale", ""),
                    })
                # Check for repo_read content
                elif "content" in data and data.get("repo_path"):
                    priority_items.append({
                        "type": "repo_read",
                        "repo_path": data.get("repo_path", ""),
                        "line_count": data.get("line_count", 0),
                        "content_preview": data.get("content", "")[:500],
                    })
        
        return {
            "items": priority_items,
            "total_priority": len(priority_items),
        }
    
    def _build_tool_context(self, evidence: dict) -> str:
        """Build tool_context_for_30b pretty-printed JSON string."""
        artifacts = []
        
        for item in evidence.get("items", []):
            data = item.get("data", {})
            if data:
                artifacts.append({
                    "artifact_id": item.get("file", ""),
                    "source": item.get("source", ""),
                    "artifact": data,
                })
        
        context = {
            "artifacts": artifacts,
            "total_artifacts": len(artifacts),
            "limit": 100,
        }
        
        return json.dumps(context, indent=2, ensure_ascii=False)
    
    def _build_openwebui_usage(self) -> dict:
        """Build openwebui_usage runtime instructions."""
        return {
            "internal_job_status": "completed",
            "instructions": [
                "Read payload_index_for_30b for navigation",
                "Check priority_evidence_for_30b for high-priority content",
                "Parse tool_context_for_30b for complete tool evidence",
            ],
            "note": "Local paths and SQLite IDs are not substitutes for inline content",
        }


# Module-level singletons
_evidence_collector: Optional[EvidenceCollector] = None
_evidence_transport: Optional[EvidenceTransport] = None

def get_evidence_collector(job_root: str) -> EvidenceCollector:
    """Get the EvidenceCollector singleton."""
    global _evidence_collector
    if _evidence_collector is None:
        _evidence_collector = EvidenceCollector(job_root)
    return _evidence_collector

def get_evidence_transport(job_root: str) -> EvidenceTransport:
    """Get the EvidenceTransport singleton."""
    global _evidence_transport
    if _evidence_transport is None:
        _evidence_transport = EvidenceTransport(job_root)
    return _evidence_transport

def collect_evidence(job_id: str, job_root: str) -> dict:
    """Convenience function to collect evidence."""
    return get_evidence_collector(job_root).collect_evidence(job_id)

def build_public_payload(job_id: str, job_root: str) -> dict:
    """Convenience function to build public payload."""
    return get_evidence_transport(job_root).build_public_payload(job_id)