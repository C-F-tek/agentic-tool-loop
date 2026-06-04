"""User-declared repository scope claims used as evidence constraints."""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from .path_tokens import repo_rel_token


PathExists = Callable[[str], bool]


def normalize_scope_claim_text(text: str) -> str:
    return (
        str(text or "")
        .lower()
        .replace("\\", "/")
        .replace("è", "e")
        .replace("é", "e")
        .replace("'", " ")
    )


def claim_area_from_user_token(
    raw_area: str,
    target_scope: str = "",
    *,
    path_exists_repo_relative: PathExists,
) -> str:
    area = repo_rel_token(raw_area)
    if area.lower() == "shared":
        area = "_shared"
    scope = repo_rel_token(target_scope)
    if area == "_shared" and scope and scope != ".":
        if scope.endswith("/_shared") or scope == "_shared":
            return scope
        scoped_area = f"{scope.rstrip('/')}/_shared"
        if path_exists_repo_relative(scoped_area):
            return scoped_area
    if area == "_shared" and path_exists_repo_relative("ia_carmine/_shared"):
        return "ia_carmine/_shared"
    return area


def user_scope_claims(
    goal: str,
    target_scope: str = "",
    *,
    path_exists_repo_relative: PathExists,
) -> list[dict[str, Any]]:
    """Extract user scope claims as evidence, not as a static blacklist."""
    text = str(goal or "")
    low = normalize_scope_claim_text(text)
    patterns = (
        r"(?P<area>(?:[\w.+-]+/)*_shared|shared)\b.{0,180}\b(?:non\s+(?:e\s+)?(?:il\s+|la\s+)?core|not\s+(?:the\s+)?core)\b",
        r"(?P<area>(?:[\w.+-]+/)*_shared|shared)\b.{0,180}\b(?:solo|only)\b.{0,120}\b(?:script|util|utility)\b",
    )
    claims: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, low, flags=re.IGNORECASE | re.DOTALL):
            area = claim_area_from_user_token(
                match.group("area"),
                target_scope,
                path_exists_repo_relative=path_exists_repo_relative,
            )
            if not area or area == ".":
                continue
            key = (area, "not_core")
            if key in seen:
                continue
            seen.add(key)
            start = max(0, match.start() - 40)
            end = min(len(text), match.end() + 40)
            claims.append({
                "area": area,
                "claim": "not_core",
                "source": "user_request",
                "text": text[start:end].strip(),
                "validator_effect": "requires_read_evidence_for_conflicting_patch_target",
            })
    return claims


def scope_claim_conflict_for_path(path: str, claims: list[dict[str, Any]]) -> dict[str, Any]:
    p = repo_rel_token(path).strip("/")
    low = p.lower()
    for claim in claims if isinstance(claims, list) else []:
        if not isinstance(claim, dict) or str(claim.get("claim") or "") != "not_core":
            continue
        area = repo_rel_token(claim.get("area") or "").strip("/").lower()
        if not area:
            continue
        if area in {"_shared", "shared"}:
            if low.startswith("_shared/") or "/_shared/" in f"/{low}/":
                return claim
            continue
        if low == area or low.startswith(area + "/"):
            return claim
    return {}
