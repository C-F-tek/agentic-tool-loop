import re
with open('C:/Users/carmi/AI/services/aicarmine_broker/application/evidence/final_quality.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Patch C: sostituire la violazione speculative_terms con logica che distingue truncated+full_context
old_code = '''        if red_flags.get("speculative_terms"):
            violations.append("repo_analysis_final_speculative_claims_without_evidence")'''

new_code = '''        # Patch C: distingue truncated+full_context da evidenza assente
        if red_flags.get("speculative_terms"):
            read_note_count = metrics.get("read_note_count", 0) or len(metrics.get("verified_content_reads", [])) or 0
            if read_note_count > 0:
                violations.append("evidence_consumed_but_final_too_short")
            else:
                violations.append("repo_analysis_final_speculative_claims_without_evidence")'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('C:/Users/carmi/AI/services/aicarmine_broker/application/evidence/final_quality.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patch C applicata con successo')
else:
    print('Pattern non trovato per Patch C')

# Verifica sintassi
import ast
try:
    ast.parse(content)
    print('Sintassi valida')
except SyntaxError as e:
    print(f'Errore di sintassi: {e}')
