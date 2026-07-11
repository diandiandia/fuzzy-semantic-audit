import os
import re
import urllib.request
from typing import List, Dict, Any, Optional
from src_v3.providers.semantic.base import SemanticProvider
from src_v3.core.enums import CapabilityLevel
from src_v3.storage.ir_store import IRStore

class CodeGraphProvider(SemanticProvider):
    provider_name: str = "CodeGraphProvider"

    def __init__(self, endpoint: str = "", repo_path: str = "", ir_store: Optional[IRStore] = None):
        self.endpoint = endpoint
        self.repo_path = os.path.abspath(repo_path) if repo_path else ""
        self.ir_store = ir_store
        self.use_fallback = not bool(endpoint)
        
        # Test endpoint connectivity if provided
        if endpoint:
            try:
                req = urllib.request.Request(endpoint, method="GET")
                with urllib.request.urlopen(req, timeout=0.5) as response:
                    self.use_fallback = False
            except Exception:
                self.use_fallback = True

    def capability_level(self) -> str:
        if self.use_fallback:
            return CapabilityLevel.L2.value
        return CapabilityLevel.L3.value

    def resolution_confidence(self) -> float:
        if self.use_fallback:
            return 0.0
        return 0.8

    def find_definitions(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        # In a real integration, we would perform an HTTP/GraphQL request to the CodeGraph endpoint.
        # Since this is a fallback capability contract, if active we can use IR symbols as definitions.
        if not self.ir_store:
            return []
        sym_name = symbol_ref.get("symbol")
        if not sym_name:
            return []
            
        defs = []
        for sn in self.ir_store.iter_symbol_nodes():
            if sn.symbol == sym_name:
                defs.append({
                    "symbol": sn.symbol,
                    "file": sn.file,
                    "span": sn.span,
                    "kind": sn.attributes.get("symbol_kind", "symbol")
                })
        return defs

    def find_references(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.ir_store or not self.repo_path:
            return []
        sym_name = symbol_ref.get("symbol")
        if not sym_name:
            return []
            
        refs = []
        for fn in self.ir_store.iter_file_nodes():
            abs_path = os.path.join(self.repo_path, fn.file)
            if not os.path.exists(abs_path):
                continue
                
            try:
                with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    
                for idx, line in enumerate(lines):
                    if re.search(r'\b' + re.escape(sym_name) + r'\b', line):
                        line_num = idx + 1
                        if fn.file == symbol_ref.get("file"):
                            ref_span = symbol_ref.get("span", {})
                            if ref_span.get("start") <= line_num <= ref_span.get("end"):
                                continue
                                
                        refs.append({
                            "symbol": sym_name,
                            "file": fn.file,
                            "span": {"start": line_num, "end": line_num},
                            "kind": "reference"
                        })
            except Exception:
                pass
        return refs

    def find_callers(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.ir_store:
            return []
        sym_name = symbol_ref.get("symbol")
        if not sym_name:
            return []
            
        callers = []
        visited = set()
        
        # Mode 1: Query call edges in the IR database
        edges = self.ir_store.get_edges()
        call_edges = [e for e in edges if e.kind == "call"]
        if call_edges:
            for edge in call_edges:
                dst_node = self.ir_store.get_node_by_id(edge.dst_node_id)
                if dst_node and dst_node.symbol == sym_name:
                    caller_node = self.ir_store.get_node_by_id(edge.src_node_id)
                    if caller_node:
                        caller_key = f"{caller_node.file}:{caller_node.symbol}:{caller_node.span['start']}"
                        if caller_key not in visited:
                            visited.add(caller_key)
                            callers.append({
                                "symbol": caller_node.symbol,
                                "file": caller_node.file,
                                "span": caller_node.span
                            })
                            
        # Mode 2: Text/reference search fallback (Ctags equivalent)
        if not callers and self.repo_path:
            refs = self.find_references(symbol_ref)
            for ref in refs:
                file_symbols = self.ir_store.get_symbols_by_file(ref["file"])
                ref_line = ref["span"]["start"]
                enclosing = None
                for fs in file_symbols:
                    if fs.attributes.get("symbol_kind") == "function":
                        if fs.span["start"] <= ref_line <= fs.span["end"]:
                            if not enclosing or (fs.span["end"] - fs.span["start"] < enclosing.span["end"] - enclosing.span["start"]):
                                enclosing = fs
                if enclosing:
                    caller_key = f"{enclosing.file}:{enclosing.symbol}:{enclosing.span['start']}"
                    if caller_key not in visited:
                        visited.add(caller_key)
                        callers.append({
                            "symbol": enclosing.symbol,
                            "file": enclosing.file,
                            "span": enclosing.span,
                            "kind": "function"
                        })
        return callers

    def find_callees(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.ir_store:
            return []
        sym_name = symbol_ref.get("symbol")
        if not sym_name:
            return []
            
        callees = []
        visited = set()
        
        # Mode 1: Query call edges in the IR database
        edges = self.ir_store.get_edges()
        call_edges = [e for e in edges if e.kind == "call"]
        if call_edges:
            for edge in call_edges:
                src_node = self.ir_store.get_node_by_id(edge.src_node_id)
                if src_node and src_node.symbol == sym_name:
                    callee_node = self.ir_store.get_node_by_id(edge.dst_node_id)
                    if callee_node:
                        callee_key = f"{callee_node.file}:{callee_node.symbol}:{callee_node.span['start']}"
                        if callee_key not in visited:
                            visited.add(callee_key)
                            callees.append({
                                "symbol": callee_node.symbol,
                                "file": callee_node.file,
                                "span": callee_node.span
                            })
                            
        # Mode 2: Function body keyword scan fallback (Ctags equivalent)
        if not callees and self.repo_path:
            file_path = symbol_ref.get("file")
            span = symbol_ref.get("span", {})
            if file_path and span:
                abs_path = os.path.join(self.repo_path, file_path)
                if os.path.exists(abs_path):
                    try:
                        with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                            lines = f.readlines()
                        start = span["start"] - 1
                        end = span["end"]
                        func_text = "".join(lines[start:end])
                        words = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', func_text))
                        for sn in self.ir_store.iter_symbol_nodes():
                            if sn.symbol in words and sn.symbol != sym_name:
                                callee_key = f"{sn.file}:{sn.symbol}:{sn.span['start']}"
                                if callee_key not in visited:
                                    visited.add(callee_key)
                                    callees.append({
                                        "symbol": sn.symbol,
                                        "file": sn.file,
                                        "span": sn.span,
                                        "kind": sn.attributes.get("symbol_kind", "symbol")
                                    })
                    except Exception:
                        pass
        return callees
