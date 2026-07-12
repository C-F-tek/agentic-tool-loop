#!/usr/bin/env python3
"""Merge AI mapping candidates deterministically."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def score(item):
    if isinstance(item, dict):
        for key in ("score", "confidence", "rank_score"):
            if isinstance(item.get(key), (int, float)):
                return float(item[key])
    return 0.5


def extract(path: Path):
    data = load(path)
    raw = (
        data.get("candidates", [])
        if isinstance(data, dict)
        else data
        if isinstance(data, list)
        else [data]
    )
    out = []
    for i, item in enumerate(raw):
        c = dict(item) if isinstance(item, dict) else {"description": str(item)}
        c.setdefault("candidate_id", f"{path.stem}:{i}")
        c.setdefault("source", str(path))
        c.setdefault("score", score(c))
        out.append(c)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", action="append", required=True)
    ap.add_argument("--output", default="output/ai_pipeline/ai_selected_mapping.json")
    ap.add_argument("--limit", type=int, default=2)
    args = ap.parse_args()
    candidates = []
    for item in args.input:
        p = Path(item).resolve()
        if p.exists():
            candidates.extend(extract(p))
    selected = sorted(candidates, key=score, reverse=True)[: max(args.limit, 1)]
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selection_policy": "highest score/confidence first",
        "selected": selected[0] if selected else {"candidate_id": "none", "score": 0.0},
        "selected_candidates": selected,
        "all_candidate_count": len(candidates),
    }
    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
