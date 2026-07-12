#!/usr/bin/env python
"""Final verification for TASK R5C-R"""

from pathlib import Path

def main():
    path = Path('services/aicarmine_broker/planner.py')
    content = path.read_text(encoding='utf-8')
    lines = content.split('\n')
    
    print("=" * 60)
    print("TASK R5C-R FINAL VERIFICATION")
    print("=" * 60)
    
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
    
    # Check 4: 5 deps entries in run_agentic_planner_job_impl - look for the text regardless of exact indentation
    deps_found = []
    for entry_name in ['controller_initial_orientation_candidate_pool', 'controller_orientation_model_select', 
                        'orientation_shadow_effective_mode', 'orientation_legacy_selected_candidate_ids', 
                        'orientation_shadow_selection_metrics']:
        if f'"{entry_name}":' in content:
            deps_found.append(entry_name)
    
    print(f"\n[{'✓' if len(deps_found) == 5 else '✗'}] Found {len(deps_found)}/5 deps entries:")
    for entry in sorted(deps_found):
        print(f"   {entry}")
    
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
    
    # Summary
    all_checks_passed = all([has_import, has_orientation_model_select, has_shadow_effective_mode, 
                              has_legacy_selected_ids, has_selection_metrics, has_mode_import, 
                              len(deps_found) == 5, duplicate_keys == 0])
    
    print("\n" + "=" * 60)
    if all_checks_passed:
        print("ALL CHECKS PASSED!")
    else:
        print("SOME CHECKS FAILED!")
    print("=" * 60)
    
    return 0 if all_checks_passed else 1

if __name__ == '__main__':
    import sys
    sys.exit(main())