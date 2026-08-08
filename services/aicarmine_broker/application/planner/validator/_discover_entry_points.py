"""Funzione _discover_entry_points per discovery dinamico degli entry point."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from services.aicarmine_broker.application.evidence.entry_point_analyzer import EntryPointAnalyzer
from services.aicarmine_broker.application.evidence.entry_point_info import EntryPointInfo


def _discover_entry_points(contract: dict[str, Any]) -> list[EntryPointInfo]:
    """Scopre entry points dinamicamente senza hardcoded.
    
    Args:
        contract: Contratto che contiene covered_owner_paths
        
    Returns:
        Lista di EntryPointInfo scoperti dinamicamente
    """
    analyzer = EntryPointAnalyzer(Path.cwd())
    entry_points = []
    
    covered_owner_paths = contract.get("covered_owner_paths", [])
    if not isinstance(covered_owner_paths, list):
        covered_owner_paths = []
    
    for path in covered_owner_paths:
        if not isinstance(path, str):
            continue
        
        file_path = Path(path)
        if not file_path.exists():
            continue
        
        functions = analyzer.scan_for_functions(file_path)
        
        for func in functions:
            entry_points.append(EntryPointInfo(
                path=str(path),
                symbol_name=func["name"],
                line_number=func["line"],
                function_signature=func["signature"],
                is_entry_point=func["is_entry_point"]
            ))
    
    return entry_points