import sqlite3
import os
from typing import Generator

def get_connection(db_path: str) -> sqlite3.Connection:
    """
    Creates and returns a sqlite3 Connection to the database at db_path.
    Creates parent directories if necessary.
    """
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_ir_cache_db(db_path: str) -> None:
    """
    Initializes the schema for the IR cache sqlite database.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    # Table for caching parsed file IRs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ir_cache (
        file_path TEXT PRIMARY KEY,
        file_hash TEXT,
        parser_provider_version TEXT,
        grammar_version TEXT,
        query_pack_version TEXT,
        ir_json TEXT,
        updated_at TEXT
    )
    """)
    
    conn.commit()
    conn.close()

def init_provider_cache_db(db_path: str) -> None:
    """
    Initializes the schema for the provider cache / database.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS provider_metadata (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    
    conn.commit()
    conn.close()
