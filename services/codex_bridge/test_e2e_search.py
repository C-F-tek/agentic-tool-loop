#!/usr/bin/env python3
"""End-to-end intelligent search test via direct Python call."""
import sys, json
sys.path.insert(0, "services")
from codex_bridge.intelligent_search import intelligent_search

query = "What is git?"
result = intelligent_search(query, top_k=20, top_n=5)
print(f"Result count: {len(result)}")
for i, r in enumerate(result[:3]):
    print(json.dumps(r, indent=None))