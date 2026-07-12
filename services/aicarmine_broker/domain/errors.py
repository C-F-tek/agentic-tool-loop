'''Backward-compatible shim for domain.errors string constants.'''

NATIVE_TOOL_NOT_IN_TURN_SURFACE = "native_tool_not_in_turn_surface"
PROMPT_CONTEXT_WINDOW_TRACKING_METADATA_MISSING = (
    "prompt_context_window_tracking_metadata_missing"
)
PROMPT_CONTEXT_WINDOW_ALREADY_CONSUMED = (
    "prompt_context_window_already_consumed"
)
PLANNER_PROMPT_NO_GENERATION_HEADROOM = ("planner_prompt_no_generation_headroom")
MISSING_CODE_PRODUCT_CANDIDATE = "missing_code_product_candidate"

__all__: list[str] = [
    "NATIVE_TOOL_NOT_IN_TURN_SURFACE",
    "PROMPT_CONTEXT_WINDOW_TRACKING_METADATA_MISSING",
    "PROMPT_CONTEXT_WINDOW_ALREADY_CONSUMED",
    "PLANNER_PROMPT_NO_GENERATION_HEADROOM",
    "MISSING_CODE_PRODUCT_CANDIDATE",
]
