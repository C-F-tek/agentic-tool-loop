"""Constants for Full0To10 effective use optimization."""
from __future__ import annotations

DEFAULT_REQUEST = (
    "Ottimizza uso SQLite FTS5, runtime tools, GPU Ollama e NPU OpenVINO "
    "per Full0To10 senza run reale provider."
)

MEMORY_NAMESPACE = "full0to10_effective_use"
DEFAULT_DB = "output/ai_runtime_memory/full0to10_effective_use.sqlite"

QUALITY_PRODUCT_NAME = "full0to10_effective_use_quality_product.md"
TELEMETRY_NAME = "full0to10_effective_use_tool_telemetry.json"
PROVIDER_HARDENING_NAME = "full0to10_provider_hardening_contracts.json"
OPTIMIZATION_NAME = "full0to10_effective_use_optimization.json"

CONTEXT_FACTS = (
    "SQLite FTS5 memory is the local searchable context lane.",
    "Runtime tools must emit telemetry and capability evidence.",
    "Ollama/GPU is the primary advisory provider lane when explicitly enabled.",
    "NPU/OpenVINO is a sampled auditor or diagnostic lane unless promoted explicitly.",
    "OpenVINO GPU.0 must remain secondary/diagnostic unless explicitly promoted.",
    "Quality gates must run before provider generation.",
    "Full0To10 means TUTTO su TUTTO: complete recursive bundle and evidence.",
)

PROVIDER_LANES = ("sqlite_fts5", "runtime_tools", "ollama_gpu", "openvino_npu", "openvino_gpu0")

SAFETY_FLAGS = {
    "provider_execution_performed": False,
    "patch_application_performed": False,
    "source_writes_performed": False,
    "persistent_memory_write_performed": False,
}
