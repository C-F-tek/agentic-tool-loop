#!/usr/bin/env python
"""Debug profile loading issues."""

import sys
sys.path.insert(0, 'services')

from pathlib import Path

print("=" * 60)
print("DEBUGGING PROFILE LOADING")
print("=" * 60)

try:
    from codex_bridge.repo_probe_profiles import _PROFILE_SPECS
    print(f"\n_Profile_SPECS loaded: {_PROFILE_SPECS}")
    print(f"Number of specs: {len(_PROFILE_SPECS)}")
    
    for i, spec in enumerate(_PROFILE_SPECS):
        print(f"\nSpec {i}:")
        print(f"  profile_id: {spec.get('profile_id')}")
        print(f"  target_module: {spec.get('target_module')}")
        print(f"  engines: {spec.get('engines')}")
        
except Exception as e:
    print(f"\nError loading _PROFILE_SPECS: {e}")
    import traceback
    traceback.print_exc()

try:
    from codex_bridge.repo_probe_profiles import repo_probe_run
    print("\nrepo_probe_run loaded successfully")
except Exception as e:
    print(f"\nError loading repo_probe_run: {e}")
    import traceback
    traceback.print_exc()

try:
    from aicarmine_broker.application.controller import orientation_lane
    print("\norientation_lane module loaded successfully")
    print(f"Available attributes: {[a for a in dir(orientation_lane) if not a.startswith('_')]}")
except Exception as e:
    print(f"\nError loading orientation_lane: {e}")
    import traceback
    traceback.print_exc()