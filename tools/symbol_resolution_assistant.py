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
    # ===== REPOSITORY OPERATIONS (aicarmine-codex-app) =====
    {
        "patterns": [r"leggi\s+il\s+contenuto\s+di", r"read\s+content\s+of", r"apri\s+file", r"open\s+file", r"leggi\s+file"],
        "recommended": "aicarmine_repo_read",
        "confidence": 0.95,
        "reason": "Task requires reading file contents",
    },
    {
        "patterns": [r"elenca\s+file", r"list\s+files", r"cosa\s+ci\s+sono", r"what\s+in\s+directory", r"elenca"],
        "recommended": "aicarmine_repo_list_files",
        "confidence": 0.92,
        "reason": "Task requires listing files in directory",
    },
    {
        "patterns": [r"albero\s+directory", r"directory\s+tree", r"struttura\s+progetto", r"tree\s+view"],
        "recommended": "aicarmine_repo_tree",
        "confidence": 0.90,
        "reason": "Task requires directory tree view",
    },
    {
        "patterns": [r"verifica\s+stato", r"check\s+status", r"commit\s+attuale", r"current\s+commit", r"stato\s+repo"],
        "recommended": "aicarmine_repo_status",
        "confidence": 0.90,
        "reason": "Task requires checking repository status",
    },
    {
        "patterns": [r"capacit[àa]\s+repo", r"repo\s+capabilities", r"capabilities"],
        "recommended": "aicarmine_repo_capabilities",
        "confidence": 0.90,
        "reason": "Task requires repository capabilities",
    },
    # ===== SEARCH OPERATIONS (aicarmine-repo-search-det) =====
    {
        "patterns": [r"cerca\s+nel\s+codice", r"search\s+code", r"trova\s+funzione", r"find\s+function", r"grep"],
        "recommended": "aicarmine_repo_search_rg",
        "confidence": 0.90,
        "reason": "Task requires searching in code (ripgrep)",
    },
    {
        "patterns": [r"cerca\s+per\s+pattern", r"find\s+by\s+pattern", r"trova\s+file", r"fd\s+search"],
        "recommended": "aicarmine_repo_search_fd",
        "confidence": 0.90,
        "reason": "Task requires file discovery by pattern (fd)",
    },
    {
        "patterns": [r"ast\s*grep", r"ricerca\s+semantica", r"semantic\s+search", r"ast\s+search"],
        "recommended": "aicarmine_repo_search_ast_grep",
        "confidence": 0.92,
        "reason": "Task requires ast-grep semantic search",
    },
    {
        "patterns": [r"simboli", r"symbol", r"ctags", r"funzioni\s+definite", r"definizioni", r"classes"],
        "recommended": "aicarmine_repo_search_ctags",
        "confidence": 0.92,
        "reason": "Task requires symbol extraction (ctags)",
    },
    {
        "patterns": [r"tree\s*sitter", r"parse", r"albero\s+ast", r"ast\s+parse"],
        "recommended": "aicarmine_repo_search_tree_sitter_parse",
        "confidence": 0.90,
        "reason": "Task requires tree-sitter parsing",
    },
    {
        "patterns": [r"\bjq\b", r"json\s+query", r"query\s+json"],
        "recommended": "aicarmine_repo_search_jq",
        "confidence": 0.90,
        "reason": "Task requires JSON query (jq)",
    },
    # ===== GIT OPERATIONS (aicarmine-git-readonly) =====
    {
        "patterns": [r"log\s+git", r"commit\s+recenti", r"storia\s+repository", r"git\s+log", r"commits"],
        "recommended": "aicarmine_git_readonly_log",
        "confidence": 0.93,
        "reason": "Task requires git log",
    },
    {
        "patterns": [r"diff\s+git", r"git\s+diff", r"cambiamenti", r"diff\s+files"],
        "recommended": "aicarmine_git_readonly_diff",
        "confidence": 0.92,
        "reason": "Task requires git diff",
    },
    {
        "patterns": [r"blame", r"chi\s+ha\s+scritto", r"author\s+di\s+linea", r"git\s+blame"],
        "recommended": "aicarmine_git_readonly_blame",
        "confidence": 0.93,
        "reason": "Task requires git blame",
    },
    {
        "patterns": [r"mostra\s+commit", r"show\s+commit", r"dettagli\s+commit", r"git\s+show"],
        "recommended": "aicarmine_git_readonly_show",
        "confidence": 0.92,
        "reason": "Task requires showing a commit",
    },
    {
        "patterns": [r"branch\s+compare", r"confronta\s+branch", r"git\s+branch"],
        "recommended": "aicarmine_git_readonly_branch_compare",
        "confidence": 0.90,
        "reason": "Task requires branch comparison",
    },
    # ===== JOB ARTIFACT OPERATIONS (aicarmine-job-artifact) =====
    {
        "patterns": [r"stato\s+job", r"job\s+status", r"verifica\s+esecuzione", r"lista\s+job"],
        "recommended": "aicarmine_job_artifact_list_jobs",
        "confidence": 0.90,
        "reason": "Task requires job status/listing",
    },
    {
        "patterns": [r"job\s+summary", r"job\s+detail", r"riepilogo\s+job"],
        "recommended": "aicarmine_job_artifact_summary",
        "confidence": 0.90,
        "reason": "Task requires job summary",
    },
    {
        "patterns": [r"eventi\s+job", r"job\s+events", r"log\s+esecuzione", r"job\s+log"],
        "recommended": "aicarmine_job_artifact_events",
        "confidence": 0.92,
        "reason": "Task requires job events",
    },
    {
        "patterns": [r"risultato\s+job", r"job\s+result", r"output\s+finale", r"final\s+result"],
        "recommended": "aicarmine_job_artifact_final",
        "confidence": 0.92,
        "reason": "Task requires job final result",
    },
    {
        "patterns": [r"tool\s+results", r"risultati\s+tool", r"tool\s+output"],
        "recommended": "aicarmine_job_artifact_tool_results",
        "confidence": 0.90,
        "reason": "Task requires job tool results",
    },
    {
        "patterns": [r"job\s+subturns", r"subturn\s+events", r"support\s+turns"],
        "recommended": "aicarmine_job_artifact_subturns",
        "confidence": 0.88,
        "reason": "Task requires job subturns",
    },
    {
        "patterns": [r"job\s+rejections", r"rejection\s+events", r"planner\s+rejection"],
        "recommended": "aicarmine_job_artifact_rejections",
        "confidence": 0.90,
        "reason": "Task requires job rejections",
    },
    {
        "patterns": [r"planner\s+payload", r"planner\s+step", r"planner\s+input"],
        "recommended": "aicarmine_job_artifact_planner_payload",
        "confidence": 0.90,
        "reason": "Task requires planner payload",
    },
    # ===== JOB VIEW OPERATIONS (aicarmine-job-view) =====
    {
        "patterns": [r"job\s+view", r"render\s+job", r"visualizza\s+job", r"job\s+html"],
        "recommended": "aicarmine_job_view_render",
        "confidence": 0.90,
        "reason": "Task requires job view rendering",
    },
    # ===== MEMORY OPERATIONS (aicarmine-project-memory) =====
    {
        "patterns": [r"cerca\s+memoria", r"search\s+memory", r"project\s+memory", r"memory\s+search"],
        "recommended": "aicarmine_project_memory_search",
        "confidence": 0.92,
        "reason": "Task requires searching project memory",
    },
    {
        "patterns": [r"leggi\s+memoria", r"read\s+memory", r"recupera\s+record", r"memory\s+get"],
        "recommended": "aicarmine_project_memory_get",
        "confidence": 0.90,
        "reason": "Task requires reading a memory record",
    },
    {
        "patterns": [r"scrivi\s+memoria", r"write\s+memory", r"salva\s+memoria", r"memory\s+upsert"],
        "recommended": "aicarmine_project_memory_upsert_verified",
        "confidence": 0.90,
        "reason": "Task requires writing a memory record",
    },
    {
        "patterns": [r"obsoleta\s+memoria", r"stale\s+memory", r"memory\s+stale", r"invalida\s+memoria"],
        "recommended": "aicarmine_project_memory_mark_stale",
        "confidence": 0.90,
        "reason": "Task requires marking memory as stale",
    },
    {
        "patterns": [r"sostituisci\s+memoria", r"supersede\s+memory", r"memory\s+replace"],
        "recommended": "aicarmine_project_memory_supersede",
        "confidence": 0.90,
        "reason": "Task requires superseding a memory record",
    },
    # ===== RAG OPERATIONS (aicarmine-rag) =====
    {
        "patterns": [r"cerca\s+semantico", r"semantic\s+search", r"rag\s+query", r"rag\s+search"],
        "recommended": "aicarmine_rag_context",
        "confidence": 0.93,
        "reason": "Task requires semantic search via RAG",
    },
    {
        "patterns": [r"stato\s+indice", r"index\s+status", r"rag\s+index", r"rag\s+health"],
        "recommended": "aicarmine_rag_index_status",
        "confidence": 0.90,
        "reason": "Task requires RAG index status",
    },
    {
        "patterns": [r"ricostruisci\s+indice", r"reindex", r"aggiorna\s+indice", r"rag\s+reindex"],
        "recommended": "aicarmine_rag_reindex",
        "confidence": 0.90,
        "reason": "Task requires RAG reindexing",
    },
    # ===== VALIDATION OPERATIONS (aicarmine-repo-validate) =====
    {
        "patterns": [r"ruff", r"lint", r"linter", r"ruff\s+check"],
        "recommended": "aicarmine_repo_validate_ruff",
        "confidence": 0.95,
        "reason": "Task requires ruff linting",
    },
    {
        "patterns": [r"pyright", r"type\s*check", r"controllo\s+tipi", r"pyright\s+check"],
        "recommended": "aicarmine_repo_validate_pyright",
        "confidence": 0.95,
        "reason": "Task requires pyright type checking",
    },
    {
        "patterns": [r"test", r"pytest", r"esecuzione\s+test", r"run\s+test", r"pytest\s+run"],
        "recommended": "aicarmine_repo_validate_pytest",
        "confidence": 0.93,
        "reason": "Task requires running tests",
    },
    {
        "patterns": [r"shellcheck", r"shell\s+script", r"controllo\s+shell", r"shell\s+lint"],
        "recommended": "aicarmine_repo_validate_shellcheck",
        "confidence": 0.95,
        "reason": "Task requires shellcheck validation",
    },
    {
        "patterns": [r"semgrep", r"security\s+scan", r"scansione\s+sicurezza", r"semgrep\s+scan"],
        "recommended": "aicarmine_repo_validate_semgrep",
        "confidence": 0.93,
        "reason": "Task requires semgrep security scan",
    },
    {
        "patterns": [r"diff\s+check", r"valida\s+diff", r"diffcheck", r"git\s+diffcheck"],
        "recommended": "aicarmine_repo_validate_diffcheck",
        "confidence": 0.90,
        "reason": "Task requires git diff --check",
    },
    {
        "patterns": [r"probe", r"probe\s+run", r"contract\s+probe", r"verifica\s+contract"],
        "recommended": "aicarmine_repo_validate_probe_run",
        "confidence": 0.88,
        "reason": "Task requires running a probe profile",
    },
    # ===== SQLITE OPERATIONS (aicarmine-sqlite-readonly) =====
    {
        "patterns": [r"query\s+sqlite", r"sqlite\s+query", r"interroga\s+database", r"db\s+query"],
        "recommended": "aicarmine_sqlite_readonly_query",
        "confidence": 0.92,
        "reason": "Task requires SQLite query",
    },
    {
        "patterns": [r"schema\s+sqlite", r"sqlite\s+schema", r"struttura\s+database", r"db\s+schema"],
        "recommended": "aicarmine_sqlite_readonly_schema",
        "confidence": 0.92,
        "reason": "Task requires SQLite schema",
    },
    {
        "patterns": [r"lista\s+database", r"list\s+database", r"sqlite\s+databases", r"databases"],
        "recommended": "aicarmine_sqlite_readonly_list_databases",
        "confidence": 0.90,
        "reason": "Task requires listing SQLite databases",
    },
    # ===== REPO CODE OPERATIONS (aicarmine-repo-code) =====
    {
        "patterns": [r"applica\s+patch", r"apply\s+patch", r"scrivi\s+file", r"write\s+file", r"apply\s+code"],
        "recommended": "aicarmine_repo_code_apply_patch",
        "confidence": 0.93,
        "reason": "Task requires applying code patch (write operation)",
    },
    {
        "patterns": [r"proponi\s+modifica", r"propose\s+edit", r"suggerisci\s+cambiamento", r"code\s+edit"],
        "recommended": "aicarmine_repo_code_propose_edit",
        "confidence": 0.92,
        "reason": "Task requires proposing code edit",
    },
    {
        "patterns": [r"valida\s+unidiff", r"validate\s+unidiff", r"controlla\s+diff", r"unidiff"],
        "recommended": "aicarmine_repo_code_unidiff_validate",
        "confidence": 0.93,
        "reason": "Task requires unidiff validation",
    },
    {
        "patterns": [r"git\s+apply\s+check", r"apply\s+check", r"verify\s+patch"],
        "recommended": "aicarmine_repo_code_git_apply_check",
        "confidence": 0.93,
        "reason": "Task requires git apply check",
    },
    # ===== AGENTIC LOOP OPERATIONS (aicarmine-agentic-loop-client) =====
    {
        "patterns": [r"avvia\s+agentic", r"start\s+agentic", r"lancia\s+task", r"agentic\s+run", r"avvia\s+loop"],
        "recommended": "aicarmine_agentic_loop_run",
        "confidence": 0.90,
        "reason": "Task requires starting agentic loop",
    },
    {
        "patterns": [r"stato\s+agentic", r"agentic\s+status", r"verifica\s+loop", r"loop\s+status"],
        "recommended": "aicarmine_agentic_loop_status",
        "confidence": 0.90,
        "reason": "Task requires agentic loop status",
    },
    {
        "patterns": [r"risultato\s+agentic", r"agentic\s+result", r"risultato\s+loop", r"loop\s+result"],
        "recommended": "aicarmine_agentic_loop_result",
        "confidence": 0.90,
        "reason": "Task requires agentic loop result",
    },
    {
        "patterns": [r"avvia\s+broker", r"ensure\s+broker", r"start\s+broker", r"broker\s+run"],
        "recommended": "aicarmine_agentic_loop_ensure_broker",
        "confidence": 0.90,
        "reason": "Task requires ensuring broker is running",
    },
    {
        "patterns": [r"avvia\s+reranker", r"ensure\s+reranker", r"start\s+reranker", r"reranker\s+ready"],
        "recommended": "aicarmine_agentic_loop_ensure_reranker",
        "confidence": 0.90,
        "reason": "Task requires ensuring reranker is ready",
    },
    # ===== LOCAL SUBAGENT OPERATIONS (aicarmine-local-subagent) =====
    {
        "patterns": [r"sottomodulo", r"subagent", r"analisi\s+bounded", r"bounded\s+analysis", r"subagent\s+run"],
        "recommended": "aicarmine_local_subagent_run_readonly",
        "confidence": 0.88,
        "reason": "Task requires bounded subagent analysis",
    },
    # ===== SERVICE STATE OPERATIONS (aicarmine-codex-ops) =====
    {
        "patterns": [r"snapshot", r"stato\s+servizi", r"service\s+state", r"ports", r"service\s+snapshot"],
        "recommended": "aicarmine_service_state_snapshot",
        "confidence": 0.90,
        "reason": "Task requires service state snapshot",
    },
    {
        "patterns": [r"processi", r"process", r"command\s+line", r"running\s+process", r"service\s+ports"],
        "recommended": "aicarmine_service_state_processes",
        "confidence": 0.90,
        "reason": "Task requires process information",
    },
    {
        "patterns": [r"log\s+file", r"log\s+tail", r"registri", r"service\s+logs", r"log\s+servizi"],
        "recommended": "aicarmine_service_state_logs",
        "confidence": 0.90,
        "reason": "Task requires log file tails",
    },
    {
        "patterns": [r"inventario\s+mcp", r"mcp\s+inventory", r"mcp\s+probe", r"probe\s+mcp"],
        "recommended": "aicarmine_mcp_inventory_probe",
        "confidence": 0.90,
        "reason": "Task requires MCP inventory probe",
    },
    # ===== REPO STATE OPERATIONS (aicarmine-repo-state) =====
    {
        "patterns": [r"stato\s+repo", r"repo\s+status", r"repo\s+state", r"branch\s+info"],
        "recommended": "aicarmine_repo_state_status",
        "confidence": 0.90,
        "reason": "Task requires repo state status",
    },
    {
        "patterns": [r"capacit[àa]\s+repo", r"repo\s+capabilities", r"repo\s+state\s+capabilities"],
        "recommended": "aicarmine_repo_state_capabilities",
        "confidence": 0.90,
        "reason": "Task requires repo state capabilities",
    },
    # ===== HEALTH CHECKS =====
    {
        "patterns": [r"health", r"salute", r"check", r"verifica\s+salute", r"stato\s+mcp"],
        "recommended": "aicarmine_bridge_health",
        "confidence": 0.85,
        "reason": "Task requires health check",
    },
    # ===== WILY OPERATIONS (aicarmine-wily) =====
    {
        "patterns": [r"\bwily\b", r"\bcomplexity\b", r"\bcyclomatic\b", r"\bradon\b", r"\bcomplessità\b", r"\bcomplex\b"],
        "recommended": "wily_complexity",
        "confidence": 0.93,
        "reason": "Task requires cyclomatic complexity analysis (Wily)",
    },
    {
        "patterns": [r"maintainability", r"mantenibilit[àa]", r"maintainability\s+index", r"indice\s+mantenibilit[àa]"],
        "recommended": "wily_maintainability",
        "confidence": 0.93,
        "reason": "Task requires maintainability index (Wily)",
    },
    {
        "patterns": [r"wily\s+list", r"python\s+files", r"py\s+files", r"elenca\s+python"],
        "recommended": "wily_list_files",
        "confidence": 0.90,
        "reason": "Task requires listing Python files for Wily analysis",
    },
    {
        "patterns": [r"wily\s+report", r"complexity\s+report", r"rapporto\s+complessit[àa]"],
        "recommended": "wily_report",
        "confidence": 0.90,
        "reason": "Task requires full Wily complexity report",
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