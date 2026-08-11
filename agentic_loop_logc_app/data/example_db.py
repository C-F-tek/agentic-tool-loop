"""
Example SQLite database creator for testing the Data RAG Agent.

Creates a sample database with users, orders, and products tables
for testing the agent's query capabilities.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def create_example_db(db_path: str = "state/example.db") -> str:
    """Create an example SQLite database for testing."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(path))
    try:
        # Create tables
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                category TEXT DEFAULT 'general'
            );
            
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                product_id INTEGER REFERENCES products(id),
                quantity INTEGER DEFAULT 1,
                order_date TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Insert sample data
            INSERT INTO users (name, email) VALUES ('Alice', 'alice@example.com');
            INSERT INTO users (name, email) VALUES ('Bob', 'bob@example.com');
            INSERT INTO users (name, email) VALUES ('Charlie', 'charlie@example.com');
            
            INSERT INTO products (name, price, category) VALUES ('Laptop', 999.99, 'electronics');
            INSERT INTO products (name, price, category) VALUES ('Book', 19.99, 'education');
            INSERT INTO products (name, price, category) VALUES ('Headphones', 49.99, 'electronics');
            
            INSERT INTO orders (user_id, product_id, quantity) VALUES (1, 1, 1);
            INSERT INTO orders (user_id, product_id, quantity) VALUES (2, 3, 2);
            INSERT INTO orders (user_id, product_id, quantity) VALUES (3, 2, 1);
        """)
        
        conn.commit()
        return str(path)
    except Exception as e:
        conn.close()
        raise e


if __name__ == "__main__":
    path = create_example_db()
    print(f"Example database created at: {path}")