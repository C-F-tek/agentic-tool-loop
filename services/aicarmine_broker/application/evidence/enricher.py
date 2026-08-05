"""Evidence contract enricher for agentic v2."""

from __future__ import annotations

import json
from typing import Any

from ...config import (
    AGENTIC_PLANNER_NUM_CTX,
    AGENTIC_PLANNER_NUM_CTX_CAP,
    AGENTIC_PLANNER_STEP_TIMEOUT,
    OLLAMA_KEEP_ALIVE,
    PLANNER_MODEL,
    PLANNER_URL,
)


def _list_or_empty(value: Any) -> list:
    return value if isinstance(value, list) else []


def _dict_or_empty(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _prompt_clip_value(value: Any, *, text_limit: int = 1600, list_limit: int = 6) -> Any:
    """Clip a value for prompt usage."""
    if isinstance(value, dict):
        return {k: _prompt_clip_value(v, text_limit=text_limit, list_limit=list_limit) for k, v in list(value.items())[:list_limit]}
    if isinstance(value, list):
        return [_prompt_clip_value(item, text_limit=text_limit, list_limit=list_limit) for item in value[:list_limit]]
    if isinstance(value, str):
        return value[:text_limit]
    return value


def _prompt_clip_text(text: str, limit: int = 500) -> str:
    """Clip text to a limit."""
    return text[:limit] if text else ""


class EvidenceContractEnricher:
    """Arricchisce il contratto evidenze per agentic v2."""

    def enrich(
        self,
        result: dict[str, Any],
        goal: str,
        decision: dict[str, Any],
        validation: dict[str, Any],
    ) -> dict[str, Any]:
        """Arricchisce il contratto evidenze."""
        if not isinstance(result, dict):
            return {}

        contract = validation.get("evidence_contract") if isinstance(validation.get("evidence_contract"), dict) else {}
        violations = validation.get("violations") if isinstance(validation.get("violations"), list) else []

        enriched: dict[str, Any] = {
            "goal": str(goal or ""),
            "rejected_decision": decision,
            "violations": violations,
            "contract": contract,
        }

        required_next_tool_call = decision.get("required_next_tool_call") if isinstance(decision.get("required_next_tool_call"), dict) else {}
        if required_next_tool_call:
            enriched["required_next_tool_call"] = required_next_tool_call

        return enriched

    def successful_read_paths(self, result: dict[str, Any]) -> list[str]:
        """Estrae i percorsi di lettura riuscita."""
        paths: list[str] = []
        for key in ("successful_repo_read_paths", "verified_content_reads"):
            for item in self._path_items(result.get(key)):
                token = self._repo_path_token(item)
                if token:
                    paths.append(token)
        return paths

    def _path_items(self, value: Any) -> list[Any]:
        if isinstance(value, dict):
            items = value.get("items")
            return items if isinstance(items, list) else []
        if isinstance(value, list):
            return value
        return []

    def _repo_path_token(self, value: Any) -> str:
        if isinstance(value, dict):
            value = value.get("path") or value.get("source_path") or ""
        token = str(value or "").strip().replace("\\", "/")
        while token.startswith("./"):
            token = token[2:]
        return token

    def agentic_v2_enrich_evidence_contract(
        self,
        contract: dict[str, Any],
        goal: str,
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Wrap _agentic_v2_enrich_evidence_contract logic for evidence enrichment."""
        from ...planner import (
            _agentic_v2_goal_scope,
            _agentic_v2_repo_list_rows,
            _agentic_v2_successful_read_paths,
            _dynamic_read_candidate_paths,
            _path_under_scope,
        )
        
        if not isinstance(contract, dict):
            contract = {}
        history = history if isinstance(history, list) else []
        scope = _agentic_v2_goal_scope(goal, contract)
        list_rows = _agentic_v2_repo_list_rows(history)
        successful_reads = _agentic_v2_successful_read_paths(history)

        known_all: list[str] = []
        for row in list_rows:
            for p in row.get("paths") or []:
                if p not in known_all:
                    known_all.append(p)

        in_scope: list[str] = []
        if scope:
            for p in known_all:
                if _path_under_scope(p, scope) and p not in in_scope:
                    in_scope.append(p)

        latest_in_scope = next((row for row in reversed(list_rows) if scope and _path_under_scope(row.get("path") or ".", scope)), None)
        latest_any = list_rows[-1] if list_rows else None
        already_read = set(successful_reads)
        unread_in_scope = _dynamic_read_candidate_paths(in_scope, read_ok=already_read, target_scope=scope)

        contract["resolved_goal_scope"] = scope or contract.get("resolved_goal_scope")
        contract["path_aliases"] = {"ai_carmine": "ia_carmine"} if scope == "ia_carmine" else contract.get("path_aliases", {})
        contract["repo_list_files_evidence"] = [
            {k: v for k, v in {
                "step": row.get("step"),
                "path": row.get("path"),
                "total_matches": row.get("total_matches"),
                "limit": row.get("limit"),
                "truncated": row.get("truncated"),
                "paths_preview": (row.get("paths") or [])[:20],
            }.items() if v not in (None, "", [], {})}
            for row in list_rows[-8:]
        ]
        if scope:
            scoped_latest_paths = list((latest_in_scope or {}).get("paths") or in_scope)
            if scoped_latest_paths:
                contract["known_paths_from_latest_repo_list_files"] = scoped_latest_paths[:80]
                contract["known_paths_total_in_latest_digest"] = len(scoped_latest_paths)
        contract["known_in_scope_paths_from_repo_list_files"] = in_scope[:80]
        contract["known_in_scope_paths_total"] = len(in_scope)
        contract["latest_in_scope_repo_list_path"] = latest_in_scope.get("path") if latest_in_scope else None
        contract["latest_repo_list_path"] = latest_any.get("path") if latest_any else None
        contract["successful_repo_read_paths"] = successful_reads
        contract["forbidden_repeated_repo_read_paths"] = successful_reads[:40]
        contract["unread_in_scope_candidate_paths"] = unread_in_scope[:40]

        guidance: list[str] = []
        if scope:
            guidance.append(f"Stay under resolved_goal_scope={scope}; do not call repo_list_files with path='.' or omitted path.")
        if successful_reads:
            guidance.append("Do not repo_read already successful paths: " + ", ".join(successful_reads[:8]))
        if unread_in_scope:
            guidance.append("Next valid progress can be repo_read one unread in-scope candidate or repo_list_files a new subdirectory under scope: " + ", ".join(unread_in_scope[:8]))
        elif latest_in_scope:
            guidance.append("If current in-scope evidence is enough, choose final and cite the read/list evidence already in history.")
        guidance.append("Controller validates only; planner must decide the next tool or final from these evidence-bound candidates.")
        contract["required_next_progress"] = " ".join(guidance)
        return contract