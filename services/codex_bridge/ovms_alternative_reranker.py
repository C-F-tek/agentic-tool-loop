#!/usr/bin/env python3
"""
Alternative reranker server using sentence-transformers CrossEncoder.

Replaces OVMS with a Python-native reranker that works on Windows
without requiring OpenVINO Model Server installation.

API endpoints:
  GET  /health              - Health check
  GET  /models/list         - List available models
  POST /v3/rerank           - Rerank documents (OVMS-compatible)
  GET  /v2/models/{name}/ready - Model readiness check

Usage:
  python ovms_alternative_reranker.py --port 3550 --model BAAI/bge-reranker-v2-m3
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, List

from sentence_transformers import CrossEncoder

# Global state (using mutable container to avoid global declaration issues)
_state = {
    "model": None,
    "model_name": "BAAI/bge-reranker-v2-m3",
    "ready": False,
}
_lock = threading.Lock()


def load_model(model_name: str) -> CrossEncoder:
    """Load the CrossEncoder model."""
    print(f"Loading reranker model: {model_name}", flush=True)
    encoder = CrossEncoder(model_name, trust_remote_code=True)
    print(f"Model loaded successfully.", flush=True)
    return encoder


class RerankerHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the reranker service."""

    def log_message(self, format: str, *args: Any) -> None:
        """Override to use print with flush."""
        print(f"[RerankerServer] {format % args}", flush=True)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json({
                "status": "healthy",
                "model": _state["model_name"],
                "ready": _state["ready"],
            })
        elif self.path == "/models/list":
            self._send_json({
                "models": [_state["model_name"]] if _state["ready"] else []
            })
        elif self.path.startswith("/v2/models/") and self.path.endswith("/ready"):
            if _state["ready"]:
                self._send_json({"status": "READY"})
            else:
                self._send_json({"status": "UNAVAILABLE"}, status_code=503)
        else:
            self._send_json({"error": "not_found"}, status_code=404)

    def do_POST(self) -> None:
        if self.path == "/v3/rerank":
            self._handle_rerank()
        else:
            self._send_json({"error": "not_found"}, status_code=404)

    def _handle_rerank(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "invalid_json"}, status_code=400)
            return

        query: str = data.get("query", "")
        documents: List[str] = data.get("documents", [])
        top_k: int = data.get("top_k", len(documents))
        model: str = data.get("model", _state["model_name"])

        if not query or not documents:
            self._send_json({"error": "missing query or documents"}, status_code=400)
            return

        if model != _state["model_name"]:
            self._send_json({"error": f"model {model} not available"}, status_code=400)
            return

        if not _state["ready"]:
            self._send_json({"error": "model not ready"}, status_code=503)
            return

        # Compute scores using CrossEncoder
        pairs = [[query, doc] for doc in documents]
        scores = _state["model"].predict(pairs, show_progress_bar=False, batch_size=32)

        # Create results with indices sorted by score descending
        indexed_scores = [(i, float(s)) for i, s in enumerate(scores)]
        indexed_scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in indexed_scores[:top_k]:
            results.append({
                "index": idx,
                "document": {"text": documents[idx]},
                "relevance_score": score
            })

        self._send_json({
            "model": _state["model_name"],
            "results": results
        })

    def _send_json(self, data: Dict[str, Any], status_code: int = 200) -> None:
        response = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def main() -> int:
    parser = argparse.ArgumentParser(description="Python-native Reranker Server (OVMS alternative)")
    parser.add_argument("--port", type=int, default=3550, help="Port to listen on")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--model", type=str, default="BAAI/bge-reranker-v2-m3", help="CrossEncoder model name")
    args = parser.parse_args()

    _state["model_name"] = args.model

    try:
        _state["model"] = load_model(args.model)
        _state["ready"] = True
    except Exception as exc:
        print(f"ERROR loading model: {exc}", flush=True)
        return 1

    server = HTTPServer((args.host, args.port), RerankerHandler)
    print(f"Reranker server listening on {args.host}:{args.port}", flush=True)
    print(f"Health check: http://{args.host}:{args.port}/health", flush=True)
    print(f"Rerank endpoint: http://{args.host}:{args.port}/v3/rerank", flush=True)
    print(f"Model: {_state['model_name']}", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.", flush=True)
        server.shutdown()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())