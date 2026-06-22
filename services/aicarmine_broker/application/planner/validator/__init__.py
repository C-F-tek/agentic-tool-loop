"""
__init__.py
================
Re-export public validator modules for the validator refactor.

This file ensures that all validator modules are properly organized and accessible
in the same directory structure as specified in the piano moduli.

Piano Moduli:
path_utils.py — utilità pure sui path (normalizzazione, validazione, scope)
contract_utils.py — lettura/scrittura del contratto (allowlist, coverage, latch)
rewrite_latch.py — macchina a stati del latch finale (block/rewrite/gap)
validators/tool_validators.py — validazione argomenti per singolo tool
validators/final_validators.py — validazione action=final
validators/block_validators.py — validazione action=block
validate_decision.py — orchestratore pubblico (entry point, firma invariata)
__init__.py — re-export pubblico
"""

# Import and re-export all validator modules
from .path_utilis import (  # type: ignore
    is_concrete_repo_path,
    coalesce_repo_read_paths,
    collect_repo_paths,
    is_concrete_search_query,
    is_prose_or_metric_token,
)

from .contract_utils import (  # type: ignore
    known_contract_repo_paths,
    known_contract_repo_dirs,
    final_quality_repo_read_allowlist,
    minimum_read_coverage_contract,
    is_coverage_required,
    is_coverage_satisfied,
    missing_coverage_owner_paths,
)

from .rewrite_latch import (  # type: ignore
    coerce_latch_state,
    next_latch_state,
    escalate_terminal_block_state,
    clear_terminal_block_state,
)

from .action_validators import (  # type: ignore
    validate_final_action,
    validate_block_action,
    validate_tool_arguments,
    validate_scratchpad_write,
)

from .validate_decision import (  # type: ignore
    validate_planner_decision_against_evidence,
    _normalize_terminal_planner_decision,
    _list_or_empty,
    _repo_path_is_concrete,
    _coalesce_repo_read_paths,
    _final_quality_repo_read_allowlist,
    _next_final_rewrite_latch,
    _escalate_final_terminal_block_state,
    _clear_final_terminal_block_state,
    _collect_repo_paths,
    _known_contract_repo_paths,
    _known_contract_repo_dirs,
    _handle_final_action,
    _handle_block_action,
    _enforce_rewrite_lane,
)

# Define public API
__all__ = [
    # path_utils
    "is_concrete_repo_path",
    "coalesce_repo_read_paths",
    "collect_repo_paths",
    "is_concrete_search_query",
    "is_prose_or_metric_token",
    
    # contract_utils
    "known_contract_repo_paths",
    "known_contract_repo_dirs",
    "final_quality_repo_read_allowlist",
    "minimum_read_coverage_contract",
    "is_coverage_required",
    "is_coverage_satisfied",
    "missing_coverage_owner_paths",
    
    # rewrite_latch
    "coerce_latch_state",
    "next_latch_state",
    "escalate_terminal_block_state",
    "clear_terminal_block_state",
    
    # action_validators
    "validate_final_action",
    "validate_block_action",
    "validate_tool_arguments",
    "validate_scratchpad_write",
    
    # validate_decision
    "validate_planner_decision_against_evidence",
    "_normalize_terminal_planner_decision",
    "_list_or_empty",
    "_repo_path_is_concrete",
    "_coalesce_repo_read_paths",
    "_final_quality_repo_read_allowlist",
    "_next_final_rewrite_latch",
    "_escalate_final_terminal_block_state",
    "_clear_final_terminal_block_state",
    "_collect_repo_paths",
    "_known_contract_repo_paths",
    "_known_contract_repo_dirs",
    "_handle_final_action",
    "_handle_block_action",
    "_enforce_rewrite_lane",
]