import re
with open('C:/Users/carmi/AI/services/aicarmine_broker/application/evidence/final_quality.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Patch C corretta: non usare if/else inline, ma un approccio diverso
old_code = '''violations.append("repo_analysis_final_speculative_claims_without_evidence")'''

new_code = '''# Evidenza già acquisita (anche se inline truncated) -> violazione differente
if read_note_count > 0:
    violations.append("evidence_consumed_but_final_too_short")
else:
    violations.append("repo_analysis_final_speculative_claims_without_evidence")'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('C:/Users/carmi/AI/services/aicarmine_broker/application/evidence/final_quality.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patch C applicata con indentazione corretta')
else:
    print('Pattern non trovato per Patch C')

# Verifica sintassi
import ast
try:
    ast.parse(content)
    print('Sintassi valida')
except SyntaxError as e:
    print(f'Errore di sintassi: {e}')
