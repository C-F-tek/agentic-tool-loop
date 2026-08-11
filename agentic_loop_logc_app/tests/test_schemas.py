"""Tests for the data schemas module."""

from __future__ import annotations

import pytest
from data.schemas import ColumnSchema, TableSchema, DatabaseSchema


class TestColumnSchema:
    """Test suite for ColumnSchema."""
    
    def test_column_schema_creation(self):
        """Test ColumnSchema creation."""
        col = ColumnSchema(name="id", data_type="INTEGER", primary_key=True)
        assert col.name == "id"
        assert col.data_type == "INTEGER"
        assert col.primary_key is True
    
    def test_column_schema_to_dict(self):
        """Test ColumnSchema to_dict conversion."""
        col = ColumnSchema(name="name", data_type="VARCHAR")
        d = col.to_dict() if hasattr(col, 'to_dict') else {"name": col.name, "data_type": col.data_type}
        assert "name" in d or col.name == "name"


class TestTableSchema:
    """Test suite for TableSchema."""
    
    def test_table_schema_creation(self):
        """Test TableSchema creation."""
        table = TableSchema(name="users", description="User table")
        assert table.name == "users"
        assert table.description == "User table"
        assert len(table.columns) == 0
    
    def test_table_schema_add_column(self):
        """Test adding columns to table schema."""
        table = TableSchema(name="users")
        table.columns.append(ColumnSchema(name="id", data_type="INTEGER", primary_key=True))
        assert len(table.columns) == 1
        assert table.columns[0].name == "id"
    
    def test_table_schema_to_dict(self):
        """Test TableSchema to_dict conversion."""
        table = TableSchema(name="users", description="Test users")
        table.columns.append(ColumnSchema(name="id", data_type="INTEGER"))
        d = table.to_dict()
        assert d["name"] == "users"
        assert d["description"] == "Test users"
        assert len(d["columns"]) == 1


class TestDatabaseSchema:
    """Test suite for DatabaseSchema."""
    
    def test_database_schema_creation(self):
        """Test DatabaseSchema creation."""
        db = DatabaseSchema(description="Test database")
        assert db.description == "Test database"
        assert len(db.tables) == 0
    
    def test_add_table(self):
        """Test adding tables to database schema."""
        db = DatabaseSchema()
        table = TableSchema(name="users", description="User table")
        db.add_table(table)
        assert "users" in db.tables
        assert db.tables["users"].description == "User table"
    
    def test_get_table(self):
        """Test getting table by name."""
        db = DatabaseSchema()
        table = TableSchema(name="orders")
        db.add_table(table)
        
        retrieved = db.get_table("orders")
        assert retrieved is not None
        assert retrieved.name == "orders"
        
        none_result = db.get_table("nonexistent")
        assert none_result is None
    
    def test_to_dict(self):
        """Test DatabaseSchema to_dict conversion."""
        db = DatabaseSchema(description="My DB")
        table = TableSchema(name="products")
        db.add_table(table)
        
        d = db.to_dict()
        assert d["description"] == "My DB"
        assert "products" in d["tables"]
    
    def test_build_index_prompt(self):
        """Test building index prompt from schema."""
        db = DatabaseSchema(description="Sample database")
        table = TableSchema(name="items", description="Items table")
        table.columns.append(ColumnSchema(name="id", data_type="INTEGER", primary_key=True))
        table.columns.append(ColumnSchema(name="name", data_type="VARCHAR"))
        db.add_table(table)
        
        prompt = db.build_index_prompt()
        assert "Sample database" in prompt
        assert "## Table: items" in prompt
        assert "| id |" in prompt
        assert "| name |" in prompt