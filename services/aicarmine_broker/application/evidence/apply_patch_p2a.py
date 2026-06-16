import re
with open('C:/Users/carmi/AI/services/aicarmine_broker/application/evidence/builder.py', 'r') as f:
    content = f.read()

# Patch P2a: correggere suggested_next_tool a usare valid_unread_suggested_read_paths
old_code = '"suggested_next_tool": "repo_read" if semantic_suggested_read_paths else ""'
new_code = '"suggested_next_tool": "repo_read" if valid_unread_suggested_read_paths else ""  # Patch P2a: usare valid_unread invece di semantic_suggested_read_paths'

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('C:/Users/carmi/AI/services/aicarmine_broker/application/evidence/builder.py', 'w') as f:
        f.write(content)
    print('Patch P2a applicata: suggested_next_tool ora usa valid_unread_suggested_read_paths')
else:
    print('Pattern non trovato per Patch P2a')

# Verifica sintassi
import ast
try:
    ast.parse(content)
    print('Sintassi valida')
except SyntaxError as e:
    print(f'Errore di sintassi: {e}')
