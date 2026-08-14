"""Public OpenWebUI payload field-name normalization."""
from __future__ import annotations

from typing import Any


PUBLIC_FIELD_NAME_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("evidence_guide_for_30b", "evidence_guide"),
    ("primary_payload_for_30b", "primary_payload"),
    ("payload_index_for_30b", "payload_index"),
    ("priority_evidence_for_30b", "priority_evidence"),
    ("tool_context_for_30b", "tool_context"),
    ("agent_context_for_30b", "agent_context"),
    ("structured_context_for_30b", "structured_context"),
    ("structured_result_for_30b", "structured_result"),
    ("working_memory_for_30b", "working_memory"),
    ("next_action_for_30b", "next_action"),
    ("answer_for_30b", "answer"),
    ("message_for_30b", "message"),
    ("summary_for_30b", "summary"),
    ("evidence_digest_for_30b", "evidence_digest"),
    ("partial_products_for_30b", "partial_products"),
    ("best_partial_product_for_30b", "best_partial_product"),
    ("tool_observation_for_30b", "tool_observation"),
    ("result_index_for_30b", "result_index"),
    ("priority_payload_for_30b", "priority_payload"),
    ("called_by_30b", "called_by"),
)

_CONTENT_VALUE_KEYS = {
    "content",
    "content_preview",
    "content_view",
    "full_content",
    "raw",
    "raw_text",
    "text",
    "unified_diff",
}

_RENAMED_TEXT_VALUE_KEYS = {
    "alias_of",
    "artifact_mirror_field",
    "concrete_results_field",
    "evidence_guide",
    "evidence_guide_field",
    "field",
    "full_context_location",
    "full_tool_evidence_field",
    "navigation_hint",
    "path",
    "payload_index_field",
    "primary_location",
    "primary_payload_field",
    "primary_payload_fields",
    "primary_payload_location_field",
    "priority_evidence_field",
    "public_scope",
    "purpose",
    "reason",
    "required_top_level_keys",
    "rule",
    "schema",
    "search_order",
    "structured_context_field",
    "top_level_evidence_guide_field",
    "top_level_present_fields",
}


def replace_public_field_name_references(text: str) -> str:
    out = str(text)
    for old, new in PUBLIC_FIELD_NAME_REPLACEMENTS:
        out = out.replace(old, new)
    return out


def normalize_public_payload_field_names(value: Any,  parent_key: str = "") -> Any:
    """Rename public field names without rewriting concrete inline payload text."""

    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = replace_public_field_name_references(str(key))
            normalized = normalize_public_payload_field_names(item, parent_key=key_text)
            if key_text in out and out[key_text] not in (None, "", [], {}):
                continue
            out[key_text] = normalized
        return out
    if isinstance(value, list):
        return [
            normalize_public_payload_field_names(item, parent_key=parent_key)
            for item in value
        ]
    if isinstance(value, str):
        if parent_key in _CONTENT_VALUE_KEYS:
            return value
        if parent_key in _RENAMED_TEXT_VALUE_KEYS:
            return replace_public_field_name_references(value)
    return value
