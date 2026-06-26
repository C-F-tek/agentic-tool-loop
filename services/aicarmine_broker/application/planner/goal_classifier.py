"""Goal classification and analysis extracted from planner.py.
These functions handle goal semantic classification, target file/scope detection,
repository analysis detection, and preseed planning decisions.
"""
from __future__ import annotations
from typing import Any
from vulkan_bridge.app import _post_json
def semantic_goal_classification(goal: str) -> dict[str, Any]:
    """Classify the semantic goal into categories (deliverable type, write intent, etc.)."""
    # Lazy import to avoid circular dependency
    from .agentic_v2 import _classify_goal_deliverable
    return _classify_goal_deliverable(goal, repo_analysis=_repo_analysis_goal(goal))
def goal_requires_code_product_report(goal: str) -> bool:
    """Return True if the goal requires producing a code product artifact."""
    classification = semantic_goal_classification(goal)
    return bool(classification.get("must_produce_code_product"))
def goal_has_write_intent(goal: str) -> bool:
    """Return True if the goal has explicit write/apply intent."""
    from .agentic_v2 import goal_requests_apply
    return goal_requests_apply(goal)
def requested_file_limit_from_goal(goal: str, default: int = 0) -> int:
    """Extract the requested file limit from the goal text."""
    from .agentic_v2 import requested_file_limit_from_goal as _inner
    return _inner(goal, default)
def goal_requested_repo_scope(goal: str) -> str:
    """Extract the repo scope requested by the goal."""
    from aicarmine_broker.infrastructure.repo_tools import safe_rel_path
    from aicarmine_broker.config import LAB_REPO
    from .agentic_v2 import goal_requested_repo_scope as _inner
    return _inner(goal, repo_root=LAB_REPO, safe_rel_path=safe_rel_path)
def goal_requests_python_file_review(goal: str) -> bool:
    """Return True if the goal requests Python file review + explanation."""
    low = semantic_goal_low(goal)
    wants_python_files = has_any(low, ("python", ".py", "file py", "files py", "file python"))
    wants_read = has_any(low, ("leggi", "read", "analizza", "analizzare", "descrivi", "dimmi", "serve", "servono"))
    wants_explain = has_any(low, ("comportamento", "funzionamento", "cosa serv", "miglior", "improvement", "describe", "purpose"))
    return wants_python_files and wants_read and wants_explain
def semantic_goal_low(goal: str) -> str:
    """Extract the low-level goal text for keyword matching."""
    from .agentic_v2 import goal_operational_intent_text
    return str(goal_operational_intent_text(goal) or "").lower()
def has_any(text: str, keywords: tuple[str, ...]) -> bool:
    """Return True if any keyword appears in the text (case-insensitive)."""
    low = text.lower() if text else ""
    return any(k in low for k in keywords)
# ---------------------------------------------------------------------------
# Repository analysis detection
# ---------------------------------------------------------------------------
_REPO_REFERENCE_TERMS = (
    "repo", "repository", "progetto", "project", "workspace", "codebase",
    "codice corrente", "current code", "codice nel workspace",
)
_REPO_ANALYSIS_INTENT_TERMS = (
    "analizza", "anlizza", "analisi", "analyze", "analyse", "analysis",
    "inspect", "inspection", "esplora", "scansiona", "struttura", "structure",
    "overview", "mappa", "review", "audit", "ispeziona", "trova", "trovare",
    "cerca", "ricerca",
)
def _repo_reference_mentioned(low: str) -> bool:
    """Return True if the goal mentions a repository reference."""
    return any(term in low for term in _REPO_REFERENCE_TERMS)
def _repo_analysis_intent_mentioned(low: str) -> bool:
    """Return True if the goal contains analysis intent keywords."""
    return any(term in low for term in _REPO_ANALYSIS_INTENT_TERMS)
def _repo_analysis_goal(goal: str) -> bool:
    """Determine whether this is a repository-analysis goal.
    Repository-analysis goals request surface inspection, structure mapping,
    or codebase understanding without explicit write intent.
    """
    from .agentic_v2 import goal_operational_intent_text
    from aicarmine_broker.infrastructure.repo_tools import safe_rel_path
    from aicarmine_broker.config import LAB_REPO
    low = goal_operational_intent_text(goal).lower()
    repo_terms = (
        "analyze the repository", "analizza la repo", "analizza il repo",
        "anlizza la repo", "anlizza il repo", "anlizza la repository",
        "repository structure", "repo structure", "struttura repo",
        "analyze repo", "analisi repo", "structure and content",
        "project inspection", "local project evidence", "workspace code",
        "codice corrente", "current code", "codebase",
        "documentation", "documentazione", "docs", "examples", "diagrams",
        "gpu coordination", "heap pointer", "recovery turns",
        "deferred evidence", "packet_review_only", "gpu1", "gpu0",
        "npu sidecar",
    )
    scoped_terms = (
        "analyze the ", "analyse the ", "analizza ", "analisi ",
        "directory", "cartella", "folder", "path",
    )
    if goal_has_write_intent(goal):
        return False
    if input_error_goal(goal):
        return False
    if any(t in low for t in repo_terms):
        return True
    if _repo_reference_mentioned(low) and _repo_analysis_intent_mentioned(low):
        return True
    # Scoped inspection requests such as "analyze the ai_carmine directory" are
    # repository-analysis goals even if they do not say "repository".
    from .agentic_v2 import goal_requested_repo_scope
    if goal_requested_repo_scope(goal) and any(t in low for t in scoped_terms):
        return True
    return False
def input_error_goal(goal: str) -> bool:
    """Return True if the goal is an input-error diagnostic request."""
    low = semantic_goal_low(goal)
    error_terms = ("input error", "errore input", "debug", "traceback", "exception")
    return any(t in low for t in error_terms)
# ---------------------------------------------------------------------------
# Goal target detection
# ---------------------------------------------------------------------------
def _goal_existing_file_candidates(goal: str) -> list[str]:
    """Extract file path candidates mentioned in the goal."""
    from aicarmine_broker.infrastructure.repo_tools import safe_rel_path
    from aicarmine_broker.config import LAB_REPO
    from .agentic_v2 import extract_existing_goal_paths
    return extract_existing_goal_paths(
        goal,
        repo_root=LAB_REPO,
        safe_rel_path=safe_rel_path,
    )
def _goal_target_file(goal: str) -> str:
    """Return the single target file for this goal, or empty string."""
    candidates = _goal_existing_file_candidates(goal)
    if not candidates:
        return ""
    # Broad repository-analysis goals often enumerate multiple canonical files.
    # Do not collapse those requests to the first incidental file mention.
    if _repo_analysis_goal(goal) and len(candidates) > 1:
        return ""
    return candidates[0]
def _agentic_v2_goal_scope(goal: str, contract: dict[str, Any]) -> str | None:
    """Extract the goal scope (directory/target) from agentic_v2 decision paths."""
    from .agentic_v2 import goal_requested_repo_scope
    result = goal_requested_repo_scope(goal)
    return result if result else None
def _goal_target_scope(goal: str) -> str:
    """Return the target scope (directory) for this goal, or empty string."""
    scope = _agentic_v2_goal_scope(goal, {}) or goal_requested_repo_scope(goal)
    return scope if scope else ""
def _goal_target_kind(goal: str) -> str:
    """Classify the goal target kind: file, directory, repository, or other."""
    if _goal_target_file(goal):
        return "file"
    if _goal_target_scope(goal):
        return "directory"
    if _repo_analysis_goal(goal):
        return "repository"
    return "other"
# ---------------------------------------------------------------------------
# Controller preseed planning
# ---------------------------------------------------------------------------
SCOPED_CONCRETE_READ_TARGET = 10
REPO_CONCRETE_READ_TARGET = 20
_NAMED_READ_PRIORITY: dict[str, int] = {
    "agents.md": 0,
    "readme.md": 1,
}
_INITAL_DOC_NAME_PRIORITY: dict[str, int] = {
    "AGENTS.md": 0,
    "README.md": 1,
}
_GENERIC_READABLE_SUFFIXES = (
    ".bat", ".c", ".cfg", ".cmd", ".cpp", ".cs", ".csv", ".go", ".h",
    ".ini", ".java", ".js", ".json", ".jsx", ".kt", ".md", ".ps1", ".py",
    ".rs", ".sh", ".toml", ".ts", ".tsx", ".txt", ".yaml", ".yml",
)
def _should_preseed_root_surface(goal: str, original_args: dict[str, Any]) -> bool:
    """Decide whether the controller should expose root surface evidence first.
    This is deterministic evidence collection for clear, sparse repo-analysis
    goals. It does not choose the next planner action and does not finalize.
    """
    args = original_args if isinstance(original_args, dict) else {}
    requested_function = str(args.get("function") or "").strip()
    if requested_function == "repo_tree":
        return True
    if input_error_goal(goal) or goal_has_write_intent(goal):
        return False
    low = semantic_goal_low(goal)
    generic_repo_terms = (
        "analizza la repo", "analizza il repo", "analizza la repository",
        "anlizza la repo", "anlizza il repo", "anlizza la repository",
        "analisi repo", "analisi della repo", "analisi della repository",
        "analyze repo", "analyze the repo", "analyze the repository",
        "repository analysis", "repo analysis", "repo structure",
        "repository structure", "struttura repo", "struttura della repo",
        "struttura della repository", "project structure", "surface project",
        "suggerimenti implementativi", "implementation suggestions",
        "dai suggerimenti", "find problems", "trova problemi",
    )
    return any(term in low for term in generic_repo_terms) or (
        _repo_reference_mentioned(low) and _repo_analysis_intent_mentioned(low)
    )
def _controller_preseed_plan(goal: str, original_args: dict[str, Any]) -> dict[str, Any] | None:
    """Generate a preseed plan based on goal target type."""
    from aicarmine_broker.config import AGENTIC_PLANNER_NUM_CTX
    target_file = _goal_target_file(goal)
    if target_file:
        return {
            "event": "controller_preseed_file_surface",
            "result_event": "controller_preseed_file_surface_result",
            "tool": "repo_read",
            "arguments": {"path": target_file, "max_chars": _single_file_prompt_read_chars()},
            "reason": "explicit_file_request_needs_file_surface",
            "artifact_suffix": "file_surface-repo_read",
        }
    target_scope = _goal_target_scope(goal)
    if target_scope:
        return {
            "event": "controller_preseed_scope_surface",
            "result_event": "controller_preseed_scope_surface_result",
            "tool": "repo_list_files",
            "arguments": {"path": target_scope, "limit": 120},
            "reason": "explicit_directory_request_needs_scope_surface",
            "artifact_suffix": "scope_surface-repo_list_files",
        }
    if _should_preseed_root_surface(goal, original_args):
        return {
            "event": "controller_preseed_root_surface",
            "result_event": "controller_preseed_root_surface_result",
            "tool": "repo_tree",
            "arguments": {"path": ".", "max_depth": 2, "max_files": 300},
            "reason": "generic_repo_request_needs_root_surface",
            "artifact_suffix": "root_surface-repo_tree",
            "dynamic_initial_orientation": True,
        }
    return None
def _planner_prompt_budget_value(default: int = 24000) -> int:
    """Get the effective prompt budget value."""
    try:
        from aicarmine_broker.config import AGENTIC_PLANNER_PROMPT_CHAR_BUDGET
        return int(AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or default)
    except Exception:
        return int(default)
def _single_file_prompt_read_chars() -> int:
    """Calculate optimal single-file read size based on prompt budget."""
    budget = _planner_prompt_budget_value()
    return max(2000, min(120000, budget // 4))
def _multi_file_prompt_read_chars() -> int:
    """Calculate optimal multi-file read size based on prompt budget."""
    budget = _planner_prompt_budget_value()
    return max(2000, min(64000, budget // 8))
def _controller_preplanner_rag_query_plan(goal: str) -> dict[str, Any]:
    """Generate a RAG query plan for preplanner context retrieval."""
    from aicarmine_broker.config import (
        AGENTIC_PLANNER_NUM_CTX,
        AGENTIC_PLANNER_STEP_TIMEOUT,
        OLLAMA_KEEP_ALIVE,
        PLANNER_MODEL,
        PLANNER_URL,
    )
    from .agentic_v2 import controller_preplanner_rag_query_plan
    return controller_preplanner_rag_query_plan(
        goal,
        post_json=_post_json,
        planner_url=PLANNER_URL,
        planner_model=PLANNER_MODEL,
        keep_alive=OLLAMA_KEEP_ALIVE,
        num_ctx=AGENTIC_PLANNER_NUM_CTX,
        timeout=AGENTIC_PLANNER_STEP_TIMEOUT,
    )
def _controller_preplanner_rag_preseed_plan(
    goal: str,
    original_args: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any], list[dict[str, Any]]]:
    """Generate a RAG preseed plan with file surface evidence."""
    from aicarmine_broker.infrastructure.repo_tools import safe_rel_path
    from aicarmine_broker.config import LAB_REPO
    from .agentic_v2 import controller_preplanner_rag_preseed_plan
    return controller_preplanner_rag_preseed_plan(
        goal,
        original_args,
        repo_root=LAB_REPO,
        safe_rel_path=safe_rel_path,
        named_read_priority=_NAMED_READ_PRIORITY,
        generic_readable_suffixes=_GENERIC_READABLE_SUFFIXES,
        multi_file_prompt_read_chars=_multi_file_prompt_read_chars(),
    )
def _controller_file_code_product_orientation_preseed_plan(goal: str) -> dict[str, Any] | None:
    """Preseed plan for file code product orientation (needs repo_tree)."""
    if not _goal_target_file(goal) or not goal_requires_code_product_report(goal):
        return None
    return {
        "event": "controller_preseed_file_code_product_orientation",
        "result_event": "controller_preseed_file_code_product_orientation_result",
        "tool": "repo_tree",
        "arguments": {"path": ".", "max_depth": 2, "max_files": 300},
        "reason": "file_code_product_request_needs_dynamic_repo_orientation",
        "artifact_suffix": "file_code_product_orientation-repo_tree",
        "dynamic_initial_orientation": True,
    }
# ---------------------------------------------------------------------------
# Memory target key
# ---------------------------------------------------------------------------
def _controller_memory_target_key(goal: str, contract: dict[str, Any] | None = None) -> str:
    """Generate the memory storage key for this goal."""
    from aicarmine_broker.infrastructure.repo_tools import repo_rel_token
    contract = contract if isinstance(contract, dict) else {}
    target_file = str(contract.get("resolved_goal_file") or _goal_target_file(goal) or "")
    if target_file:
        return "file:" + repo_rel_token(target_file)
    target_scope = str(contract.get("resolved_goal_scope") or _goal_target_scope(goal) or "")
    if target_scope:
        return "scope:" + repo_rel_token(target_scope)
    return "repo:root" if _repo_analysis_goal(goal) else "goal:general"
# ---------------------------------------------------------------------------
# Repository path helpers
# ---------------------------------------------------------------------------
def repo_existing_file(path: str) -> bool:
    """Check if a file exists in the repository."""
    from aicarmine_broker.infrastructure.repo_tools import safe_rel_path
    from aicarmine_broker.config import LAB_REPO
    try:
        rel = safe_rel_path(path)
        full = (LAB_REPO / rel).resolve(strict=False)
        full.relative_to(LAB_REPO)
        return full.exists() and full.is_file()
    except Exception:
        return False
def repo_existing_dir(path: str) -> bool:
    """Check if a directory exists in the repository."""
    from aicarmine_broker.infrastructure.repo_tools import safe_rel_path
    from aicarmine_broker.config import LAB_REPO
    try:
        rel = safe_rel_path(path)
        full = (LAB_REPO / rel).resolve(strict=False)
        full.relative_to(LAB_REPO)
        return full.exists() and full.is_dir()
    except Exception:
        return False
def extract_existing_goal_path(goal: str) -> str:
    """Extract the first existing file path from goal text."""
    candidates = _goal_existing_file_candidates(goal)
    return candidates[0] if candidates else ""
# ---------------------------------------------------------------------------
# Local aliases for backward compatibility with planner.py imports
# ---------------------------------------------------------------------------
semantic_goal_classification = semantic_goal_classification
goal_requires_code_product_report = goal_requires_code_product_report
goal_has_write_intent = goal_has_write_intent
requested_file_limit_from_goal = requested_file_limit_from_goal
goal_requested_repo_scope = goal_requested_repo_scope
goal_requests_python_file_review = goal_requests_python_file_review
_repo_analysis_goal = _repo_analysis_goal
_goal_target_file = _goal_target_file
_goal_target_scope = _goal_target_scope
_goal_target_kind = _goal_target_kind
_controller_memory_target_key = _controller_memory_target_key
_controller_preseed_plan = _controller_preseed_plan
_controller_preplanner_rag_query_plan = _controller_preplanner_rag_query_plan
_controller_preplanner_rag_preseed_plan = _controller_preplanner_rag_preseed_plan
_controller_file_code_product_orientation_preseed_plan = _controller_file_code_product_orientation_preseed_plan
_single_file_prompt_read_chars = _single_file_prompt_read_chars
_multi_file_prompt_read_chars = _multi_file_prompt_read_chars
_should_preseed_root_surface = _should_preseed_root_surface
_planner_prompt_budget_value = _planner_prompt_budget_value
repo_existing_file = repo_existing_file
repo_existing_dir = repo_existing_dir
extract_existing_goal_path = extract_existing_goal_path
__all__ = [
    "semantic_goal_classification",
    "goal_requires_code_product_report",
    "goal_has_write_intent",
    "requested_file_limit_from_goal",
    "goal_requested_repo_scope",
    "goal_requests_python_file_review",
    "_repo_analysis_goal",
    "_goal_target_file",
    "_goal_target_scope",
    "_goal_target_kind",
    "_controller_memory_target_key",
    "_controller_preseed_plan",
    "_controller_preplanner_rag_query_plan",
    "_controller_preplanner_rag_preseed_plan",
    "_controller_file_code_product_orientation_preseed_plan",
    "_single_file_prompt_read_chars",
    "_multi_file_prompt_read_chars",
    "_should_preseed_root_surface",
    "_planner_prompt_budget_value",
    "repo_existing_file",
    "repo_existing_dir",
    "_classify_goal_deliverable",
    "extract_existing_goal_path",
]