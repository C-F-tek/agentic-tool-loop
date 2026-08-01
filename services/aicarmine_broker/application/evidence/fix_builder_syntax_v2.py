import re
with open('C:/Users/carmi/from aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

AI/services/aicarmine_broker/application/evidence/builder.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Aggiungi virgola alla fine della riga 1534 (commento) per separare correttamente le coppie del dizionario
old_code = '''                "suggested_next_tool": "repo_read" if valid_unread_suggested_read_paths else ""  # Patch P2a: usare valid_unread'''

new_code = '''                "suggested_next_tool": "repo_read" if valid_unread_suggested_read_paths else "",  # Patch P2a: usare valid_unread'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('C:/Users/carmi/AI/services/aicarmine_broker/application/evidence/builder.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Virgola aggiunta alla fine del commento - SyntaxError dovrebbe essere risolto')
else:
    print('Pattern non trovato per correzione virgola')

# Verifica sintassi
import ast
try:
    ast.parse(content)
    print('Sintassi valida dopo correzione')
except SyntaxError as e:
    print(f'Errore di sintassi: {e}')
