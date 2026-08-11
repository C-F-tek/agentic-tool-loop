# Agentic Loop - Data RAG Agent Usage Guide

## Quick Start Commands

### 1. Build RAG Index (Prerequisite for querying)
```powershell
# Build index from current directory
python main.py --action build --source-path .

# Build index with verbose output
python main.py --action build --source-path . --verbose

# Build index from specific path
python main.py --action build --source-path C:\path\to\project
```

### 2. Query the Database
```powershell
# Simple query
python main.py --query "What tables are in the database?"

# Query with max steps limit
python main.py --query "Who bought laptops?" --max-steps 5

# Auto mode with iterative refinement
python main.py --query "Show me all users" --auto --max-steps 10

# Verbose query
python main.py --query "What columns does the orders table have?" --verbose
```

### 3. Check RAG Index Status
```powershell
python main.py --action status
```

### 4. List Available MCP Tools
```powershell
python main.py --action list-tools
```

### 5. Run Diagnostics
```powershell
# Show diagnostics summary
python main.py --diagnostics-action summary

# Log a new error
python main.py --diagnostics-action log --diagnostics-error "Connection failed" --diagnostics-severity warning --diagnostics-category tool --diagnostics-step 3

# List pending errors
python main.py --diagnostics-action list

# Resolve an error
python main.py --diagnostics-action resolve --diagnostics-id BUG-001 --diagnostics-resolution "Fixed connection timeout"
```

### 6. File Agent Commands (Filesystem Navigation)
```powershell
# List files in directory
python agents/data_query.py --action list --path .

# Search for pattern in files
python agents/data_query.py --action search --pattern "def " --extension ".py"

# Read file content
python agents/data_query.py --action read --path README.md

# Natural language query about files
python agents/data_query.py --action query --question "What Python files contain database connectors?"
```

### 7. Ollama Tool Integration
```powershell
# Query via Ollama tool
python ollama_tools/run_tool.py --action query --question "What is the schema?"

# Build index via Ollama tool
python ollama_tools/run_tool.py --action build --source-path .

# List tool definition
python ollama_tools/run_tool.py --tool-def
```

### 8. MCP Client Direct Calls
```powershell
# Query SQLite database directly
python orchestrator/mcp_client.py --server sqlite_readonly --tool aicarmine_sqlite_readonly_query --args-file query.json

# Create query.json file:
# {"db": "state/rag_index.sqlite3", "sql": "SELECT COUNT(*) FROM chunks"}
```

## Example Database Queries

The example database (`state/example.db`) contains these tables:
- `users` - User information
- `orders` - Order records
- `products` - Product catalog

Sample questions to try:
1. "What tables exist in the database?"
2. "Who bought laptops?"
3. "Show me all users"
4. "What columns does the orders table have?"
5. "List all products"

## Troubleshooting

### Common Issues
1. **FTS match failed**: Index may need rebuilding - run `python main.py --action build`
2. **LLM generation failed**: Ollama not running or model not available - system falls back to source-based answers
3. **Database not found**: Check state/ directory for rag_index.sqlite3

### Log Files
Check `logs/diagnostics.ndjson` for error tracking and `logs/agentic_loop.log` for loop execution logs.