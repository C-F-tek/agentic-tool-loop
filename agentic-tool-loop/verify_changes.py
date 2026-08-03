#!/usr/bin/env python
"""Verify TASK R5C-R changes to planner.py"""

import sys
sys.path.insert(0, 'services')

from pathlib import Path

def main():
    path = Path('services/aicarmine_broker/planner.py')
    content = path.read_text(encoding='utf-8')
    lines = content.split('\n')
    
    # Check 1: Import controller_initial_orientation_candidate_pool
    has_import = 'controller_initial_orientation_candidate_pool\n    as _controller_initial_orientation_candidate_pool_impl' in content
    print(f"[{'✓' if has_import else '✗'}] Import controller_initial_orientation_candidate_pool")
    
    # Check 2: Import other orientation shadow functions
    has_orientation_model_select = 'controller_orientation_model_select\n    as _controller_orientation_model_select_impl' in content
    has_shadow_effective_mode = 'orientation_shadow_effective_mode\n    as _orientation_shadow_effective_mode_impl' in content
    has_legacy_selected_ids = 'orientation_legacy_selected_candidate_ids\n    as _orientation_legacy_selected_candidate_ids_impl' in content
    has_selection_metrics = 'orientation_shadow_selection_metrics\n    as _orientation_shadow_selection_metrics_impl' in content
    print(f"[{'✓' if has_orientation_model_select else '✗'}] Import controller_orientation_model_select")
    print(f"[{'✓' if has_shadow_effective_mode else '✗'}] Import orientation_shadow_effective_mode")
    print(f"[{'✓' if has_legacy_selected_ids else '✗'}] Import orientation_legacy_selected_candidate_ids")
    print(f"[{'✓' if has_selection_metrics else '✗'}] Import orientation_shadow_selection_metrics")
    
    # Check 3: AICARMINE_ORIENTATION_LANE_MODE import
    has_mode_import = 'AICARMINE_ORIENTATION_LANE_MODE,' in content
    print(f"[{'✓' if has_mode_import else '✗'}] Import AICARMINE_ORIENTATION_LANE_MODE")
    
    # Check 4: 5 deps entries in run_agentic_planner_job_impl
    deps_section_start = None
    for i, line in enumerate(lines):
        if '"initial_orientation_surface_from_history": _initial_orientation_surface_from_history,' in line:
            deps_section_start = i
            break
    
    if deps_section_start is not None:
        next_lines = lines[deps_section_start:deps_section_start+10]
        found_entries = []
        for line in next_lines:
            if any(entry in line for entry in ['controller_initial_orientation_candidate_pool:', 'controller_orientation_model_select:', 'orientation_shadow_effective_mode:', 'orientation_legacy_selected_candidate_ids:', 'orientation_shadow_selection_metrics:']):
                found_entries.append(line.strip())
        
        print(f"\n[{'✓' if len(found_entries) == 5 else '✗'}] Found {len(found_entries)}/5 deps entries:")
        for entry in found_entries:
            print(f"   {entry}")
    else:
        print("\n[✗] Could not find deps section")
    
    # Check 5: AICARMINE_ORIENTATION_LANE_MODE in config dicts
    config_matches = sum(1 for line in lines if '"AICARMINE_ORIENTATION_LANE_MODE": AICARMINE_ORIENTATION_LANE_MODE,' in line)
    print(f"\n[{'✓' if config_matches >= 2 else '✗'}] Found {config_matches} config entries with AICARMINE_ORIENTATION_LANE_MODE")
    
    # Check 6: No duplicate keys
    duplicate_keys = sum(1 for line in lines if line.count('"AICARMINE_ORIENTATION_LANE_MODE":') > 1)
    print(f"[{'✓' if duplicate_keys == 0 else '✗'}] No duplicate keys (found {duplicate_keys})")
    
    # Check 7: py_compile passes
    try:
        import py_compile
        py_compile.compile(str(path), doraise=True)
        print("[✓] py_compile passed")
    except Exception as e:
        print(f"[✗] py_compile failed: {e}")
    
    # Line count
    line_count = len(lines)
    print(f"\nTotal lines in planner.py: {line_count}")
    
    return 0 if all([has_import, has_orientation_model_select, has_shadow_effective_mode, 
                      has_legacy_selected_ids, has_selection_metrics, has_mode_import, 
                      config_matches >= 2, duplicate_keys == 0]) else 1

if __name__ == '__main__':
    sys.exit(main())