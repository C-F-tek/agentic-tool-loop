import re
with open('C:/Users/carmi/AI/services/aicarmine_broker/application/evidence/final_quality.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Patch C: Aggiungere logica per distinguere truncated + full_context da evidenza assente
# Troviamo la funzione che genera violazioni speculative e aggiungiamo il check

old_code = '''violations.append("repo_analysis_final_speculative_claims_without_evidence")'''

new_code = '''# Check se full_context è disponibile (inline truncation non è evidenza assente)
read_note_count = metrics.get("read_note_count", 0) or len(metrics.get("verified_content_reads", [])) or 0
if read_note_count > 0:
    # Evidenza già acquisita, anche se inline truncated
    violations.append("evidence_consumed_but_final_too_short")
else:
    violations.append("repo_analysis_final_speculative_claims_without_evidence")'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('C:/Users/carmi/AI/services/aicarmine_broker/application/evidence/final_quality.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patch C applicata: final-quality ora distingue truncated+full_context da evidenza assente')
else:
    # Cerca pattern alternativo
    old_code_alt = '''violations.append("repo_analysis_final_speculative_claims_without_evidence")'''
    if old_code_alt in content:
        print('Pattern non trovato per Patch C - la violazione potrebbe essere già gestita diversamente')
    else:
        print('Pattern non trovato per Patch C')

# Verifica sintassi
import ast
try:
    ast.parse(content)
    print('Sintassi valida')
except SyntaxError as e:
    print(f'Errore di sintassi: {e}')
