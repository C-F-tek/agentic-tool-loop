"""Test that decision_normalizer properly handles {"tool_calls": [...]} format."""
import json
import sys
sys.path.insert(0, 'services')

from aicarmine_broker.application.planner.decision_normalizer import normalize_planner_decision

# Test case: mimic the exact output from job-7231228c step-004
raw_text = '{"tool_calls": [{"name": "planner_scratchpad_read", "arguments": {"kind": "prompt_context_window", "document_id": "prompt-context-1e91674c72f4a2107c66a9d5", "offset": 16384, "max_chars": 16384}}]}'

result = normalize_planner_decision(raw_text, 'analizza repo', 1, {})
print('Result:', json.dumps(result, indent=2))
print()
print('action:', result.get('action'))
print('tool:', result.get('tool'))
print('json_extraction_fallback:', result.get('json_extraction_fallback'))
print('json_extraction_source:', result.get('json_extraction_source'))

# Verify fix works
assert result.get('action') == 'tool', f"Expected action='tool' but got '{result.get('action')}'"
assert result.get('tool') == 'planner_scratchpad_read', f"Expected tool='planner_scratchpad_read' but got '{result.get('tool')}'"
assert result.get('json_extraction_fallback') is True, "Expected json_extraction_fallback=True"
assert result.get('json_extraction_source') == 'strict_json_native_conversion', f"Expected source='strict_json_native_conversion' but got '{result.get('json_extraction_source')}'"

print()
print("ALL TESTS PASSED")