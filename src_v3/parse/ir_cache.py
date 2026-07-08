import sqlite3
import hashlib
import json
import datetime
from typing import Dict, Any, List, Tuple, Optional
from src_v3.core.models import IRNode, IREdge

def compute_file_hash(file_path: str) -> str:
    """
    Computes the SHA256 hash of a file's content.
    """
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()

def load_ir_if_fresh(
    file_path: str, 
    cache_key: Dict[str, str], 
    conn: sqlite3.Connection
) -> Optional[Tuple[List[IRNode], List[IREdge]]]:
    """
    Loads cached IR nodes and edges if the cache key (file hash and parser details) is fresh.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT file_hash, parser_provider_version, grammar_version, query_pack_version, ir_json
        FROM ir_cache WHERE file_path = ?
        """,
        (file_path,)
    )
    row = cursor.fetchone()
    if not row:
        return None
        
    # Check if cache is fresh
    if (
        row["file_hash"] == cache_key.get("file_hash") and
        row["parser_provider_version"] == cache_key.get("parser_provider_version") and
        row["grammar_version"] == cache_key.get("grammar_version") and
        row["query_pack_version"] == cache_key.get("query_pack_version")
    ):
        try:
            ir_data = json.loads(row["ir_json"])
            nodes = [IRNode.from_dict(n) for n in ir_data.get("nodes", [])]
            edges = [IREdge.from_dict(e) for e in ir_data.get("edges", [])]
            return nodes, edges
        except Exception:
            return None
            
    return None

def save_ir(
    file_path: str,
    cache_key: Dict[str, str],
    nodes: List[IRNode],
    edges: List[IREdge],
    conn: sqlite3.Connection
) -> None:
    """
    Saves the IR nodes and edges of a file to the SQLite cache database.
    """
    ir_data = {
        "nodes": [n.to_dict() for n in nodes],
        "edges": [e.to_dict() for e in edges]
    }
    ir_json = json.dumps(ir_data, ensure_ascii=False)
    updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO ir_cache 
        (file_path, file_hash, parser_provider_version, grammar_version, query_pack_version, ir_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            file_path,
            cache_key.get("file_hash", ""),
            cache_key.get("parser_provider_version", ""),
            cache_key.get("grammar_version", ""),
            cache_key.get("query_pack_version", ""),
            ir_json,
            updated_at
        )
    )
    conn.commit()
