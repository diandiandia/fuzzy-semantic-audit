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
        # Split nodes into files and symbols/other code elements
        file_nodes = [n for n in nodes if n.kind == "file"]
        symbol_nodes = [n for n in nodes if n.kind != "file"]

        if overwrite:
            # If both lists are empty, perform a full clear/reset
            if not nodes and not edges:
                for path in [self.files_path, self.symbols_path, self.edges_path]:
                    with open(path, 'w', encoding='utf-8') as f:
                        pass
            else:
                # Only truncate files that are actually being rewritten
                if file_nodes:
                    with open(self.files_path, 'w', encoding='utf-8') as f:
                        pass
                if symbol_nodes:
                    with open(self.symbols_path, 'w', encoding='utf-8') as f:
                        pass
                if edges:
                    with open(self.edges_path, 'w', encoding='utf-8') as f:
                        pass
                    
        mode = 'w' if overwrite else 'a'
        
        # Write files
        if file_nodes:
            if overwrite:
                unique_files = []
                seen_fids = set()
                for fn in file_nodes:
                    if fn.node_id not in seen_fids:
                        seen_fids.add(fn.node_id)
                        unique_files.append(fn)
                with open(self.files_path, mode, encoding='utf-8') as f:
                    for fn in unique_files:
                        f.write(json.dumps(fn.to_dict(), ensure_ascii=False) + "\n")
            else:
                existing_fids = {f.node_id for f in self.get_file_nodes()}
                unique_files = []
                for fn in file_nodes:
                    if fn.node_id not in existing_fids:
                        existing_fids.add(fn.node_id)
                        unique_files.append(fn)
                if unique_files:
                    with open(self.files_path, mode, encoding='utf-8') as f:
                        for fn in unique_files:
                            f.write(json.dumps(fn.to_dict(), ensure_ascii=False) + "\n")
                    
        # Write symbols
        if symbol_nodes:
            if overwrite:
                unique_syms = []
                seen_sids = set()
                for sn in symbol_nodes:
                    if sn.node_id not in seen_sids:
                        seen_sids.add(sn.node_id)
                        unique_syms.append(sn)
                with open(self.symbols_path, mode, encoding='utf-8') as f:
                    for sn in unique_syms:
                        f.write(json.dumps(sn.to_dict(), ensure_ascii=False) + "\n")
            else:
                existing_sids = {s.node_id for s in self.get_symbol_nodes()}
                unique_syms = []
                for sn in symbol_nodes:
                    if sn.node_id not in existing_sids:
                        existing_sids.add(sn.node_id)
                        unique_syms.append(sn)
                if unique_syms:
                    with open(self.symbols_path, mode, encoding='utf-8') as f:
                        for sn in unique_syms:
                            f.write(json.dumps(sn.to_dict(), ensure_ascii=False) + "\n")
                    
        # Write edges
        if edges:
            if overwrite:
                unique_edges = []
                seen_edge_ids = set()
                for ed in edges:
                    if ed.edge_id not in seen_edge_ids:
                        seen_edge_ids.add(ed.edge_id)
                        unique_edges.append(ed)
                with open(self.edges_path, mode, encoding='utf-8') as f:
                    for ed in unique_edges:
                        f.write(json.dumps(ed.to_dict(), ensure_ascii=False) + "\n")
            else:
                existing_edge_ids = {e.edge_id for e in self.get_edges()}
                unique_edges = []
                for ed in edges:
                    if ed.edge_id not in existing_edge_ids:
                        existing_edge_ids.add(ed.edge_id)
                        unique_edges.append(ed)
                if unique_edges:
                    with open(self.edges_path, mode, encoding='utf-8') as f:
                        for ed in unique_edges:
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

    def get_nodes_by_kind(self, kind: str) -> List[IRNode]:
        """
        Queries all nodes matching the specified kind (e.g. 'file', 'symbol', 'entrypoint', 'guard_check', etc.).
        """
        if kind == "file":
            return self.get_file_nodes()
        results = []
        for sn in self.iter_symbol_nodes():
            if sn.kind == kind:
                results.append(sn)
        return results

    def get_symbols_by_name(self, symbol_name: str) -> List[IRNode]:
        """
        Queries all symbol nodes matching the specified symbol name.
        """
        results = []
        for sn in self.iter_symbol_nodes():
            if sn.symbol == symbol_name:
                results.append(sn)
        return results

    def get_edges_by_kind(self, kind: str) -> List[IREdge]:
        """
        Queries all edges matching the specified edge kind (e.g. 'contain', 'import', 'call').
        """
        results = []
        for ed in self.iter_edges():
            if ed.kind == kind:
                results.append(ed)
        return results

    def get_edges_by_source(self, src_node_id: str) -> List[IREdge]:
        """
        Queries all edges originating from the specified source node ID.
        """
        results = []
        for ed in self.iter_edges():
            if ed.src_node_id == src_node_id:
                results.append(ed)
        return results

    def get_edges_by_destination(self, dst_node_id: str) -> List[IREdge]:
        """
        Queries all edges pointing to the specified destination node ID.
        """
        results = []
        for ed in self.iter_edges():
            if ed.dst_node_id == dst_node_id:
                results.append(ed)
        return results
