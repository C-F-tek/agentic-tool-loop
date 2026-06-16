import re
with open('C:/Users/carmi/AI/services/aicarmine_broker/planner.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Patch A: Aggiungere comment per judge report in finalize_agentic_job
old_code = '''def finalize_agentic_job(
    job_id: str,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:'''

new_code = '''# Patch A: judge report per blocked_needs_attention
def finalize_agentic_job(
    job_id: str,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('C:/Users/carmi/AI/services/aicarmine_broker/planner.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patch A applicata (comment aggiunti in finalize_agentic_job)')
else:
    print('Pattern non trovato per Patch A')

# Verifica sintassi
import ast
try:
    ast.parse(content)
    print('Sintassi valida')
except SyntaxError as e:
    print(f'Errore di sintassi: {e}')
