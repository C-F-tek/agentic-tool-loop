"""
Data Schemas - Schema definitions for the Data RAG Agent.

This module provides schema definitions and validation for database structures.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ColumnSchema:
    """Represents a column in a table."""
    name: str
    data_type: str
    nullable: bool = True
    default: Any = None
    primary_key: bool = False


@dataclass
class TableSchema:
    """Represents a table schema."""
    name: str
    columns: list[ColumnSchema] = field(default_factory=list)
    description: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert schema to dictionary."""
        return {
            "name": self.name,
            "columns": [c.__dict__ for c in self.columns],
            "description": self.description,
        }


@dataclass
class DatabaseSchema:
    """Represents a complete database schema."""
    tables: dict[str, TableSchema] = field(default_factory=dict)
    description: str = ""
    
    def add_table(self, schema: TableSchema) -> None:
        """Add a table schema."""
        self.tables[schema.name] = schema
        logger.info(f"Added table: {schema.name} with {len(schema.columns)} columns")
    
    def get_table(self, name: str) -> TableSchema | None:
        """Get a table schema by name."""
        return self.tables.get(name)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert schema to dictionary."""
        return {
            "description": self.description,
            "tables": {k: v.to_dict() for k, v in self.tables.items()},
        }
    
    def build_index_prompt(self) -> str:
        """Build a prompt for indexing the schema."""
        lines = [f"# Database Schema\n"]
        if self.description:
            lines.append(f"{self.description}\n")
        
        for name, table in self.tables.items():
            lines.append(f"## Table: {name}")
            if table.description:
                lines.append(f"\n{table.description}\n")
            
            lines.append("| Column | Type | Nullable | Default | Primary Key |")
            lines.append("|--------|------|----------|---------|-------------|")
            for col in table.columns:
                lines.append(
                    f"| {col.name} | {col.data_type} | {'Yes' if col.nullable else 'No'} | "
                    f"{str(col.default) if col.default is not None else 'None'} | {'Yes' if col.primary_key else 'No'} |"
                )
            lines.append("")
        
        return "\n".join(lines)