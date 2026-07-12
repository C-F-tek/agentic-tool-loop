"""Scope-claim conflict resolution helpers for code-product validation."""
from __future__ import annotations

import re
from typing import Any

from ..code_product.state import code_product_action_has_complete_payload
from ..shared.path_tokens import repo_rel_token
from .user_scope_claims import normalize_scope_claim_text


SCOPE_CONFLICT_RATIONALE_TERMS = (
    "core", "runtime", "entrypoint", "entry point", "planner", "validator",
    "controller", "broker", "dispatch", "orchestrat", "loop", "contract",
    "tool", "schema", "evidence", "repo_read", "contenuto", "letto",
    "nucleo", "flusso", "contratto", "strumento",
)

_ANCHOR_STOPWORDS = {
    "from", "import", "return", "self", "true", "false", "none",
    "path", "file", "line", "with", "that", "this", "sono",
    "solo", "core",
}


def target_scope_conflict_resolved(path: str, args: dict[str, Any], contract: dict[str, Any]) -> bool:
    target = repo_rel_token(path)
    verified_rows = contract.get("verified_content_reads") if isinstance(contract.get("verified_content_reads"), list) else []
    verified_paths = {
        repo_rel_token(row.get("path") or "")
        for row in verified_rows
        if isinstance(row, dict) and row.get("path")
    }
    if target not in verified_paths:
        return False
    if not code_product_action_has_complete_payload({"tool": "repo_propose_code_edit", "arguments": args}):
        return False
    rationale = str(args.get("rationale") or "").strip()
    low = normalize_scope_claim_text(rationale)
    if len(re.findall(r"\w+", low)) < 8:
        return False
    if not any(term in low for term in SCOPE_CONFLICT_RATIONALE_TERMS):
        return False
    file_memory = contract.get("file_memory") if isinstance(contract.get("file_memory"), list) else []
    anchors: set[str] = set()
    for item in file_memory:
        if not isinstance(item, dict) or repo_rel_token(item.get("path") or "") != target:
            continue
        chunks: list[str] = []
        for key in ("headings", "key_lines", "mentioned_paths"):
            value = item.get(key)
            if isinstance(value, list):
                chunks.extend(str(part) for part in value)
        chunks.append(str(item.get("content_excerpt") or ""))
        for chunk in chunks:
            for word in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{3,}", normalize_scope_claim_text(chunk)):
                if word in _ANCHOR_STOPWORDS:
                    continue
                anchors.add(word)
        break
    if anchors:
        return any(anchor in low for anchor in sorted(anchors)[:120])
    return True
