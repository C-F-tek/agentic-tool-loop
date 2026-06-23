#!/usr/bin/env python3
"""Diagnose non-ASCII bytes in the 6 problematic files."""
import sys
from pathlib import Path

files = [
    "services/aicarmine_broker/application/planner/decision.py",
    "services/aicarmine_broker/planner.py",
    "services/aicarmine_broker/job_html.py",
    "services/aicarmine_broker/job_html_assets.py",
    "codex_ollama_bridge_applied/aicarmine_vulkan_tool_broker.py",
    "services/aicarmine_broker/planner_core/json_io.py",
]

for fpath in files:
    raw = Path(fpath).read_bytes()
    non_ascii = [(i, raw[i]) for i in range(min(len(raw), 8000)) if raw[i] > 127]
    print(f"--- {fpath} ({len(raw)} bytes) ---")
    print(f"Non-ASCII bytes in first 8000: {len(non_ascii)}")
    for offset, byte_val in non_ascii[:5]:
        print(f"  Offset {offset}: 0x{byte_val:02X} ({byte_val})")
    # Check if file is valid UTF-8
    try:
        raw.decode("utf-8")
        print("  UTF-8 decode: OK")
    except UnicodeDecodeError as e:
        print(f"  UTF-8 decode: FAIL — {e}")
    # Check if it's already UTF-8 with BOM
    if raw[:3] == bytes([0xEF, 0xBB, 0xBF]):
        print("  Has UTF-8 BOM")
    else:
        print("  No UTF-8 BOM")
    print()