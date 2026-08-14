"""Test Ollama model native tool call support."""
import requests
import json

url = "http://127.0.0.1:11434/api/chat"
model = "Qwen_Qwen3.6-35B_v1:latest"

tools = [
    {
        "name": "final_answer",
        "description": "Return final answer",
        "parameters": {
            "type": "object",
            "properties": {
                "answer": {"type": "string"}
            }
        }
    },
    {
        "name": "repo_read",
        "description": "Read a file",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "max_chars": {"type": "integer"}
            }
        }
    }
]

data = {
    "model": model,
    "messages": [
        {"role": "user", "content": "test"}
    ],
    "stream": False,
    "tools": tools
}

print(f"Testing Ollama model {model} at {url}")
print(f"Tools: {[t['name'] for t in tools]}")
print()

try:
    r = requests.post(url, json=data, timeout=30)
    print(f"Status: {r.status_code}")
    print()
    
    if r.status_code == 200:
        result = r.json()
        print(f"Response keys: {list(result.keys())}")
        print()
        
        # Check for tool_calls in message
        message = result.get("message", {})
        print(f"Message role: {message.get('role')}")
        print(f"Message content: {message.get('content', '')[:500]}")
        
        tool_calls = message.get("tool_calls", [])
        print(f"Tool calls count: {len(tool_calls)}")
        
        if tool_calls:
            for tc in tool_calls:
                print(f"  Tool call: {json.dumps(tc, indent=2, ensure_ascii=False)[:500]}")
        else:
            print("  No tool_calls found in message")
        
        # Print full response for inspection
        print()
        print(f"Full response preview (first 1000 chars):")
        print(json.dumps(result, indent=2, ensure_ascii=False)[:1000])
    else:
        print(f"Error response: {r.text[:1000]}")
        
except Exception as e:
    print(f"Error: {e}")