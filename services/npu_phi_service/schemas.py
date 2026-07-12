from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SceneSpecRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)
    prompt: str | None = Field(default=None, max_length=8000)
    evidence_hash: str = Field(default="")
    schema_version: str = Field(default="scene_spec.v1")
    json_schema: dict[str, Any] | None = None
    max_new_tokens: int = Field(default=512, ge=32, le=2048)
    timeout_s: float | None = Field(default=None, ge=1, le=120)


class WarmupRequest(BaseModel):
    force: bool = False


DEFAULT_SCENE_SPEC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "scene_elements": {
            "type": "array",
            "items": {"type": "string"},
        },
        "camera": {"type": "string"},
        "lighting": {"type": "string"},
        "risks": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["title", "summary", "scene_elements", "camera", "lighting", "risks"],
}


def build_scene_prompt(request: SceneSpecRequest) -> str:
    if request.prompt:
        return request.prompt
    return (
        "Return only compact JSON matching the provided schema. "
        "Create a diagnostic scene specification for this goal:\n"
        f"{request.goal}"
    )
