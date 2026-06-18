#!/usr/bin/env python
"""Test script for lane_catalog validation."""

import sys
sys.path.insert(0, '.')

from application.planner.lane_catalog import (
    CONTROL_LANE_SPECS,
    CONTROL_LANE_BY_ID,
    validate_control_lane_catalog,
    get_control_lane_spec,
)

def main():
    print("=" * 60)
    print("LANE CATALOG AUDIT REPORT")
    print("=" * 60)
    
    # 1. Count verification
    count = len(CONTROL_LANE_SPECS)
    print(f"\n1. Numero lane: {count} (atteso: 28)")
    print(f"   Status: {'OK' if count == 28 else 'DISCREPANCY'}")
    
    # 2. Validation
    errors = validate_control_lane_catalog()
    print(f"\n2. Validazione validate_control_lane_catalog():")
    if errors:
        for err in errors:
            print(f"   ERROR: {err}")
    else:
        print("   Status: OK (nessun errore)")
    
    # 3. Unique IDs
    seen = set()
    duplicates = []
    for spec in CONTROL_LANE_SPECS:
        if spec.lane_id in seen:
            duplicates.append(spec.lane_id)
        seen.add(spec.lane_id)
    
    print(f"\n3. ID univoci:")
    if duplicates:
        print(f"   Status: DISCREPANCY - Duplicate IDs found: {duplicates}")
    else:
        print(f"   Status: OK (tutti gli ID sono unici)")
    
    # 4. may_execute_tools check
    tool_executors = [s for s in CONTROL_LANE_SPECS if s.may_execute_tools]
    print(f"\n4. may_execute_tools=true:")
    print(f"   Lanes found: {[s.lane_id for s in tool_executors]}")
    if len(tool_executors) == 1 and tool_executors[0].lane_id == "23 dispatch.tool":
        print(f"   Status: OK (solo dispatch.tool può eseguire tools)")
    else:
        print(f"   Status: DISCREPANCY - Expected only '23 dispatch.tool'")
    
    # 5. Specific lane verification
    target_lanes = [
        "01 planner.primary",
        "02 planner.cuda_rewrite",
        "03 planner.replan",
        "04 judge.final_quality",
        "05 repair.vulkan_gpu0",
        "06 preplanner.semantic_query",
        "07 planner.native_tool_batch",
        "08 planner.guided_terminal_final_quality",
        "09 routing.evidence_gap",
        "10 planner.incomprehensible_retry",
        "11 planner.native_protocol_recovery",
        "12 orientation.initial",
        "13 orientation.area_expansion",
        "14 candidate_actions.ranking",
        "15 planner.max_step_terminal_synthesis",
        "16 coverage.interpretation",
        "17 validator.evidence",
        "18 quality.deterministic_floor",
        "19 audit.specialist_route",
        "20 guard.repeat",
        "21 cache.tool_result",
        "22 guard.approval",
        "23 dispatch.tool",
        "24 guard.repeated_rejection_breaker",
        "25 lifecycle.terminal_status",
        "26 judge.terminal",
        "27 diagnostic.npu_phi",
        "28 boundary.internal_tool_selector",
    ]
    
    print(f"\n5. Verifica delle lane target:")
    print("-" * 60)
    print(f"{'Lane ID':<40} {'Owner':<25} {'Provider':<20} {'Authority':<20}")
    print("-" * 60)
    
    for lid in target_lanes:
        spec = get_control_lane_spec(lid)
        if spec:
            # Determine owner based on provider and lane characteristics
            if spec.provider == "controller":
                owner = "controller"
            elif spec.provider == "gpu1_planner":
                owner = "planner"
            elif spec.provider == "gpu0_task_model":
                owner = "task_model"
            elif spec.provider == "npu_phi":
                owner = "npu_phi"
            elif spec.provider == "mixed":
                owner = "mixed"
            elif spec.provider == "gpu1_planner":
                owner = "planner"
            else:
                owner = spec.provider
            
            print(f"{lid:<40} {owner:<25} {spec.provider:<20} {spec.authority:<20}")
    
    # 6. judge.terminal e diagnostic.npu_phi check
    print(f"\n6. Verifica judge.terminal e diagnostic.npu_phi:")
    judge_terminal = get_control_lane_spec("26 judge.terminal")
    diagnostic_npu = get_control_lane_spec("27 diagnostic.npu_phi")
    
    if judge_terminal:
        print(f"\n   judge.terminal:")
        print(f"      affects_control_flow: {judge_terminal.affects_control_flow}")
        print(f"      Status: {'OK (non influenza control flow)' if not judge_terminal.affects_control_flow else 'DISCREPANCY'}")
    
    if diagnostic_npu:
        print(f"\n   diagnostic.npu_phi:")
        print(f"      affects_control_flow: {diagnostic_npu.affects_control_flow}")
        print(f"      Status: {'OK (non influenza control flow)' if not diagnostic_npu.affects_control_flow else 'DISCREPANCY'}")
    
    # Summary
    print("\n" + "=" * 60)
    print("Riepilogo:")
    print("=" * 60)
    
    issues = []
    if count != 28:
        issues.append(f"Numero lane: {count} != 28")
    if errors:
        issues.extend(errors)
    if duplicates:
        issues.append(f"ID duplicati: {duplicates}")
    if len(tool_executors) != 1 or tool_executors[0].lane_id != "23 dispatch.tool":
        issues.append("may_execute_tools=true non solo su dispatch.tool")
    if judge_terminal and judge_terminal.affects_control_flow:
        issues.append("judge.terminal influenza control flow")
    if diagnostic_npu and diagnostic_npu.affects_control_flow:
        issues.append("diagnostic.npu_phi influenza control flow")
    
    if issues:
        print("DISCREPANZE TROVATE:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("CATALOGO CONFERMATO - Nessun problema rilevato.")
    
    print("\nFILE MODIFICATI: 0")
    
    return len(issues) == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)