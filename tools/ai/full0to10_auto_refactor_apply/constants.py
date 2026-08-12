"""Constants for controlled Full0To10 refactor apply."""
from __future__ import annotations

ALLOWED_APPLY_KINDS = {
    "safe_cleanup_trailing_whitespace",
    "safe_cleanup_final_newline",
}

REJECTED_KINDS = {
    "markdown_split",
    "code_split_candidate",
    "npu_gpu0_integration_contract",
    "npu_sampled_auditor_contract",
    "gpu_telemetry_visibility",
}

TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".ps1",
    ".txt",
    ".json",
}

SAFETY_FLAGS = {
    "provider_execution_performed": False,
    "patch_application_performed": False,
    "persistent_memory_write_performed": False,
}
