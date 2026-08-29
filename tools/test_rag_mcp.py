#!/usr/bin/env python3
"""Test script for RAG MCP server - search planner from project."""
import json
import subprocess
import sys

SERVER_SCRIPT = "services/codex_bridge/rag_mcp_server.py"
REPO_ROOT = r"c:\Users\someo\agentic-tool-loop"


def send_msg(proc, msg):
    data = (json.dumps(msg) + "\n").encode("utf-8")
    proc.stdin.write(data.decode())
    proc.stdin.flush()


def recv_msg(proc):
    line = proc.stdout.readline()
    if not line:
        return None
    return json.loads(line.strip())


def main():
    proc = subprocess.Popen(
        ["python", "-u", SERVER_SCRIPT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        # Initialize
        print("=== Initializing ===")
        send_msg(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        resp = recv_msg(proc)
        print(json.dumps(resp.get("result"), indent=2))

        # Call reindex first to build the index
        print("\n=== Rebuilding RAG Index (filesystem mode) ===")
        send_msg(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "aicarmine_rag_reindex",
                    "arguments": {
                        "search_path": REPO_ROOT,
                        "source": "filesystem",
                        "mode": "full",
                    },
                },
            },
        )
        resp = recv_msg(proc)
        result = resp.get("result", {})
        inner = result if isinstance(result, dict) else {}
        actual_result = inner.get("result", {})
        files_indexed = actual_result.get("files_indexed", 0)
        chunks_indexed = actual_result.get("chunks_indexed", 0)
        db = inner.get("db", "")
        print(f"Files indexed: {files_indexed}")
        print(f"Chunks indexed: {chunks_indexed}")
        print(f"DB path: {db}")

        # Now search for planner
        print("\n=== Searching for 'planner' ===")
        send_msg(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "aicarmine_rag_search",
                    "arguments": {
                        "query": "planner decision normalizer execution digest evidence",
                        "search_path": REPO_ROOT,
                        "top_k": 15,
                        "candidate_limit": 80,
                        "rerank": False,
                    },
                },
            },
        )
        resp = recv_msg(proc)
        result = resp.get("result", {})

        if isinstance(result, dict):
            chunks = result.get("chunks", [])
            query = result.get("query", "")
            candidate_count = result.get("candidate_count", 0)
            returned = result.get("returned", 0)

            print(f"\nQuery: {query}")
            print(f"Candidates found: {candidate_count}")
            print(f"Chunks returned: {returned}\n")

            for i, chunk in enumerate(chunks, 1):
                path = chunk.get("path", "N/A")
                content = chunk.get("content", "").strip()[:300]
                start_line = chunk.get("start_line", "N/A")
                end_line = chunk.get("end_line", "N/A")
                symbol = chunk.get("symbol", "")

                print(f"[{i}] Path: {path}")
                print(f"    Lines: {start_line}-{end_line}")
                print(f"    Symbol: {symbol}")
                print(f"    Content preview:\n    ---\n    {content}\n    ---")
                print()

    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
