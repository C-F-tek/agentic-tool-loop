import re
with open('C:/Users/carmi/AI/services/aicarmine_broker/application/evidence/final_quality.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Correggere indentazione della riga 814 (if read_note_count > 0)
old_code = '''        violations.append("repo_analysis_final_speculative_claims_without_evidence")
    if red_flags.get("generic_no_issue_phrases")'''

new_code = '''        violations.append("repo_analysis_final_speculative_claims_without_evidence")
        if red_flags.get("generic_no_issue_phrases")'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('C:/Users/carmi/AI/services/aicarmine_broker/application/evidence/final_quality.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Indentazione corretta per Patch C')
else:
    print('Pattern non trovato per correzione indentazione')

# Verifica sintassi
import ast
try:
    ast.parse(content)
    print('Sintassi valida dopo correzione indentazione')
except SyntaxError as e:
    print(f'Errore di sintassi: {e}')
