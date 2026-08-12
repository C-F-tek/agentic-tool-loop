"""Tests for the data connectors module."""

from __future__ import annotations

import csv
import tempfile
import pytest
from pathlib import Path

from ..data.connectors import DatabaseConnector


class TestDatabaseConnector:
    """Test suite for DatabaseConnector."""
    
    @pytest.fixture
    def temp_csv(self):
        """Create a temporary CSV file for testing."""
        with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "value"])
            writer.writerow(["test", "42"])
            yield f.name
            Path(f.name).unlink(missing_ok=True)
    
    def test_sqlite_connect(self):
        """Test SQLite connection."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            connector = DatabaseConnector(db_type="sqlite", db_path=f.name)
            conn = connector.connect()
            assert conn is not None
            conn.close()
    
    def test_csv_read(self, temp_csv):
        """Test CSV reading."""
        connector = DatabaseConnector(db_type="csv", db_path=temp_csv)
        results = connector._connect_csv()
        assert len(results) == 1
        assert results[0]["name"] == "test"
        assert results[0]["value"] == "42"
    
    def test_get_sqlite_schema(self):
        """Test SQLite schema retrieval."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            connector = DatabaseConnector(db_type="sqlite", db_path=f.name)
            conn = connector.connect()
            try:
                schema = connector._get_sqlite_schema(conn)
                assert isinstance(schema, dict)
            finally:
                conn.close()