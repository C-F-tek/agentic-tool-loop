"""Discovery dinamico degli entry point tramite AST parsing."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from services.aicarmine_broker.application.evidence.entry_point_info import EntryPointInfo


class EntryPointAnalyzer:
    """Analizzatore per discovery dinamico degli entry point senza hardcoded."""
    
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
    
    def scan_for_functions(self, file_path: Path) -> list[dict]:
        """Scansiona AST per trovare funzioni entry point."""
        try:
            with open(file_path, encoding="utf-8") as f:
                source = f.read()
            tree = ast.parse(source)
            
            functions = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    args = [arg.arg for arg in node.args.args if arg.arg != "self"]
                    sig = f"{node.name}({', '.join(args)})" if args else node.name
                    functions.append({
                        "name": node.name,
                        "signature": sig,
                        "line": node.lineno,
                        "is_entry_point": node.name in {"main", "run", "start", "execute"},
                        "docstring": ast.get_docstring(node)
                    })
            return functions
        except Exception:
            return []
    
    def identify_entry_points(self, contract: dict[str, Any]) -> list[EntryPointInfo]:
        """Identifica entry points dinamicamente dal contratto."""
        entry_points = []
        
        covered_owner_paths = contract.get("covered_owner_paths", [])
        if not isinstance(covered_owner_paths, list):
            covered_owner_paths = []
        
        for path in covered_owner_paths:
            if not isinstance(path, str):
                continue
            
            file_path = self.repo_root / path
            if not file_path.exists():
                continue
            
            functions = self.scan_for_functions(file_path)
            
            for func in functions:
                entry_points.append(EntryPointInfo(
                    path=path,
                    symbol_name=func["name"],
                    line_number=func["line"],
                    function_signature=func["signature"],
                    is_entry_point=func["is_entry_point"]
                ))
        
        return entry_points
    
    def calculate_coverage(self, discovered_ep: list[EntryPointInfo], 
                          verified_reads: list[dict]) -> float:
        """Calcola coverage strutturale completa."""
        if not discovered_ep:
            return 0.0
        
        total_ep = len(discovered_ep)
        covered_ep = sum(
            1 for ep in discovered_ep
            if any(ep.path in str(r.get("path", "")) for r in verified_reads)
        )
        
        return covered_ep / total_ep if total_ep > 0 else 0.0