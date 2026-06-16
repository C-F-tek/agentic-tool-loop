import re
with open('C:/Users/carmi/AI/services/aicarmine_broker/application/planner/validator.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Patch B più semplice: solo aggiungere il comment e non duplicare codice
old_code = '''contract["required_next_progress"] = (
            "Duplicate repo_read detected: read/analysis path already exists in successful repo_read history. "
            "Use required_working_set and verified_content_reads to consume the evidence; "
            "do not repeat full-path repo_read for already successful paths."
        )'''

new_code = '''# Patch B: duplicate repo_read recovery con evidence consumption route
contract["required_next_progress"] = (
    "Duplicate repo_read detected. Consume verified evidence windows or rewrite final from existing reads."
)'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('C:/Users/carmi/AI/services/aicarmine_broker/application/planner/validator.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patch B applicata (versione semplificata)')
else:
    print('Pattern non trovato per Patch B')

# Verifica sintassi
import ast
try:
    ast.parse(content)
    print('Sintassi valida')
except SyntaxError as e:
    print(f'Errore di sintassi: {e}')
