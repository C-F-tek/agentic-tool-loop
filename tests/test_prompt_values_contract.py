from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.prompt_values import (  # noqa: E402
    prompt_clip_text,
    prompt_clip_value,
    text_hash,
)


def test_prompt_clip_text_marks_truncation() -> None:
    clipped = prompt_clip_text("abcdef", 5)

    assert clipped.endswith("<prompt_preview_truncated>")
    assert len(clipped) > 5


def test_prompt_clip_value_turns_diff_into_metadata() -> None:
    value = prompt_clip_value({
        "unified_diff": "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n",
        "structured_operations": [{"op": "replace"}],
        "content": "abcdef",
    }, text_limit=4)

    assert value["unified_diff_present"] is True
    assert value["unified_diff_markers_present"] is True
    assert value["structured_operations_present"] is True
    assert value["structured_operations_count"] == 1
    assert value["content"].endswith("<prompt_preview_truncated>")


def test_text_hash_is_stable_sha256() -> None:
    assert text_hash("a") == "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb"
