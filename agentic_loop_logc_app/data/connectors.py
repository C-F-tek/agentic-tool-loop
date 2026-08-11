"""
Data Connectors - Database connectors for the Data RAG Agent.

This module provides connectors for SQLite, PostgreSQL, and CSV databases.
"""

from __future__ import annotations

import csv
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class DatabaseConnector:
    """Database connector for querying and indexing data."""
    
    db_type: str = "sqlite"
    db_path: Optional[str] = None
    host: str = "localhost"
    port: int = 5432
    name: str = "data"
    user: str = "admin"
    password: str = ""
    
    def connect(self) -> Any:
        """Connect to the database based on type."""
        if self.db_type == "sqlite":
            return self._connect_sqlite()
        elif self.db_type == "postgresql":
            return self._connect_postgresql()
        elif self.db_type == "csv":
            return self._connect_csv()
        else:
            raise ValueError(f"Unsupported database type: {self.db_type}")
    
    def _connect_sqlite(self) -> sqlite3.Connection:
        """Connect to SQLite database."""
        if not self.db_path:
            raise ValueError("SQLite db_path is required")
        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def _connect_postgresql(self) -> Any:
        """Connect to PostgreSQL database."""
        try:
            import psycopg2
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.name,
                user=self.user,
                password=self.password,
            )
            return conn
        except ImportError:
            logger.error("psycopg2 not installed. Install with: pip install psycopg2-binary")
            raise RuntimeError("PostgreSQL connector requires psycopg2")
    
    def _connect_csv(self) -> list[dict[str, str]]:
        """Connect to CSV file(s)."""
        if not self.db_path:
            raise ValueError("CSV db_path is required")
        path = Path(self.db_path)
        
        if path.is_file():
            return self._read_csv_file(path)
        elif path.is_dir():
            return self._read_csv_directory(path)
        else:
            raise FileNotFoundError(f"CSV path not found: {self.db_path}")
    
    def _read_csv_file(self, path: Path) -> list[dict[str, str]]:
        """Read a single CSV file."""
        results = []
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                results.append(dict(row))
        logger.info(f"Read {len(results)} rows from {path}")
        return results
    
    def _read_csv_directory(self, path: Path) -> list[dict[str, str]]:
        """Read all CSV files in a directory."""
        results = []
        for csv_file in path.glob("*.csv"):
            results.extend(self._read_csv_file(csv_file))
        logger.info(f"Read {len(results)} rows from {path}")
        return results
    
    def get_schema(self) -> dict[str, Any]:
        """Get the database schema for indexing."""
        conn = self.connect()
        try:
            if self.db_type == "sqlite":
                return self._get_sqlite_schema(conn)
            elif self.db_type == "postgresql":
                return self._get_postgresql_schema(conn)
            elif self.db_type == "csv":
                return self._get_csv_schema(conn)
        finally:
            conn.close()
    
    def _get_sqlite_schema(self, conn: sqlite3.Connection) -> dict[str, Any]:
        """Get SQLite schema."""
        tables = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table'"
        ).fetchall()
        
        schema = {}
        for table_name, table_sql in tables:
            columns = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
            schema[table_name] = {
                "columns": [dict(c) for c in columns],
                "sql": table_sql,
            }
        
        logger.info(f"Got SQLite schema with {len(schema)} tables")
        return schema
    
    def _get_postgresql_schema(self, conn: Any) -> dict[str, Any]:
        """Get PostgreSQL schema."""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT table_name, column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema = 'public'
        """)
        rows = cursor.fetchall()
        
        schema = {}
        for row in rows:
            table = row[0]
            if table not in schema:
                schema[table] = {"columns": [], "sql": ""}
            schema[table]["columns"].append({
                "name": row[1],
                "type": row[2],
            })
        
        logger.info(f"Got PostgreSQL schema with {len(schema)} tables")
        return schema
    
    def _get_csv_schema(self, conn: list[dict[str, str]]) -> dict[str, Any]:
        """Get CSV schema."""
        if not conn:
            return {}
        
        sample = conn[0]
        schema = {"csv_files": {"columns": [{"name": k, "type": "string"} for k in sample.keys()]}}
        logger.info(f"Got CSV schema with columns: {list(sample.keys())}")
        return schema
    
    def query_data(self, sql: str) -> list[dict[str, Any]]:
        """Execute a read-only query."""
        conn = self.connect()
        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            if cursor.description:
                return [dict(row) for row in cursor.fetchall()]
            return []
        finally:
            conn.close()