import sqlite3
import os
from typing import Generator, Optional, Any

class SQLiteTransaction:
    """
    Context manager for managing SQLite connection, transaction lifecycle, 
    and ensuring proper schema constraint enforcement.
    """
    def __init__(self, db_path: str):
        self.db_path = os.path.abspath(db_path)
        self.conn: Optional[sqlite3.Connection] = None

    def __enter__(self) -> sqlite3.Cursor:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        # Enable Foreign Key support inside SQLite
        self.conn.execute("PRAGMA foreign_keys = ON;")
        return self.conn.cursor()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        if self.conn:
            if exc_type is not None:
                self.conn.rollback()
            else:
                self.conn.commit()
            self.conn.close()
        return False # Bubble exception if any occurred

def get_connection(db_path: str) -> sqlite3.Connection:
    """
    Creates and returns a sqlite3 Connection to the database at db_path.
    Creates parent directories if necessary.
    """
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_schema_version(db_path: str) -> None:
    """
    Ensures schema versioning tables are initialized to support migration tracking.
    """
    with SQLiteTransaction(db_path) as cursor:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now', 'utc'))
        )
        """)
        
        # Initialize to version 1 if empty
        cursor.execute("SELECT COUNT(*) FROM schema_version")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO schema_version (version) VALUES (1)")

def init_ir_cache_db(db_path: str) -> None:
    """
    Initializes the schema for the IR cache sqlite database.
    """
    init_schema_version(db_path)
    with SQLiteTransaction(db_path) as cursor:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ir_cache (
            file_path TEXT PRIMARY KEY,
            file_hash TEXT NOT NULL,
            parser_provider_version TEXT,
            grammar_version TEXT,
            query_pack_version TEXT,
            ir_json TEXT,
            updated_at TEXT DEFAULT (datetime('now', 'utc'))
        )
        """)

def init_provider_cache_db(db_path: str) -> None:
    """
    Initializes the schema for the provider cache / database.
    """
    init_schema_version(db_path)
    with SQLiteTransaction(db_path) as cursor:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS provider_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """)
