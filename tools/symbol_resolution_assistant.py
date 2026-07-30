#!/usr/bin/env python3
"""
AICarmine Symbol Resolution Assistant.

Provides a tool that helps the planner resolve which MCP tool to use
based on task description. Uses keyword matching against the symbol
reference for immediate tool recommendation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SYMBOL_REF_PATH = Path(__file__).resolve().parents[1] / ".docs" / "tool_symbol_reference.json"


# ---------------------------------------------------------------------------
# Task-to-tool patterns
# ---------------------------------------------------------------------------

TASK_PATTERNS: list[dict[str, Any]] = [
    # Repository operations
    {
        "patterns": [r"leggi\s+il\s+contenuto\s+di", r"read\s+content\s+of", r"apri\s+file", r"open\s+file"],
        "recommended": "aicarmine_repo_read",
        "confidence": 0.95,
        "reason": "Task requires reading file contents",
    },
    {
        "patterns": [r"elenca\s+file", r"list\s+files", r"cosa\s+ci\s+sono", r"what\s+in\s+directory"],
        "recommended": "aicarmine_repo_list_files",
        "confidence": 0.92,
        "reason": "Task requires listing files in directory",
    },
    {
        "patterns": [r"cerca\s+nel\s+codice", r"search\s+code", r"trova\s+funzione", r"find\s+function"],
        "recommended": "aicarmine_repo_search",
        "confidence": 0.88,
        "reason": "Task requires searching in code",
    },
    {
        "patterns": [r"cerca\s+per\s+pattern", r"find\s+by\s+pattern", r"trova\s+file"],
        "recommended": "aicarmine_repo_fd_files",
        "confidence": 0.90,
        "reason": "Task requires file discovery by pattern",
    },
    {
        "patterns": [r"cerca\s+con\s+ripgrep", r"rg\s+search"],
        "recommended": "aicarmine_repo_rg_search",
        "confidence": 0.95,
        "reason": "Task explicitly mentions ripgrep search",
    },
    {
        "patterns": [r"verifica\s+stato", r"check\s+status", r"commit\s+attuale", r"current\s+commit"],
        "recommended": "aicarmine_repo_status",
        "confidence": 0.90,
        "reason": "Task requires checking repository status",
    },
    {
        "patterns": [r"albero\s+directory", r"directory\s+tree", r"struttura\s+progetto"],
        "recommended": "aicarmine_repo_tree",
        "confidence": 0.90,
        "reason": "Task requires directory tree view",
    },
    {
        "patterns": [r"proponi\s+modifica", r"propose\s+edit", r"suggerisci\s+cambiamento"],
        "recommended": "aicarmine_repo_propose_code_edit",
        "confidence": 0.92,
        "reason": "Task requires proposing code edit",
    },
    {
        "patterns": [r"applica\s+patch", r"apply\s+patch", r"scrivi\s+file", r"write\s+file"],
        "recommended": "aicarmine_repo_apply_patch",
        "confidence": 0.93,
        "reason": "Task requires applying patch (write operation)",
    },
    {
        "patterns": [r"valida\s+diff", r"validate\s+diff", r"controlla\s+codice"],
        "recommended": "aicarmine_repo_validate",
        "confidence": 0.88,
        "reason": "Task requires validation",
    },
    {
        "patterns": [r"ruff", r"lint", r"linter"],
        "recommended": "aicarmine_repo_ruff_check",
        "confidence": 0.95,
        "reason": "Task requires ruff linting",
    },
    {
        "patterns": [r"pyright", r"type\s*check", r"controllo\s+tipi"],
        "recommended": "aicarmine_repo_pyright_check",
        "confidence": 0.95,
        "reason": "Task requires pyright type checking",
    },
    {
        "patterns": [r"test", r"pytest", r"esecuzione\s+test"],
        "recommended": "aicarmine_repo_pytest_run",
        "confidence": 0.93,
        "reason": "Task requires running tests",
    },
    # Git operations
    {
        "patterns": [r"log\s+git", r"commit\s+recenti", r"storia\s+repository"],
        "recommended": "aicarmine_git_readonly_log",
        "confidence": 0.93,
        "reason": "Task requires git log",
    },
    {
        "patterns": [r"diff\s+git", r"git\s+diff", r"cambiamenti"],
        "recommended": "aicarmine_git_readonly_diff",
        "confidence": 0.92,
        "reason": "Task requires git diff",
    },
    {
        "patterns": [r"blame", r"chi\s+ha\s+scritto", r"author\s+di\s+linea"],
        "recommended": "aicarmine_git_readonly_blame",
        "confidence": 0.93,
        "reason": "Task requires git blame",
    },
    {
        "patterns": [r"mostra\s+commit", r"show\s+commit", r"dettagli\s+commit"],
        "recommended": "aicarmine_git_readonly_show",
        "confidence": 0.92,
        "reason": "Task requires showing a commit",
    },
    # Job operations
    {
        "patterns": [r"stato\s+job", r"job\s+status", r"verifica\s+esecuzione"],
        "recommended": "aicarmine_jobs_status",
        "confidence": 0.90,
        "reason": "Task requires job status",
    },
    {
        "patterns": [r"eventi\s+job", r"job\s+events", r"log\s+esecuzione"],
        "recommended": "aicarmine_job_artifact_events",
        "confidence": 0.92,
        "reason": "Task requires job events",
    },
    {
        "patterns": [r"risultato\s+job", r"job\s+result", r"output\s+finale"],
        "recommended": "aicarmine_job_artifact_final",
        "confidence": 0.92,
        "reason": "Task requires job final result",
    },
    # Memory operations
    {
        "patterns": [r"cerca\s+memoria", r"search\s+memory", r"project\s+memory"],
        "recommended": "aicarmine_project_memory_search",
        "confidence": 0.92,
        "reason": "Task requires searching project memory",
    },
    {
        "patterns": [r"leggi\s+memoria", r"read\s+memory", r"recupera\s+record"],
        "recommended": "aicarmine_project_memory_get",
        "confidence": 0.90,
        "reason": "Task requires reading a memory record",
    },
    # RAG operations
    {
        "patterns": [r"cerca\s+semantico", r"semantic\s+search", r"rag\s+query"],
        "recommended": "aicarmine_rag_context",
        "confidence": 0.93,
        "reason": "Task requires semantic search via RAG",
    },
    {
        "patterns": [r"stato\s+indice", r"index\s+status", r"rag\s+index"],
        "recommended": "aicarmine_rag_index_status",
        "confidence": 0.90,
        "reason": "Task requires RAG index status",
    },
    # Search operations
    {
        "patterns": [r"simboli", r"symbol", r"ctags", r"funzioni\s+definite"],
        "recommended": "aicarmine_repo_ctags_symbols",
        "confidence": 0.92,
        "reason": "Task requires symbol extraction",
    },
    {
        "patterns": [r"ast", r"albero\s+sinottico", r"tree\s+sitter", r"parse"],
        "recommended": "aicarmine_repo_tree_sitter_parse",
        "confidence": 0.90,
        "reason": "Task requires tree-sitter parsing",
    },
    {
        "patterns": [r"ast\s*grep", r"ricerca\s+semantica", r"semantic\s+search"],
        "recommended": "aicarmine_repo_search_ast_grep",
        "confidence": 0.92,
        "reason": "Task requires ast-grep search",
    },
    # Validation operations
    {
        "patterns": [r"shellcheck", r"shell\s+script", r"controllo\s+shell"],
        "recommended": "aicarmine_repo_validate_shellcheck",
        "confidence": 0.95,
        "reason": "Task requires shellcheck validation",
    },
    {
        "patterns": [r"semgrep", r"security\s+scan", r"scansione\s+sicurezza"],
        "recommended": "aicarmine_repo_validate_semgrep",
        "confidence": 0.93,
        "reason": "Task requires semgrep security scan",
    },
    # Agentic loop operations
    {
        "patterns": [r"avvia\s+agentic", r"start\s+agentic", r"lancia\s+task"],
        "recommended": "aicarmine_agentic_loop_run",
        "confidence": 0.90,
        "reason": "Task requires starting agentic loop",
    },
    {
        "patterns": [r"stato\s+agentic", r"agentic\s+status", r"verifica\s+loop"],
        "recommended": "aicarmine_agentic_loop_status",
        "confidence": 0.90,
        "reason": "Task requires agentic loop status",
    },
    # Service state operations
    {
        "patterns": [r"snapshot", r"stato\s+servizi", r"service\s+state", r"ports"],
        "recommended": "aicarmine_service_state_snapshot",
        "confidence": 0.90,
        "reason": "Task requires service state snapshot",
    },
    {
        "patterns": [r"processi", r"process", r"command\s+line"],
        "recommended": "aicarmine_service_state_processes",
        "confidence": 0.90,
        "reason": "Task requires process information",
    },
    {
        "patterns": [r"log\s+file", r"log\s+tail", r"registri"],
        "recommended": "aicarmine_service_state_logs",
        "confidence": 0.90,
        "reason": "Task requires log file tails",
    },
    # SQLite operations
    {
        "patterns": [r"query\s+sqlite", r"sqlite\s+query", r"interroga\s+database"],
        "recommended": "aicarmine_sqlite_readonly_query",
        "confidence": 0.92,
        "reason": "Task requires SQLite query",
    },
    {
        "patterns": [r"schema\s+sqlite", r"sqlite\s+schema", r"struttura\s+database"],
        "recommended": "aicarmine_sqlite_readonly_schema",
        "confidence": 0.92,
        "reason": "Task requires SQLite schema",
    },
    # Local subagent operations
    {
        "patterns": [r"sottomodulo", r"subagent", r"analisi\s+bounded"],
        "recommended": "aicarmine_local_subagent_run_readonly",
        "confidence": 0.88,
        "reason": "Task requires bounded subagent analysis",
    },
    # Repo code operations
    {
        "patterns": [r"valida\s+unidiff", r"validate\s+unidiff", r"controlla\s+diff"],
        "recommended": "aicarmine_repo_code_unidiff_validate",
        "confidence": 0.93,
        "reason": "Task requires unidiff validation",
    },
    {
        "patterns": [r"git\s+apply\s+check", r"apply\s+check"],
        "recommended": "aicarmine_repo_code_git_apply_check",
        "confidence": 0.93,
        "reason": "Task requires git apply check",
    },
]


# ---------------------------------------------------------------------------
# Resolution logic
# ---------------------------------------------------------------------------

def resolve_tool_for_task(task_description: str) -> dict[str, Any]:
    """
    Resolve the best tool for a given task description.

    Returns a dict with:
    - recommended_tool: str
    - confidence: float
    - alternatives: list[str]
    - reasoning: str
    """
    if not task_description:
        return {
            "recommended_tool": None,
            "confidence": 0.0,
            "alternatives": [],
            "reasoning": "Empty task description",
        }

    task_lower = task_description.lower()

    best_match = None
    best_confidence = 0.0

    for pattern_entry in TASK_PATTERNS:
        patterns = pattern_entry.get("patterns", [])
        for pattern in patterns:
            if re.search(pattern, task_lower):
                confidence = pattern_entry.get("confidence", 0.0)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = pattern_entry
                break

    if best_match is None:
        return {
            "recommended_tool": None,
            "confidence": 0.0,
            "alternatives": [],
            "reasoning": "No matching pattern found - use MCP tools/list for discovery",
        }

    recommended = best_match.get("recommended")
    reasoning = best_match.get("reason", "Pattern match")

    # Find alternatives (same category)
    alternatives = _find_alternatives(recommended)

    return {
        "recommended_tool": recommended,
        "confidence": best_confidence,
        "alternatives": alternatives,
        "reasoning": reasoning,
    }


def _find_alternatives(tool_name: str) -> list[str]:
    """Find alternative tools in the same category."""
    # Load symbol reference if available
    if not SYMBOL_REF_PATH.exists():
        return []

    try:
        content = SYMBOL_REF_PATH.read_text(encoding="utf-8")
        ref = json.loads(content)
    except (json.JSONDecodeError, OSError):
        return []

    # Find the category of the recommended tool
    target_category = None
    for entry in ref.get("tool_entries", []):
        if entry.get("tool_name") == tool_name:
            target_category = entry.get("category")
            break

    if target_category is None:
        return []

    # Find alternatives in same category
    alternatives = []
    for entry in ref.get("tool_entries", []):
        if entry.get("category") == target_category and entry.get("tool_name") != tool_name:
            alternatives.append(entry.get("tool_name"))

    return alternatives[:5]  # Limit to 5 alternatives


def main() -> None:
    """CLI interface for symbol resolution."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python symbol_resolution_assistant.py <task_description>")
        sys.exit(1)

    task = " ".join(sys.argv[1:])
    result = resolve_tool_for_task(task)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()