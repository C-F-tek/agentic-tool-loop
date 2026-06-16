import re
with open('C:/Users/carmi/AI/services/aicarmine_broker/application/planner/validator.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Patch B: Aggiungere evidence consumption route quando repo_read_already_successful
old_code = '''contract["required_next_progress"] = (
            "Duplicate repo_read detected: read/analysis path already exists in successful repo_read history. "
            "Use required_working_set and verified_content_reads to consume the evidence; "
            "do not repeat full-path repo_read for already successful paths."
        )'''

new_code = '''# Patch B: evidence consumption route per duplicate repo_read
contract["required_next_progress"] = (
    "Duplicate repo_read detected. Consume verified evidence windows or rewrite final from existing reads."
)
# Se esiste prompt_context_window, proponi planner_scratchpad_read
prompt_context_available = contract.get("prompt_context_document_id") is not None
if prompt_context_available:
    required_next_tool_call = {
        "tool": "planner_scratchpad_read",
        "arguments": {
            "kind": "prompt_context_window",
            "document_id": str(contract.get("prompt_context_document_id")),
            "offset": "next_or_relevant",
            "max_chars": 6000,
        },
        "reason": "repo_read artifact already exists; consume verified prompt window instead of repeating repo_read",
        "source": "duplicate_repo_read_recovery_contract",
        "validated": True,
    }
    contract["required_next_tool_call"] = required_next_tool_call
else:
    # Altrimenti final rewrite allowed from verified evidence
    final_contract = (
        contract.get("finalization_contract")
        if isinstance(contract.get("finalization_contract"), dict)
        else {}
    )
    final_contract["planner_may_choose_final"] = True
    final_contract.setdefault("reason", "Duplicate repo_read: use verified evidence for final rewrite")
    contract["finalization_contract"] = final_contract'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('C:/Users/carmi/AI/services/aicarmine_broker/application/planner/validator.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patch B applicata: duplicate repo_read ora ha evidence consumption route')
else:
    print('Pattern non trovato per Patch B - controllo contesto...')

# Verifica sintassi
import ast
try:
    ast.parse(content)
    print('Sintassi valida')
except SyntaxError as e:
    print(f'Errore di sintassi: {e}')
