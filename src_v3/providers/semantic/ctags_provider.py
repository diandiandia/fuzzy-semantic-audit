import os
import re
from typing import List, Dict, Any, Optional
from src_v3.providers.semantic.base import SemanticProvider
from src_v3.core.enums import CapabilityLevel
from src_v3.storage.ir_store import IRStore

class CtagsProvider(SemanticProvider):
    provider_name: str = "CtagsProvider"

    def __init__(self, repo_path: str, ir_store: IRStore):
        self.repo_path = os.path.abspath(repo_path)
        self.ir_store = ir_store
        self._file_cache = {}
        self._file_words = {}

    def capability_level(self) -> str:
        # Ctags-style name and text matching is structural assistance, not semantic
        # reference resolution.  Callers must report it as an explicit fallback.
        return CapabilityLevel.L1.value

    def resolution_confidence(self) -> float:
        return 0.5 # Moderate confidence (heuristic based)

    def _get_file_lines(self, rel_path: str) -> List[str]:
        if rel_path not in self._file_cache:
            abs_path = os.path.join(self.repo_path, rel_path)
            if not os.path.exists(abs_path):
                self._file_cache[rel_path] = []
            else:
                try:
                    with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                        self._file_cache[rel_path] = f.readlines()
                except Exception:
                    self._file_cache[rel_path] = []
        return self._file_cache[rel_path]

    def _get_file_words(self, rel_path: str) -> set:
        if rel_path not in self._file_words:
            lines = self._get_file_lines(rel_path)
            text = "".join(lines)
            self._file_words[rel_path] = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', text))
        return self._file_words[rel_path]

    def find_definitions(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Finds definitions by searching symbol nodes in the IRStore.
        """
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
        """
        Finds references by text-searching the symbol name in the codebase.
        """
        sym_name = symbol_ref.get("symbol")
        if not sym_name or len(sym_name) < 4:
            return []

        blacklist = {
            "name", "type", "data", "file", "class", "result", "error", "status", "info", "code",
            "message", "count", "total", "request", "response", "config", "params", "args", "list",
            "dict", "true", "false", "null", "none", "void", "main", "init", "start", "stop", "close",
            "open", "read", "write", "send", "recv", "connect", "query", "user", "admin", "token",
            "method", "route", "guard", "check", "state", "event", "task", "object", "system"
        }
        if sym_name.lower() in blacklist:
            return []

        refs = []
        # Walk and text-search files in the workspace
        for fn in self.ir_store.iter_file_nodes():
            words = self._get_file_words(fn.file)
            if sym_name not in words:
                continue

            lines = self._get_file_lines(fn.file)
            if not lines:
                continue

            for idx, line in enumerate(lines):
                # Check if symbol is referenced (using word boundaries to avoid partial matches)
                if re.search(r'\b' + re.escape(sym_name) + r'\b', line):
                    # Avoid matching its own definition
                    line_num = idx + 1
                    if fn.file == symbol_ref.get("file"):
                        ref_span = symbol_ref.get("span", {})
                        if ref_span.get("start") <= line_num <= ref_span.get("end"):
                            continue # This is the definition itself, skip

                    refs.append({
                        "symbol": sym_name,
                        "file": fn.file,
                        "span": {"start": line_num, "end": line_num},
                        "kind": "reference"
                    })
        return refs

    def find_callers(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Finds callers by locating which functions contain references to the symbol.
        """
        refs = self.find_references(symbol_ref)
        callers = []
        visited = set()
        
        for ref in refs:
            # Find enclosing function/symbol for this reference
            file_symbols = self.ir_store.get_symbols_by_file(ref["file"])
            ref_line = ref["span"]["start"]
            
            enclosing = None
            for fs in file_symbols:
                if fs.attributes.get("symbol_kind") == "function":
                    if fs.span["start"] <= ref_line <= fs.span["end"]:
                        # Take the most specific enclosing function (smallest span)
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
        """
        Finds callees by analyzing the content of the function body and looking up defined symbols.
        """
        file_path = symbol_ref.get("file")
        span = symbol_ref.get("span", {})
        if not file_path or not span:
            return []
            
        lines = self._get_file_lines(file_path)
        if not lines:
            return []
            
        callees = []
        try:
            start = span["start"] - 1
            end = span["end"]
            func_lines = lines[start:end]
            func_text = "".join(func_lines)
            
            # Find all words that could be symbol calls
            words = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', func_text))
            
            blacklist = {
                "name", "type", "data", "file", "class", "result", "error", "status", "info", "code",
                "message", "count", "total", "request", "response", "config", "params", "args", "list",
                "dict", "true", "false", "null", "none", "void", "main", "init", "start", "stop", "close",
                "open", "read", "write", "send", "recv", "connect", "query", "user", "admin", "token",
                "method", "route", "guard", "check", "state", "event", "task", "object", "system"
            }

            # Match these words against known symbols in the IRStore
            for sn in self.ir_store.iter_symbol_nodes():
                if len(sn.symbol) >= 4 and sn.symbol.lower() not in blacklist:
                    if sn.symbol in words and sn.symbol != symbol_ref.get("symbol"):
                        callees.append({
                            "symbol": sn.symbol,
                            "file": sn.file,
                            "span": sn.span,
                            "kind": sn.attributes.get("symbol_kind", "symbol")
                        })
        except Exception:
            pass
        return callees
