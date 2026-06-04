from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.prompt.intrinsic_context import (  # noqa: E402
    compact_intrinsic_context_for_prompt,
)


def test_compact_intrinsic_context_rejects_non_dict() -> None:
    assert compact_intrinsic_context_for_prompt([], prompt_preview_chars=1000) == {}  # type: ignore[arg-type]


def test_compact_intrinsic_context_bounds_rag_and_memory_items() -> None:
    context = {
        "schema": "planner_intrinsic_context.v1",
        "retrieved_rag_chunks": {
            "items": [{"path": f"doc_{idx}.md", "text": "r" * 600} for idx in range(5)],
        },
        "retrieved_memory": {
            "items": [{"key": f"memory_{idx}", "text": "m" * 600} for idx in range(6)],
        },
    }

    payload = compact_intrinsic_context_for_prompt(context, prompt_preview_chars=2000)

    rag = payload["retrieved_rag_chunks"]
    memory = payload["retrieved_memory"]
    assert rag["count"] == 4
    assert len(rag["items"]) == 4
    assert rag["items"][-1] == {"omitted_items_for_prompt": 2}
    assert memory["count"] == 5
    assert len(memory["items"]) == 5
    assert memory["items"][-1] == {"omitted_items_for_prompt": 2}
