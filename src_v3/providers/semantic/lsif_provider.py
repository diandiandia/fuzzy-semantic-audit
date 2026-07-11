import os
import re
import json
from typing import List, Dict, Any, Optional
from src_v3.providers.semantic.base import SemanticProvider
from src_v3.core.enums import CapabilityLevel
from src_v3.storage.ir_store import IRStore

class LSIFProvider(SemanticProvider):
    provider_name: str = "LSIFProvider"

    def __init__(self, lsif_path: str = "", repo_path: str = "", ir_store: Optional[IRStore] = None):
        self.lsif_path = lsif_path
        self.repo_path = os.path.abspath(repo_path) if repo_path else ""
        self.ir_store = ir_store
        self.use_fallback = not bool(lsif_path) or not os.path.exists(lsif_path)
        
        # Parsed LSIF index maps
        self.ranges: Dict[int, Dict[str, Any]] = {}
        self.documents: Dict[int, str] = {}
        self.definitions: Dict[int, List[Dict[str, Any]]] = {}
        self.references: Dict[int, List[Dict[str, Any]]] = {}
        
        if not self.use_fallback:
            try:
                self._parse_lsif()
                self.use_fallback = False
            except Exception:
                self.use_fallback = True

    def _parse_lsif(self):
        """
        Parses the LSIF JSONL file to construct symbol mapping.
        """
        id_to_label: Dict[int, str] = {}
        id_to_obj: Dict[int, Dict[str, Any]] = {}
        
        # Temp relations
        next_map: Dict[int, int] = {} # outV -> inV
        def_result_map: Dict[int, int] = {} # resultSet -> definitionResult
        ref_result_map: Dict[int, int] = {} # resultSet -> referenceResult
        item_map: Dict[int, List[Dict[str, Any]]] = {} # resultId -> list of range objects
        
        with open(self.lsif_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                obj_id = obj.get("id")
                obj_type = obj.get("type")
                label = obj.get("label")
                
                id_to_obj[obj_id] = obj
                id_to_label[obj_id] = label
                
                if obj_type == "vertex":
                    if label == "document":
                        uri = obj.get("uri", "")
                        # Relativize URI
                        if uri.startswith("file://"):
                            uri = uri[7:]
                        if self.repo_path and uri.startswith(self.repo_path):
                            uri = os.path.relpath(uri, self.repo_path)
                        self.documents[obj_id] = uri
                    elif label == "range":
                        self.ranges[obj_id] = obj
                elif obj_type == "edge":
                    out_v = obj.get("outV")
                    in_vs = obj.get("inVs", [])
                    in_v = obj.get("inV")
                    
                    if label == "contains":
                        if out_v in self.documents:
                            for inv in in_vs:
                                if inv in self.ranges:
                                    self.ranges[inv]["document"] = self.documents[out_v]
                    elif label == "next":
                        for inv in in_vs:
                            next_map[out_v] = inv
                    elif label == "textDocument/definition":
                        for inv in in_vs:
                            def_result_map[out_v] = inv
                    elif label == "textDocument/references":
                        for inv in in_vs:
                            ref_result_map[out_v] = inv
                    elif label == "item":
                        for inv in in_vs:
                            if out_v not in item_map:
                                item_map[out_v] = []
                            item_map[out_v].append({
                                "range_id": inv,
                                "document_id": obj.get("document")
                            })

        # Resolve definitions/references for each range
        for r_id, range_obj in self.ranges.items():
            result_set_id = next_map.get(r_id)
            if not result_set_id:
                continue
                
            # Definitions
            def_res_id = def_result_map.get(result_set_id)
            if def_res_id and def_res_id in item_map:
                self.definitions[r_id] = []
                for item in item_map[def_res_id]:
                    target_range = self.ranges.get(item["range_id"])
                    if target_range:
                        self.definitions[r_id].append({
                            "file": target_range.get("document", ""),
                            "span": {
                                "start": target_range["start"]["line"] + 1,
                                "end": target_range["end"]["line"] + 1
                            }
                        })
            
            # References
            ref_res_id = ref_result_map.get(result_set_id)
            if ref_res_id and ref_res_id in item_map:
                self.references[r_id] = []
                for item in item_map[ref_res_id]:
                    target_range = self.ranges.get(item["range_id"])
                    if target_range:
                        self.references[r_id].append({
                            "file": target_range.get("document", ""),
                            "span": {
                                "start": target_range["start"]["line"] + 1,
                                "end": target_range["end"]["line"] + 1
                            }
                        })

    def capability_level(self) -> str:
        if self.use_fallback:
            return CapabilityLevel.L1.value
        return CapabilityLevel.L2.value

    def resolution_confidence(self) -> float:
        if self.use_fallback:
            return 0.0
        return 0.8

    def _find_matching_range_id(self, symbol_ref: Dict[str, Any]) -> Optional[int]:
        """
        Finds the LSIF range ID matching the symbol name, file, and span.
        """
        sym_name = symbol_ref.get("symbol")
        file_path = symbol_ref.get("file")
        span = symbol_ref.get("span", {})
        
        if not sym_name or not file_path:
            return None
            
        for r_id, r_obj in self.ranges.items():
            if r_obj.get("document") == file_path:
                # Approximate span overlap or text match
                r_line = r_obj["start"]["line"] + 1
                if span.get("start") <= r_line <= span.get("end"):
                    return r_id
        return None

    def find_definitions(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.use_fallback:
            r_id = self._find_matching_range_id(symbol_ref)
            if r_id and r_id in self.definitions:
                return [
                    {
                        "symbol": symbol_ref.get("symbol"),
                        "file": d["file"],
                        "span": d["span"],
                        "kind": "definition"
                    }
                    for d in self.definitions[r_id]
                ]
            return []
            
        # Fallback Mode
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
        if not self.use_fallback:
            r_id = self._find_matching_range_id(symbol_ref)
            if r_id and r_id in self.references:
                return [
                    {
                        "symbol": symbol_ref.get("symbol"),
                        "file": r["file"],
                        "span": r["span"],
                        "kind": "reference"
                    }
                    for r in self.references[r_id]
                ]
            return []

        # Fallback Mode
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
        # If we have LSIF parsed data, find callers by looking up LSIF references and locating enclosing function in IR
        if not self.use_fallback:
            refs = self.find_references(symbol_ref)
            if refs and self.ir_store:
                callers = []
                visited = set()
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
                if callers:
                    return callers

        # Fallback Mode
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
        # If we have LSIF data, find callees by scanning within range and looking up definitions
        if not self.use_fallback and self.ir_store:
            r_id = self._find_matching_range_id(symbol_ref)
            if r_id and r_id in self.ranges:
                func_range = self.ranges[r_id]
                func_file = func_range.get("document")
                func_start = func_range["start"]["line"] + 1
                func_end = func_range["end"]["line"] + 1
                
                callees = []
                visited = set()
                # Find all sub-ranges in the same file that are within the function body
                for sub_id, sub_range in self.ranges.items():
                    if sub_id != r_id and sub_range.get("document") == func_file:
                        sub_line = sub_range["start"]["line"] + 1
                        if func_start <= sub_line <= func_end:
                            # Check if this sub-range has a definition
                            if sub_id in self.definitions:
                                for df in self.definitions[sub_id]:
                                    # Find matching symbol node
                                    for sn in self.ir_store.iter_symbol_nodes():
                                        if sn.file == df["file"] and sn.span["start"] <= df["span"]["start"] <= sn.span["end"]:
                                            callee_key = f"{sn.file}:{sn.symbol}:{sn.span['start']}"
                                            if callee_key not in visited:
                                                visited.add(callee_key)
                                                callees.append({
                                                    "symbol": sn.symbol,
                                                    "file": sn.file,
                                                    "span": sn.span,
                                                    "kind": sn.attributes.get("symbol_kind", "symbol")
                                                })
                if callees:
                    return callees

        # Fallback Mode
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
