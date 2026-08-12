"""Constants for Full0To10 track input contract."""
from __future__ import annotations

CONTRACT_JSON = "full0to10_track_input_contract.json"
CONTRACT_MD = "full0to10_track_input_contract.md"
TEMPLATE_JSON = "full0to10_track_input_template.json"

INPUT_ROLES = (
    "analysis_json",
    "music_context_json",
    "blender_keyframes_json",
)

ROLE_PATTERNS = {
    "analysis_json": (
        "analysis.json",
        "_analysis.json",
        "audio_analysis.json",
        "wav_analysis.json",
    ),
    "music_context_json": (
        "music_context.json",
        "_music_context.json",
        "track_context.json",
        "song_context.json",
    ),
    "blender_keyframes_json": (
        "blender_keyframes.json",
        "_keyframes.json",
        "keyframes.json",
        "audio_keyframes.json",
    ),
}

SEARCH_ROOTS = (
    "output",
    "input",
    "inputs",
    "data",
    "assets",
    "Scripting",
)

EXCLUDED_DIRS = (
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "renders",
    "node_modules",
)

SAFETY_FLAGS = {
    "provider_execution_performed": False,
    "patch_application_performed": False,
    "source_writes_performed": False,
    "persistent_memory_write_performed": False,
    "blender_runtime_execution_performed": False,
    "ffmpeg_execution_performed": False,
}
