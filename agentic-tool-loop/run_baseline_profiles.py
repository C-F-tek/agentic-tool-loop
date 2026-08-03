#!/usr/bin/env python
"""Run baseline profiles to verify they still pass."""

import sys
sys.path.insert(0, 'services')

from pathlib import Path
from codex_bridge.repo_probe_profiles import repo_probe_run

root = Path.cwd()

print("=" * 60)
print("RUNNING BASELINE PROFILES")
print("=" * 60)

# Profile 1: orientation.selector.contract.v1
result1 = repo_probe_run({
    "profile_id": "orientation.selector.contract.v1",
    "engine": "deterministic",
    "max_examples": 200,
    "seed": 42,
}, root=root)

print(f"\nProfile: orientation.selector.contract.v1")
print(f"  ok={result1.get('ok')}")
print(f"  case_count={result1.get('case_count')}")
print(f"  passed={result1.get('passed')}")
print(f"  failed={result1.get('failed')}")

# Profile 2: orientation.shadow_helpers.contract.v1
result2 = repo_probe_run({
    "profile_id": "orientation.shadow_helpers.contract.v1",
    "engine": "deterministic",
    "max_examples": 200,
    "seed": 42,
}, root=root)

print(f"\nProfile: orientation.shadow_helpers.contract.v1")
print(f"  ok={result2.get('ok')}")
print(f"  case_count={result2.get('case_count')}")
print(f"  passed={result2.get('passed')}")
print(f"  failed={result2.get('failed')}")

# Profile 3: orientation.shadow_evaluator.contract.v1 (expected RED - missing callable)
result3 = repo_probe_run({
    "profile_id": "orientation.shadow_evaluator.contract.v1",
    "engine": "deterministic",
    "max_examples": 200,
    "seed": 42,
}, root=root)

print(f"\nProfile: orientation.shadow_evaluator.contract.v1")
print(f"  ok={result3.get('ok')}")
print(f"  case_count={result3.get('case_count')}")
print(f"  passed={result3.get('passed')}")
print(f"  failed={result3.get('failed')}")

all_ok = result1.get('ok') and result2.get('ok')
print("\n" + "=" * 60)
if all_ok:
    print("BASELINE PROFILES OK!")
else:
    print("BASELINE PROFILES FAILED!")
print("=" * 60)