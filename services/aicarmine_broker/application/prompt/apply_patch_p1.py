import re
with open("C:/Users/carmi/AI/services/aicarmine_broker/application/prompt/pack_builder.py", "r", encoding="utf-8") as f:
    content = f.read()

# Patch P1: correggi _filter_candidate_actions_by_available_tools
old_code = '''    has_restriction = bool(available_tool_names)
    for action in candidate_actions if isinstance(candidate_actions, list) else []:
        if not isinstance(action, dict):
            continue
        tool = str(action.get("tool") or "").strip()
        if not tool:
            if not has_restriction:
                visible_actions.append(action)
            else:
                action["hidden_from_payload"] = True
                action["hidden_from_payload_reason"] = hidden_reason
                hidden_actions.append(action)
            continue
        if has_restriction and tool not in available_tool_names:'''

new_code = '''    transport_surface_empty = not available_tool_names
    for action in candidate_actions if isinstance(candidate_actions, list) else []:
        if not isinstance(action, dict):
            continue
        tool = str(action.get("tool") or "").strip()
        if not tool:
            if not transport_surface_empty:
                visible_actions.append(action)
            else:
                action["hidden_from_payload"] = True
                action["hidden_from_payload_reason"] = hidden_reason
                hidden_actions.append(action)
            continue
        if transport_surface_empty or tool not in available_tool_names:  # Patch P1: tools=[] è il caso più restrittivo'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open("C:/Users/carmi/AI/services/aicarmine_broker/application/prompt/pack_builder.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("Patch P1 applicata con successo")
else:
    print("Pattern non trovato per Patch P1")

# Verifica sintassi
import ast
try:
    ast.parse(content)
    print("Sintassi valida")
except SyntaxError as e:
    print(f"Errore di sintassi: {e}")
