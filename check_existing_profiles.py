#!/usr/bin/env python
"""Check existing profiles in repo_probe_profiles.py"""

import sys
sys.path.insert(0, 'services')

try:
    from codex_bridge import repo_probe_profiles
    print("repo_probe_profiles loaded")
    print("Existing profiles:", list(repo_probe_profiles._PROFILE_SPECS.keys()))
except Exception as e:
    print(f"Error loading repo_probe_profiles: {e}")