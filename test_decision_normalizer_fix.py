"""Test that decision_normalizer properly handles {"tool_calls": [...]} format."""
import json
import sys
sys.path.insert(0, 'services')

from aicarmine_broker.application.planner.decision_normalizer import normalize_planner_decision
from aicarmine_broker.tool_contract import parse_tool_call

# Test 1: Original test case - name-based format
print("=== Test 1: name-based format (existing) ===")
raw_text = '{"tool_calls": [{"name": "planner_scratchpad_read", "arguments": {"kind": "prompt_context_window", "document_id": "prompt-context-1e91674c72f4a2107c66a9d5", "offset": 16384, "max_chars": 16384}}]}'

result = normalize_planner_decision(raw_text, 'analizza repo', 1, {})
print('Result:', json.dumps(result, indent=2))
assert result.get('action') == 'tool', f"Expected action='tool' but got '{result.get('action')}'"
assert result.get('tool') == 'planner_scratchpad_read', f"Expected tool='planner_scratchpad_read' but got '{result.get('tool')}'"
print("Test 1 PASSED")

# Test 2: Ollama native format - {"tool": "...", "arguments": {...}}
print("\n=== Test 2: Ollama native format (from job-f08a3dfb) ===")
raw_text_ollama = '{"tool_calls": [{"tool": "repo_list_files", "arguments": {"path": "services", "limit": 120}}]}'

result_ollama = normalize_planner_decision(raw_text_ollama, 'fai una analisi sulla repo e descrivila', 1, {})
print('Result:', json.dumps(result_ollama, indent=2))
assert result_ollama.get('action') == 'tool', f"Expected action='tool' but got '{result_ollama.get('action')}'"
assert result_ollama.get('tool') == 'repo_list_files', f"Expected tool='repo_list_files' but got '{result_ollama.get('tool')}'"
assert result_ollama.get('json_extraction_fallback') is True, "Expected json_extraction_fallback=True"
assert result_ollama.get('json_extraction_source') == 'strict_json_native_conversion', f"Expected source='strict_json_native_conversion' but got '{result_ollama.get('json_extraction_source')}'"
print("Test 2 PASSED")

# Test 3: parse_tool_call with Ollama native format
print("\n=== Test 3: parse_tool_call with Ollama native format ===")
call_ollama = {"tool": "repo_list_files", "arguments": {"path": "services", "limit": 120}}
name, args = parse_tool_call(call_ollama)
print(f"parse_tool_call result: name={name}, args={args}")
assert name == 'repo_list_files', f"Expected name='repo_list_files' but got '{name}'"
assert args == {"path": "services", "limit": 120}, f"Expected args dict but got {args}"
print("Test 3 PASSED")

# Test 4: parse_tool_call with OpenAI format (function object)
print("\n=== Test 4: parse_tool_call with OpenAI function format ===")
call_openai = {"function": {"name": "repo_read", "arguments": {"path": "README.md"}}}
name, args = parse_tool_call(call_openai)
print(f"parse_tool_call result: name={name}, args={args}")
assert name == 'repo_read', f"Expected name='repo_read' but got '{name}'"
assert args == {"path": "README.md"}, f"Expected args dict but got {args}"
print("Test 4 PASSED")

# Test 5: parse_tool_call with stringified JSON arguments (Ollama common)
print("\n=== Test 5: parse_tool_call with stringified JSON arguments ===")
call_string_args = {"tool": "repo_search", "arguments": '{"query": "test", "path": "."}'}
name, args = parse_tool_call(call_string_args)
print(f"parse_tool_call result: name={name}, args={args}")
assert name == 'repo_search', f"Expected name='repo_search' but got '{name}'"
assert isinstance(args, dict), f"Expected args to be dict but got {type(args)}"
assert args.get('query') == 'test', f"Expected args.query='test' but got {args}"
print("Test 5 PASSED")

# Test 6: Real-world format from job-f08a3dfb step-5 (repo_read with paths array)
print("\n=== Test 6: Real-world format from job-f08a3dfb ===")
raw_text_real = '{"tool_calls": [{"tool": "repo_read", "arguments": {"paths": ["services/aicarmine-executor-server.ps1", "services/aicarmine-executor-server.py"], "max_chars": 32768, "max_paths": 16}}]}'

result_real = normalize_planner_decision(raw_text_real, 'fai una analisi sulla repo e descrivila', 5, {})
print('Result:', json.dumps(result_real, indent=2))
assert result_real.get('action') == 'tool', f"Expected action='tool' but got '{result_real.get('action')}'"
assert result_real.get('tool') == 'repo_read', f"Expected tool='repo_read' but got '{result_real.get('tool')}'"
print("Test 6 PASSED")

print("\n=== ALL TESTS PASSED ===")