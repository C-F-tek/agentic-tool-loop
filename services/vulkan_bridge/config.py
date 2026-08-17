from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


EnvMapping = Mapping[str, str]


def _env(env: EnvMapping | None = None) -> EnvMapping:
    return os.environ if env is None else env


def int_env(name: str, default: int, env: EnvMapping | None = None) -> int:
    try:
        return int(_env(env).get(name, str(default)))
    except (TypeError, ValueError):
        return default


def bool_env(name: str, default: bool, env: EnvMapping | None = None) -> bool:
    value = _env(env).get(name)
    if value is None:
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off", ""}


def first_env(
    names: tuple[str, ...],
    default: str,
    env: EnvMapping | None = None,
) -> str:
    source = _env(env)
    for name in names:
        value = source.get(name)
        if value is not None and value.strip():
            return value
    return default


@dataclass(frozen=True)
class BridgeConfig:
    agent_url: str
    bridge_timeout_seconds: int
    max_openwebui_response_chars: int
    max_openwebui_summary_chars: int
    max_openwebui_answer_chars: int
    openwebui_inline_file_chars: int
    openwebui_inline_evidence_chars: int
    final_tool_settle_seconds: int
    final_unload_planner: bool
    final_unload_timeout_seconds: int
    planner_url: str
    planner_model: str
    openwebui_return_model: str


def load_bridge_config_from_env(env: EnvMapping | None = None) -> BridgeConfig:
    planner_model = first_env(
        (
        "AICARMINE_AGENT_PLANNER_MODEL",
        "AICARMINE_PLANNER_MODEL",
        "AICARMINE_OLLAMA_PLANNER_MODEL",
    ),
    "codex-qwen25-7b-main",
        env,
    )
    openwebui_return_model = first_env(
        (
            "AICARMINE_OPENWEBUI_RETURN_MODEL",
            "AICARMINE_OPENWEBUI_MODEL",
            "AICARMINE_OPENWEBUI_CHAT_MODEL",
        ),
        planner_model,
        env,
    )
    return BridgeConfig(
        agent_url=first_env(
            ("AICARMINE_VULKAN_AGENT_URL",),
            "http://127.0.0.1:3572/vulkan/agent",
            env,
        ),
        bridge_timeout_seconds=int_env("AICARMINE_VULKAN_BRIDGE_TIMEOUT_SECONDS", 1200, env),
        max_openwebui_response_chars=int_env("AICARMINE_BRIDGE_MAX_OPENWEBUI_RESPONSE_CHARS", 90000, env),
        max_openwebui_summary_chars=int_env("AICARMINE_BRIDGE_MAX_OPENWEBUI_SUMMARY_CHARS", 24000, env),
        max_openwebui_answer_chars=int_env("AICARMINE_BRIDGE_MAX_OPENWEBUI_ANSWER_CHARS", 0, env),
        openwebui_inline_file_chars=int_env("AICARMINE_BRIDGE_OPENWEBUI_INLINE_FILE_CHARS", 60000, env),
        openwebui_inline_evidence_chars=int_env("AICARMINE_BRIDGE_OPENWEBUI_INLINE_EVIDENCE_CHARS", 160000, env),
        final_tool_settle_seconds=max(0, int_env("AICARMINE_OPENWEBUI_FINAL_TOOL_SETTLE_SECONDS", 0, env)),
        final_unload_planner=bool_env("AICARMINE_OPENWEBUI_FINAL_UNLOAD_PLANNER", True, env),
        final_unload_timeout_seconds=max(1, int_env("AICARMINE_OPENWEBUI_FINAL_UNLOAD_TIMEOUT_SECONDS", 10, env)),
        planner_url=first_env(
            ("AICARMINE_AGENT_PLANNER_URL", "AICARMINE_PLANNER_URL"),
            "http://127.0.0.1:11434/api/chat",
            env,
        ),
        planner_model=planner_model,
        openwebui_return_model=openwebui_return_model,
    )
