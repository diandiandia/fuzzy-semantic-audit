import os
import re
import socket
import json
from typing import List, Dict, Any, Optional
from src_v3.providers.semantic.base import SemanticProvider
from src_v3.core.enums import CapabilityLevel
from src_v3.storage.ir_store import IRStore

class LSPProvider(SemanticProvider):
    provider_name: str = "LSPProvider"

    def __init__(self, lsp_server_addr: str = "", repo_path: str = "", ir_store: Optional[IRStore] = None):
        self.lsp_server_addr = lsp_server_addr
        self.repo_path = os.path.abspath(repo_path) if repo_path else ""
        self.ir_store = ir_store
        self.use_fallback = not bool(lsp_server_addr)
        self.fallback_reason = "LSP server is not configured" if self.use_fallback else ""
        self._socket: Optional[socket.socket] = None
        self._request_id = 0
        self._initialized = False
        self._opened_documents = set()
        
        # Test connection if address is provided
        if lsp_server_addr:
            try:
                # Expect host:port or similar
                if ":" in lsp_server_addr:
                    host, port = lsp_server_addr.split(":")
                    self._socket = socket.create_connection((host, int(port)), timeout=2.0)
                    self._socket.settimeout(2.0)
                    self._initialize()
                    self.use_fallback = False
                else:
                    self.use_fallback = True
            except Exception:
                self.use_fallback = True
                self.fallback_reason = "LSP server is unreachable"

    def capability_level(self) -> str:
        if self.use_fallback:
            return CapabilityLevel.L1.value
        return CapabilityLevel.L2.value

    def resolution_confidence(self) -> float:
        if self.use_fallback:
            return 0.0
        return 0.9

    def _send_lsp_rpc(self, method: str, params: Dict[str, Any]) -> Any:
        try:
            if not self._initialized:
                self._initialize()
            return self._request(method, params)
        except Exception as exc:
            # A TCP listener alone is not an LSP implementation. Once an RPC
            # fails, all later results must be treated as explicit fallback.
            self.use_fallback = True
            self.fallback_reason = f"LSP RPC '{method}' failed: {exc}"
            self._close()
            return None

    def _initialize(self) -> None:
        if not self._socket:
            raise RuntimeError("LSP socket is unavailable")
        root_uri = f"file://{self.repo_path}" if self.repo_path else None
        result = self._request("initialize", {
            "processId": os.getpid(),
            "rootUri": root_uri,
            "capabilities": {}
        })
        if result is None:
            raise RuntimeError("LSP initialize returned no result")
        self._notify("initialized", {})
        self._initialized = True

    def _request(self, method: str, params: Dict[str, Any]) -> Any:
        self._request_id += 1
        self._send({
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params
        })
        while True:
            response = self._read_message()
            if response.get("id") != self._request_id:
                continue
            if "error" in response:
                raise RuntimeError(str(response["error"]))
            return response.get("result")

    def _notify(self, method: str, params: Dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _send(self, message: Dict[str, Any]) -> None:
        if not self._socket:
            raise RuntimeError("LSP socket is unavailable")
        body = json.dumps(message).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self._socket.sendall(header + body)

    def _read_message(self) -> Dict[str, Any]:
        if not self._socket:
            raise RuntimeError("LSP socket is unavailable")
        header = b""
        while b"\r\n\r\n" not in header:
            chunk = self._socket.recv(1)
            if not chunk:
                raise RuntimeError("LSP server closed the connection")
            header += chunk
        content_length = 0
        for line in header.decode("ascii", errors="ignore").split("\r\n"):
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":", 1)[1].strip())
                break
        if content_length <= 0:
            raise RuntimeError("LSP response lacks Content-Length")
        body = b""
        while len(body) < content_length:
            chunk = self._socket.recv(content_length - len(body))
            if not chunk:
                raise RuntimeError("LSP response body is incomplete")
            body += chunk
        return json.loads(body.decode("utf-8"))

    def _ensure_document_open(self, file_path: str) -> None:
        if file_path in self._opened_documents or not self.repo_path:
            return
        abs_path = os.path.join(self.repo_path, file_path)
        with open(abs_path, "r", encoding="utf-8", errors="ignore") as source:
            text = source.read()
        self._notify("textDocument/didOpen", {
            "textDocument": {
                "uri": f"file://{abs_path}",
                "languageId": os.path.splitext(file_path)[1].lstrip("."),
                "version": 1,
                "text": text
            }
        })
        self._opened_documents.add(file_path)

    def _close(self) -> None:
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
        self._socket = None
        self._initialized = False

    def _to_repo_relative(self, uri: str) -> str:
        if uri.startswith("file://"):
            uri = uri[7:]
        if self.repo_path and uri.startswith(self.repo_path):
            return os.path.relpath(uri, self.repo_path)
        return uri

    def _position_for_symbol(self, symbol_ref: Dict[str, Any]) -> Dict[str, int]:
        line = max(0, symbol_ref.get("span", {}).get("start", 1) - 1)
        character = 0
        file_path = symbol_ref.get("file", "")
        symbol = symbol_ref.get("symbol", "")
        if self.repo_path and file_path and symbol:
            try:
                with open(os.path.join(self.repo_path, file_path), "r", encoding="utf-8", errors="ignore") as source:
                    lines = source.readlines()
                if line < len(lines):
                    character = max(0, lines[line].find(symbol))
            except OSError:
                pass
        return {"line": line, "character": character}

    def find_definitions(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.use_fallback:
            self._ensure_document_open(symbol_ref.get("file", ""))
            file_uri = f"file://{os.path.join(self.repo_path, symbol_ref.get('file', ''))}"
            params = {
                "textDocument": {"uri": file_uri},
                "position": self._position_for_symbol(symbol_ref)
            }
            res = self._send_lsp_rpc("textDocument/definition", params)
            if res:
                # LSP can return Location, Location[] or LocationLink[]
                locations = res if isinstance(res, list) else [res]
                defs = []
                for loc in locations:
                    uri = loc.get("uri") or loc.get("targetUri")
                    rng = loc.get("range") or loc.get("targetSelectionRange")
                    if uri and rng:
                        rel_file = self._to_repo_relative(uri)
                        defs.append({
                            "symbol": symbol_ref.get("symbol"),
                            "file": rel_file,
                            "span": {
                                "start": rng["start"]["line"] + 1,
                                "end": rng["end"]["line"] + 1
                            },
                            "kind": "definition"
                        })
                if defs:
                    return defs

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
            self._ensure_document_open(symbol_ref.get("file", ""))
            file_uri = f"file://{os.path.join(self.repo_path, symbol_ref.get('file', ''))}"
            params = {
                "textDocument": {"uri": file_uri},
                "position": self._position_for_symbol(symbol_ref),
                "context": {"includeDeclaration": True}
            }
            res = self._send_lsp_rpc("textDocument/references", params)
            if res and isinstance(res, list):
                refs = []
                for loc in res:
                    uri = loc.get("uri")
                    rng = loc.get("range")
                    if uri and rng:
                        rel_file = self._to_repo_relative(uri)
                        refs.append({
                            "symbol": symbol_ref.get("symbol"),
                            "file": rel_file,
                            "span": {
                                "start": rng["start"]["line"] + 1,
                                "end": rng["end"]["line"] + 1
                            },
                            "kind": "reference"
                        })
                if refs:
                    return refs

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
        # If we have live LSP, we can trace callers by resolving references first,
        # then mapping references to enclosing functions. Since the reference locations
        # are semantically returned by LSP, the caller resolution is semantically accurate!
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
        # If we have live LSP, we can get callees of a function symbol
        # by querying prepareCallHierarchy / callHierarchy/outgoingCalls or text-scanning the function body
        # and checking if each identifier has a semantic definition.
        if not self.use_fallback and self.repo_path and self.ir_store:
            file_path = symbol_ref.get("file")
            span = symbol_ref.get("span", {})
            sym_name = symbol_ref.get("symbol")
            if file_path and span:
                abs_path = os.path.join(self.repo_path, file_path)
                if os.path.exists(abs_path):
                    try:
                        with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                            lines = f.readlines()
                        start = max(0, span["start"] - 1)
                        end = min(len(lines), span["end"])
                        func_text = "".join(lines[start:end])
                        words = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', func_text))
                        
                        callees = []
                        visited = set()
                        for word in words:
                            if word == sym_name:
                                continue
                            # Check if the word is defined in the project by querying definition
                            defs = self.find_definitions({"symbol": word, "file": file_path, "span": span})
                            if defs:
                                for df in defs:
                                    callee_key = f"{df['file']}:{df['symbol']}:{df['span']['start']}"
                                    if callee_key not in visited:
                                        visited.add(callee_key)
                                        callees.append({
                                            "symbol": df["symbol"],
                                            "file": df["file"],
                                            "span": df["span"],
                                            "kind": df.get("kind", "symbol")
                                        })
                        if callees:
                            return callees
                    except Exception:
                        pass

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
