import os
import json
from typing import List, Tuple, Dict, Any, Generator
from src_v3.core.models import IRNode, IREdge

class IRStore:
    """
    Handles persistence and query of IR Nodes and Edges under .audit_workspace_v3/ir/.
    Files are stored as JSONL: files.jsonl, symbols.jsonl, edges.jsonl.
    """
    def __init__(self, workspace_dir: str):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.ir_dir = os.path.join(self.workspace_dir, "ir")
        os.makedirs(self.ir_dir, exist_ok=True)
        
        self.files_path = os.path.join(self.ir_dir, "files.jsonl")
        self.symbols_path = os.path.join(self.ir_dir, "symbols.jsonl")
        self.edges_path = os.path.join(self.ir_dir, "edges.jsonl")

    def save(self, nodes: List[IRNode], edges: List[IREdge], overwrite: bool = True) -> None:
        """
        Saves nodes and edges to respective JSONL files.
        If overwrite is False, appends to the files.
        """
        if overwrite:
            # Truncate files to clear existing data
            for path in [self.files_path, self.symbols_path, self.edges_path]:
                with open(path, 'w', encoding='utf-8') as f:
                    pass
                    
        mode = 'w' if overwrite else 'a'
        
        # Split nodes into files and symbols
        file_nodes = [n for n in nodes if n.kind == "file"]
        symbol_nodes = [n for n in nodes if n.kind == "symbol"]
        
        # Write files
        if file_nodes:
            with open(self.files_path, mode, encoding='utf-8') as f:
                for fn in file_nodes:
                    f.write(json.dumps(fn.to_dict(), ensure_ascii=False) + "\n")
                    
        # Write symbols
        if symbol_nodes:
            with open(self.symbols_path, mode, encoding='utf-8') as f:
                for sn in symbol_nodes:
                    f.write(json.dumps(sn.to_dict(), ensure_ascii=False) + "\n")
                    
        # Write edges
        if edges:
            with open(self.edges_path, mode, encoding='utf-8') as f:
                for ed in edges:
                    f.write(json.dumps(ed.to_dict(), ensure_ascii=False) + "\n")

    def get_file_nodes(self) -> List[IRNode]:
        """
        Loads and returns all File nodes.
        """
        return list(self.iter_file_nodes())

    def iter_file_nodes(self) -> Generator[IRNode, None, None]:
        if not os.path.exists(self.files_path):
            return
        with open(self.files_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    yield IRNode.from_dict(json.loads(line.strip()))

    def get_symbol_nodes(self) -> List[IRNode]:
        """
        Loads and returns all Symbol nodes.
        """
        return list(self.iter_symbol_nodes())

    def iter_symbol_nodes(self) -> Generator[IRNode, None, None]:
        if not os.path.exists(self.symbols_path):
            return
        with open(self.symbols_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    yield IRNode.from_dict(json.loads(line.strip()))

    def get_edges(self) -> List[IREdge]:
        """
        Loads and returns all Edges.
        """
        return list(self.iter_edges())

    def iter_edges(self) -> Generator[IREdge, None, None]:
        if not os.path.exists(self.edges_path):
            return
        with open(self.edges_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    yield IREdge.from_dict(json.loads(line.strip()))

    def get_symbols_by_file(self, rel_file_path: str) -> List[IRNode]:
        """
        Queries all symbols belonging to a specific file.
        """
        results = []
        for sn in self.iter_symbol_nodes():
            if sn.file == rel_file_path:
                results.append(sn)
        return results

    def get_node_by_id(self, node_id: str) -> Optional[IRNode]:
        """
        Searches for any node by its ID.
        """
        for fn in self.iter_file_nodes():
            if fn.node_id == node_id:
                return fn
        for sn in self.iter_symbol_nodes():
            if sn.node_id == node_id:
                return sn
        return None
