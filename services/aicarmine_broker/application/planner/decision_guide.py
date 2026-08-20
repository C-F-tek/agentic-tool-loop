"""Planner decision guide - deterministic state-machine based on evidence contract state."""
from __future__ import annotations

from typing import Any, Dict


def get_decision_guidance(contract: dict[str, Any]) -> dict[str, Any]:
    """Generate dynamic guidance for the planner based on current contract state using Priority Queue logic."""
    contract = contract if isinstance(contract, dict) else {}
    
    guidance = {
        "schema": "planner_decision_guide.v1",
        "priority_action": "PRIORITÀ_1_ESPLORAZIONE",
        "reason": "",
        "checklist_status": {},
    }
    
    # Case 1: Coverage not satisfied OR candidate_next_actions not empty -> PRIORITÀ 1 (Esplorazione Obbligatoria)
    coverage = contract.get("minimum_read_coverage") if isinstance(contract.get("minimum_read_coverage"), dict) else {}
    coverage_satisfied = coverage.get("coverage_satisfied") is True if coverage else False
    
    candidate_next_actions = contract.get("candidate_next_actions") if isinstance(contract.get("candidate_next_actions"), list) else []
    
    if not coverage_satisfied or (candidate_next_actions and len(candidate_next_actions) > 0):
        guidance["priority_action"] = "PRIORITÀ_1_ESPLORAZIONE_OBBLIGATORIA"
        guidance["reason"] = "coverage_not_satisfied_or_candidate_next_actions_not_empty"
        return guidance
    
    # Case 2: Evidence saturation -> PRIORITÀ 2 (Saturazione Evidenza)
    verified_reads = contract.get("verified_content_reads") if isinstance(contract.get("verified_content_reads"), list) else []
    verified_read_count = len(verified_reads) if isinstance(verified_reads, list) else 0
    
    if coverage_satisfied and verified_read_count < 8:
        guidance["priority_action"] = "PRIORITÀ_2_SATURAZIONE_EVIDENZA"
        guidance["reason"] = f"coverage_satisfied_but_verified_reads_count_{verified_read_count}_less_than_8"
        return guidance
    
    # Case 3: Finalization -> PRIORITÀ 3 (Finalizzazione)
    final_contract = contract.get("finalization_contract") if isinstance(contract.get("finalization_contract"), dict) else {}
    final_allowed = final_contract.get("final_allowed") is True if final_contract else False
    
    if coverage_satisfied and verified_read_count >= 8 and final_allowed:
        guidance["priority_action"] = "PRIORITÀ_3_FINALIZZAZIONE"
        guidance["reason"] = "coverage_satisfied_and_verified_reads_ge_8_and_final_allowed"
        
        # Checklist status
        guidance["checklist_status"] = {
            "coverage_satisfied": coverage_satisfied,
            "verified_reads_count_ge_8": verified_read_count >= 8,
            "final_allowed": final_allowed,
            "core_file_analyzed": False, # Placeholder - would need to check file types
        }
        return guidance
    
    # Case 4: Block -> PRIORITÀ 4 (Blocco)
    if not candidate_next_actions or len(candidate_next_actions) == 0:
        guidance["priority_action"] = "PRIORITÀ_4_BLOCCO"
        guidance["reason"] = "candidate_next_actions_empty_and_goal_unreachable"
    else:
        guidance["priority_action"] = "PRIORITÀ_1_ESPLORAZIONE_OBBLIGATORIA"
        guidance["reason"] = "candidate_next_actions_not_empty_requires_repo_read"
    
    return guidance


def format_guidance_as_instructions(guidance: dict[str, Any]) -> str:
    """Format the decision guide as natural language instructions for the planner."""
    if not isinstance(guidance, dict):
        return ""
    
    priority_action = guidance.get("priority_action", "PRIORITÀ_1_ESPLORAZIONE")
    reason = guidance.get("reason", "")
    checklist_status = guidance.get("checklist_status", {})
    
    instructions = []
    
    if priority_action == "PRIORITÀ_1_ESPLORAZIONE_OBBLIGATORIA":
        instructions.append("PRIORITÀ 1 (Esplorazione Obbligatoria): AZIONE UNICA CONSENTITA: repo_read. Scegli il primo path in candidate_next_actions che NON sia presente in verified_content_reads.")
    elif priority_action == "PRIORITÀ_2_SATURAZIONE_EVIDENZA":
        instructions.append("PRIORITÀ 2 (Saturazione Evidenza): AZIONE UNICA CONSENTITA: repo_read. Cerca nuovi file tramite repo_search o esplora sottodirectory fino a raggiungere ≥8 file letti.")
    elif priority_action == "PRIORITÀ_3_FINALIZZAZIONE":
        instructions.append("PRIORITÀ 3 (Finalizzazione): AZIONE: final. Checklist di uscita: coverage_satisfied==true, verified_content_reads.count>=8, final_allowed==true.")
    elif priority_action == "PRIORITÀ_4_BLOCCO":
        instructions.append("PRIORITÀ 4 (Blocco): action=block è consentita SOLO se candidate_next_actions è vuota, repo_search non produce risultati e il goal è oggettivamente irraggiungibile.")
    else:
        instructions.append("PROSEGUI CON TOOL/EVIDENZA: Continua con repo_read, search, o altri tool evidence-bound.")
    
    if checklist_status:
        instructions.append("\nCHECKLIST DI USCITA (HARD GATE):")
        for key, value in checklist_status.items():
            status = "TRUE" if value else "FALSE"
            instructions.append(f"- [ ] {key} == {status}?")
        
        if not all(checklist_status.values()):
            instructions.append("**Se uno solo di questi è FALSE → Torna a PRIORITÀ 1 (repo_read).**")
    
    return "\n".join(instructions)
