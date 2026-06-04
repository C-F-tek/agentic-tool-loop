from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_openapi_exposes_only_vulkan_helper() -> None:
    from vulkan_bridge.app import app

    schema = app.openapi()

    assert set(schema["paths"]) == {"/vulkan_helper"}
    assert schema["x-aicarmine-public-surface"] == ["vulkan_helper"]


def test_vulkan_helper_response_schema_names_primary_payload_fields() -> None:
    from vulkan_bridge.openapi_builder import vulkan_helper_completed_response_schema

    properties = vulkan_helper_completed_response_schema()["properties"]

    assert "payload_index_for_30b" in properties
    assert "priority_evidence_for_30b" in properties
    assert "tool_context_for_30b" in properties
    assert "openwebui_usage" in properties
