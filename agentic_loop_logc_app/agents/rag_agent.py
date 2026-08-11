"""
Data RAG Agent - Main agent implementation for data querying.

This module provides the DataRAGAgent class that orchestrates:
1. Database connection and schema extraction
2. RAG index building from database schemas and sample data
3. Query retrieval and reranking
4. Answer generation using LLM via Ollama or HTTP endpoint

The agent uses RAG as its primary tool, combined with database connectors
and schema analysis to answer natural language questions about data.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rag.indexer import RAGIndexer, ChunkInfo
from rag.retriever import RAGRetriever
from rag.reranker import RAGReranker
from data.connectors import DatabaseConnector
from data.schemas import DatabaseSchema, TableSchema, ColumnSchema

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Result of a query operation."""
    answer: str
    sources: list[dict]
    confidence: float
    schema_info: dict = field(default_factory=dict)
    execution_time_ms: int = 0


class DataRAGAgent:
    """Data RAG Agent - Orchestrates RAG-based data querying."""
    
    def __init__(
        self,
        config_path: str | None = None,
        index_db: str | None = None,
        db_type: str = "sqlite",
        db_path: str | None = None,
    ) -> None:
        """Initialize the agent with configuration."""
        # Load config if available
        if config_path is None:
            config_path = str(Path(__file__).parent.parent / "config" / "settings.ini")
        
        try:
            from config import load_settings
            settings = load_settings(config_path)
            
            db_type = settings.get("database", {}).get("type", "sqlite")
            db_path = settings.get("database", {}).get("path")
            index_db = settings.get("rag", {}).get("index_db")
        except (ImportError, FileNotFoundError):
            pass
        
        # Set defaults
        self.index_db = Path(index_db or "state/rag_index.sqlite3")
        self.db_type = db_type
        self.db_path = db_path
        
        # Initialize RAG components
        self.indexer = RAGIndexer(
            index_db=self.index_db,
            chunk_chars=4000,
            chunk_lines=180,
            max_file_bytes=2000000,
        )
        
        self.retriever = RAGRetriever(
            index_db=self.index_db,
            candidate_limit=80,
            top_k=12,
        )
        
        self.reranker = RAGReranker(
            enabled=True,
            strategy="hybrid",  # BM25 + TF-IDF + keyword overlap
            candidate_limit=12,
        )
        
        # Database connector
        self.connector: DatabaseConnector | None = None
        if db_type and db_path:
            self.connector = DatabaseConnector(db_type=db_type, db_path=db_path)
        
        # LLM endpoint (Ollama or HTTP)
        self.llm_url: str = "http://127.0.0.1:11434/api/generate"
        self.llm_model: str = "qwen2.5:32b"
    
    def build_index(self, source_path: str = ".", source_type: str = "filesystem") -> dict[str, Any]:
        """Build the RAG index from database schema and files."""
        logger.info(f"Building index from {source_path} ({source_type})")
        start_time = time.time()
        
        result = {
            "ok": False,
            "source": source_path,
            "source_type": source_type,
            "files_indexed": 0,
            "total_chunks": 0,
            "schema_tables": 0,
            "schema_columns": 0,
            "execution_time_ms": 0,
        }
        
        try:
            # 1. Index files using RAG indexer
            file_result = self.indexer.build_index(source_path, source_type)
            result["files_indexed"] = file_result.get("files_indexed", 0)
            result["total_chunks"] = file_result.get("total_chunks", 0)
            
            # 2. Extract and index database schema
            if self.connector:
                schema = self._extract_schema()
                if schema:
                    result["schema_tables"] = len(schema.get("tables", {}))
                    result["schema_columns"] = sum(len(t.get("columns", [])) for t in schema.get("tables", {}).values())
                    
                    # Index schema description into the RAG index
                    self._index_schema(schema)
            
            result["ok"] = True
            logger.info(f"Index built successfully in {time.time() - start_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Index build failed: {e}")
            result["error"] = str(e)
        
        result["execution_time_ms"] = int((time.time() - start_time) * 1000)
        return result
    
    def query(self, question: str) -> QueryResult:
        """Query the RAG index and generate an answer."""
        start_time = time.time()
        
        try:
            # 1. Retrieve relevant chunks
            candidates = self.retriever.retrieve(question)
            
            if not candidates:
                return QueryResult(
                    answer="No relevant sources found in the index.",
                    sources=[],
                    confidence=0.0,
                )
            
            # 2. Rerank candidates
            ranked = self.reranker.rerank(question, candidates)
            
            # 3. Select top-k results
            top_k = ranked[:self.reranker.candidate_limit]
            
            # 4. Calculate confidence based on scores
            avg_score = sum(c.get("rerank_score", 0) for c in top_k) / len(top_k) if top_k else 0
            confidence = min(1.0, abs(avg_score))
            
            # 5. Generate answer using LLM
            prompt = self._build_prompt(question, top_k)
            answer = self._generate_answer(prompt, question, top_k)
            
            execution_time = int((time.time() - start_time) * 1000)
            
            return QueryResult(
                answer=answer,
                sources=top_k,
                confidence=confidence,
                execution_time_ms=execution_time,
            )
            
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return QueryResult(
                answer=f"Error during query: {str(e)}",
                sources=[],
                confidence=0.0,
            )
    
    def _extract_schema(self) -> dict[str, Any]:
        """Extract database schema."""
        if not self.connector:
            return {}
        
        try:
            conn = self.connector.connect()
            schema = self.connector._get_sqlite_schema(conn) if self.db_type == "sqlite" else {}
            conn.close()
            return schema
        except Exception as e:
            logger.warning(f"Schema extraction failed: {e}")
            return {}
    
    def _index_schema(self, schema: dict[str, Any]) -> None:
        """Index database schema into the RAG index."""
        conn = sqlite3.connect(str(self.index_db))
        try:
            # Clear existing schema chunks
            conn.execute("DELETE FROM chunks WHERE kind = 'schema'")
            conn.execute("DELETE FROM chunks_fts WHERE kind = 'schema'")
            
            # Build schema description
            tables = schema.get("tables", {})
            for table_name, table_info in tables.items():
                columns = table_info.get("columns", [])
                
                # Create schema chunk
                content = f"Table: {table_name}\n"
                content += f"Description: {table_info.get('description', '')}\n"
                content += "Columns:\n"
                for col in columns:
                    content += f"- {col.get('name', '')} ({col.get('data_type', '')})"
                    if col.get("primary_key"):
                        content += " [PK]"
                    content += "\n"
                
                # Insert into chunks table
                conn.execute(
                    "INSERT INTO chunks (path, start_line, end_line, symbol, kind, content) VALUES (?, ?, ?, ?, ?, ?)",
                    (f"schema://{table_name}", 1, 1, table_name, "schema", content),
                )
                
                # Get row ID and insert into FTS
                cursor = conn.lastrowid
                conn.execute("INSERT INTO chunks_fts (content) VALUES (?)", (content,))
            
            conn.commit()
        finally:
            conn.close()
    
    def _build_prompt(self, question: str, sources: list[dict]) -> str:
        """Build LLM prompt with retrieved sources."""
        prompt = f"Question: {question}\n\n"
        prompt += "Relevant sources:\n\n"
        
        for i, source in enumerate(sources, 1):
            content = source.get("content", "")
            path = source.get("path", "unknown")
            prompt += f"[Source {i}] Path: {path}\n{content}\n\n"
        
        prompt += "Please answer the question based on these sources."
        return prompt
    
    def _generate_answer(self, prompt: str, question: str, sources: list[dict]) -> str:
        """Generate answer using Ollama API."""
        payload = {
            "model": self.llm_model,
            "prompt": prompt,
            "stream": False,
        }
        
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.llm_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            
            with urllib.request.urlopen(req, timeout=60) as res:
                raw = res.read()
                response = json.loads(raw.decode("utf-8"))
                return response.get("response", "No answer generated.")
                
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            logger.warning(f"LLM generation failed: {e}")
            # Fallback: return a simple response
            return self._simple_answer(question, sources)
    
    def _simple_answer(self, question: str, sources: list[dict]) -> str:
        """Simple answer generation when LLM is unavailable."""
        if not sources:
            return "No sources available to answer this question."
        
        # Extract key information from sources
        contents = [s.get("content", "") for s in sources[:5]]
        combined = "\n\n".join(contents)
        
        return f"Retrieved information:\n{combined}\n\nPlease review these sources to answer: {question}"