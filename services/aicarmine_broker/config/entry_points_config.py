"""Entry points contract schema definition.

Entry points MUST be defined in the evidence_contract.minimum_read_coverage
or evidence_contract.entry_points fields, NOT hardcoded here.

This module provides schema documentation and validation helpers only.
Actual entry point values come from the contract at mount point.
"""

from __future__ import annotations

from typing import Any


ENTRY_POINTS_SCHEMA = {
    "type": "object",
    "description": "Project entry points defined in contract at mount point",
    "properties": {
        "agent_entry": {"type": "string", "description": "Agent entry point path"},
        "app": {"type": "string", "description": "Application entry point path"},
    },
    "required": [],
    "additionalProperties": False,
}


def entry_points_from_contract(contract: dict[str, Any]) -> dict[str, str] | None:
    """Extract entry points from contract.
    
    Entry points are defined in contract.minimum_read_coverage.covered_owner_paths
    or contract.entry_points. Do not hardcode paths here.
    
    Args:
        contract: Evidence contract containing entry_points field
        
    Returns:
        Dictionary of entry point names to paths, or None if not present
    """
    if not isinstance(contract, dict):
        return None
    
    entry_points = contract.get("entry_points")
    if not isinstance(entry_points, dict):
        return None
    
    return {
        key: str(value)
        for key, value in entry_points.items()
        if isinstance(value, str) and value
    }


__all__ = ["ENTRY_POINTS_SCHEMA", "entry_points_from_contract"]
