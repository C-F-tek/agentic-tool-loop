import re
with open('C:/Users/carmi/AI/services/aicarmine_broker/application/evidence/builder.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Rimuovi la virgola dal commento (causa SyntaxError)
old_code = '''                "suggested_next_tool": "repo_read" if valid_unread_suggested_read_paths else ""  # Patch P2a: usare valid_unread invece di semantic_suggested_read_paths,'''

new_code = '''                "suggested_next_tool": "repo_read" if valid_unread_suggested_read_paths else ""  # Patch P2a: usare valid_unread'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('C:/Users/carmi/AI/services/aicarmine_broker/application/evidence/builder.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Virgola rimossa dal commento - SyntaxError dovrebbe essere risolto')
else:
    print('Pattern non trovato per correzione virgola')

# Verifica sintassi
import ast
try:
    ast.parse(content)
    print('Sintassi valida dopo correzione')
except SyntaxError as e:
    print(f'Errore di sintassi: {e}')
