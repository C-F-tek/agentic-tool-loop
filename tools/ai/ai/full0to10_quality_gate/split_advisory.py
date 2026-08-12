"""Split and refactor advisory for Full0To10 quality gate."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


def load_specs(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, list):
        return list(data)
    if isinstance(data, dict) and isinstance(data.get("patch_specs"), list):
        return list(data["patch_specs"])
    return []


def summarize_split_specs(specs: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(item.get("candidate_kind") or item.get("kind") or "unknown") for item in specs)
    markdown = [item for item in specs if item.get("candidate_kind") == "markdown_split"]
    code = [item for item in specs if item.get("candidate_kind") == "code_split_candidate"]
    hardware = [
        item for item in specs
        if str(item.get("candidate_kind", "")).startswith(("gpu_", "npu_"))
        or "gpu" in str(item.get("candidate_kind", ""))
        or "npu" in str(item.get("candidate_kind", ""))
    ]
    return {
        "spec_count": len(specs),
        "kind_counts": dict(counts),
        "useful_markdown_splits": markdown[:20],
        "useful_code_splits": code[:20],
        "hardware_contract_suggestions": hardware[:20],
        "advisory_only": True,
        "apply_performed": False,
    }
