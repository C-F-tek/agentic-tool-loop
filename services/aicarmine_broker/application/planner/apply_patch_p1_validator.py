import re
with open('C:/Users/carmi/from aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

AI/services/aicarmine_broker/application/planner/validator.py', 'r', encoding='utf-8') as f:
    content = f.read()

# P1: Correggere condizione di promotion per required_next_tool_call={}
old_code = '''and not isinstance(contract.get("required_next_tool_call"), dict)'''

new_code = '''and (not contract.get("required_next_tool_call") or \
        not isinstance(contract.get("required_next_tool_call"), dict) or \
        not bool(contract.get("required_next_tool_call")))'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('C:/Users/carmi/AI/services/aicarmine_broker/application/planner/validator.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('P1 applicata: promotion ora scatta anche per required_next_tool_call={}')
else:
    print('Pattern non trovato per P1 - controllo contesto...')

# Verifica sintassi
import ast
try:
    ast.parse(content)
    print('Sintassi valida dopo correzione P1')
except SyntaxError as e:
    print(f'Errore di sintassi: {e}')
