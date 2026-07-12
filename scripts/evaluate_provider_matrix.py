#!/usr/bin/env python3
import argparse
import json
import os
import socketserver
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src_v3.core.models import FileNode, IREdge, SymbolNode
from src_v3.providers.semantic.codegraph_provider import CodeGraphProvider
from src_v3.providers.semantic.lsif_provider import LSIFProvider
from src_v3.providers.semantic.lsp_provider import LSPProvider
from src_v3.storage.ir_store import IRStore


def _write_lsp_message(sock, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    sock.sendall(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)


def _read_lsp_message(sock) -> Dict[str, Any]:
    header = b""
    while b"\r\n\r\n" not in header:
        chunk = sock.recv(1)
        if not chunk:
            raise RuntimeError("connection closed")
        header += chunk
    content_length = 0
    for line in header.decode("ascii", errors="ignore").split("\r\n"):
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":", 1)[1].strip())
            break
    body = b""
    while len(body) < content_length:
        body += sock.recv(content_length - len(body))
    return json.loads(body.decode("utf-8"))


class FakeLSPHandler(socketserver.BaseRequestHandler):
    repo_dir = ""

    def handle(self):
        while True:
            try:
                request = _read_lsp_message(self.request)
            except Exception:
                return
            method = request.get("method")
            request_id = request.get("id")
            if request_id is None:
                continue
            app_uri = f"file://{os.path.join(self.repo_dir, 'app.py')}"
            if method == "initialize":
                result = {"capabilities": {"definitionProvider": True, "referencesProvider": True}}
            elif method == "textDocument/definition":
                result = {"uri": app_uri, "range": {"start": {"line": 0}, "end": {"line": 0}}}
            elif method == "textDocument/references":
                result = [
                    {"uri": app_uri, "range": {"start": {"line": 0}, "end": {"line": 0}}},
                    {"uri": app_uri, "range": {"start": {"line": 3}, "end": {"line": 3}}},
                ]
            else:
                result = None
            _write_lsp_message(self.request, {"jsonrpc": "2.0", "id": request_id, "result": result})


class FakeCodeGraphHandler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return

    def do_GET(self):
        if self.path == "/":
            self._send({"ok": True})
            return
        if self.path.startswith("/definitions"):
            self._send({"results": [{"symbol": "target", "file": "app.py", "span": {"start": 1, "end": 1}, "kind": "definition"}]})
            return
        if self.path.startswith("/references"):
            self._send({"results": [{"symbol": "target", "file": "app.py", "span": {"start": 4, "end": 4}, "kind": "reference"}]})
            return
        if self.path.startswith("/callers"):
            self._send({"results": [{"symbol": "caller", "file": "app.py", "span": {"start": 3, "end": 4}, "kind": "function"}]})
            return
        if self.path.startswith("/callees"):
            self._send({"results": [{"symbol": "target", "file": "app.py", "span": {"start": 1, "end": 1}, "kind": "function"}]})
            return
        self.send_response(404)
        self.end_headers()

    def _send(self, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_fixture() -> Tuple[tempfile.TemporaryDirectory, str, str, str, IRStore]:
    tmp = tempfile.TemporaryDirectory()
    repo_dir = os.path.join(tmp.name, "repo")
    workspace_dir = os.path.join(tmp.name, "workspace")
    os.makedirs(repo_dir, exist_ok=True)
    with open(os.path.join(repo_dir, "app.py"), "w", encoding="utf-8") as f:
        f.write("def target():\n    return 1\n\ndef caller():\n    return target()\n")

    store = IRStore(workspace_dir)
    target = SymbolNode("sym_app.py_target_1_2", "symbol", "python", "app.py", "target", {"start": 1, "end": 2}, {"symbol_kind": "function"})
    caller = SymbolNode("sym_app.py_caller_3_4", "symbol", "python", "app.py", "caller", {"start": 3, "end": 5}, {"symbol_kind": "function"})
    store.save([
        FileNode("file_app.py", "file", "python", "app.py"),
        target,
        caller,
    ], [
        IREdge("call_caller_target", "call", caller.node_id, target.node_id, provider_trace=["fixture"])
    ])

    lsif_path = os.path.join(tmp.name, "fixture.lsif")
    abs_app = os.path.join(repo_dir, "app.py")
    lsif_records = [
        {"id": 1, "type": "vertex", "label": "document", "uri": f"file://{abs_app}"},
        {"id": 2, "type": "vertex", "label": "range", "start": {"line": 0, "character": 4}, "end": {"line": 0, "character": 10}},
        {"id": 3, "type": "vertex", "label": "range", "start": {"line": 4, "character": 11}, "end": {"line": 4, "character": 17}},
        {"id": 4, "type": "vertex", "label": "resultSet"},
        {"id": 5, "type": "vertex", "label": "definitionResult"},
        {"id": 6, "type": "vertex", "label": "referenceResult"},
        {"id": 7, "type": "edge", "label": "contains", "outV": 1, "inVs": [2, 3]},
        {"id": 8, "type": "edge", "label": "next", "outV": 3, "inVs": [4]},
        {"id": 9, "type": "edge", "label": "textDocument/definition", "outV": 4, "inVs": [5]},
        {"id": 10, "type": "edge", "label": "textDocument/references", "outV": 4, "inVs": [6]},
        {"id": 11, "type": "edge", "label": "item", "outV": 5, "inVs": [2], "document": 1},
        {"id": 12, "type": "edge", "label": "item", "outV": 6, "inVs": [3], "document": 1},
    ]
    with open(lsif_path, "w", encoding="utf-8") as f:
        for record in lsif_records:
            f.write(json.dumps(record) + "\n")

    return tmp, repo_dir, workspace_dir, lsif_path, store


def run_matrix() -> Dict[str, Any]:
    tmp, repo_dir, _workspace_dir, lsif_path, store = create_fixture()
    try:
        codegraph = ThreadingHTTPServer(("127.0.0.1", 0), FakeCodeGraphHandler)
        cg_thread = threading.Thread(target=codegraph.serve_forever, daemon=True)
        cg_thread.start()

        FakeLSPHandler.repo_dir = repo_dir
        lsp = socketserver.ThreadingTCPServer(("127.0.0.1", 0), FakeLSPHandler)
        lsp_thread = threading.Thread(target=lsp.serve_forever, daemon=True)
        lsp_thread.start()

        symbol_ref = {"symbol": "target", "file": "app.py", "span": {"start": 5, "end": 5}}
        providers = [
            ("lsif", LSIFProvider(lsif_path, repo_dir, store)),
            ("codegraph", CodeGraphProvider(f"http://127.0.0.1:{codegraph.server_port}", repo_dir, store)),
            ("lsp", LSPProvider(f"127.0.0.1:{lsp.server_address[1]}", repo_dir, store)),
        ]
        rows: List[Dict[str, Any]] = []
        for provider_id, provider in providers:
            definitions = provider.find_definitions(symbol_ref)
            references = provider.find_references(symbol_ref)
            callers = provider.find_callers(symbol_ref)
            callees = provider.find_callees({"symbol": "caller", "file": "app.py", "span": {"start": 3, "end": 5}})
            rows.append({
                "provider": provider_id,
                "provider_name": provider.provider_name,
                "fallback": bool(getattr(provider, "use_fallback", False)),
                "definitions": len(definitions),
                "references": len(references),
                "callers": len(callers),
                "callees": len(callees),
                "passed": bool(definitions and references and (provider_id != "codegraph" or callers and callees)),
            })
        passed = all(row["passed"] and not row["fallback"] for row in rows)
        return {"ok": passed, "matrix": rows}
    finally:
        for _provider_id, provider in locals().get("providers", []):
            close = getattr(provider, "_close", None)
            if close:
                close()
        for server_name in ["codegraph", "lsp"]:
            server = locals().get(server_name)
            if server:
                server.shutdown()
                server.server_close()
        tmp.cleanup()


def main():
    parser = argparse.ArgumentParser(description="Run local semantic provider compatibility matrix")
    parser.parse_args()
    result = run_matrix()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
