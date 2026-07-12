import unittest
import os
import json
import tempfile
import shutil
from unittest.mock import patch
from src_v3.core.models import RepoProfile, LanguageShard
from src_v3.core.provider_registry import resolve_parser, resolve_semantic, resolve_embedding, resolve_frameworks
from src_v3.providers.parser.treesitter_native import TreeSitterNativeProvider
from src_v3.providers.parser.treesitter_wasm import TreeSitterWASMProvider
from src_v3.providers.semantic.null_provider import NullProvider
from src_v3.providers.semantic.lsp_provider import LSPProvider
from src_v3.providers.semantic.lsif_provider import LSIFProvider
from src_v3.providers.semantic.codegraph_provider import CodeGraphProvider
from src_v3.providers.semantic.ctags_provider import CtagsProvider
from src_v3.providers.embedding.keyword_provider import KeywordFallbackProvider
from src_v3.providers.embedding.openai_provider import OpenAIProvider
from src_v3.providers.embedding.gemini_provider import GeminiProvider
from src_v3.providers.embedding.cohere_provider import CohereProvider
from src_v3.providers.embedding.fastembed_provider import FastEmbedProvider
from src_v3.packs.semantic import load_semantic_pack
from src_v3.packs.frameworks import load_framework_pack
from src_v3.packs.tracks import load_track_pack

class TestProviders(unittest.TestCase):
    def test_resolve_parser(self):
        parser = resolve_parser("python", {})
        self.assertEqual(parser.provider_name, "TreeSitterNativeProvider")

    def test_resolve_semantic_fallback(self):
        # Empty config should default to Ctags or Null
        semantic = resolve_semantic("python", {})
        self.assertEqual(semantic.provider_name, "NullProvider")

    def test_resolve_embedding_fallback(self):
        # Missing keys/configs should fallback to KeywordFallbackProvider
        embedding = resolve_embedding({"embedding_preference": "openai"})
        self.assertEqual(embedding.provider_name, "KeywordFallbackProvider")

    def test_versioned_semantic_packs_loading(self):
        # Python semantic pack should load with version 1.0.0
        pack = load_semantic_pack("python")
        self.assertEqual(pack["version"], "1.0.0")
        self.assertIn("lsp", pack["provider_preference"])

    def test_versioned_framework_packs_loading(self):
        # django framework pack should load successfully
        pack = load_framework_pack("django")
        self.assertEqual(pack["version"], "1.0.0")
        self.assertTrue(len(pack["route_patterns"]) > 0)

    def test_versioned_tracks_packs_loading(self):
        # authz track pack should load rules successfully
        pack = load_track_pack("authz")
        self.assertEqual(pack["version"], "1.0.0")
        self.assertTrue(len(pack["rules"]) > 0)
        self.assertEqual(pack["rules"][0]["id"], "authz.ownership.missing")

    def test_lsp_provider_fallback(self):
        # Unconfigured LSPProvider should use fallback
        lsp = LSPProvider("", "", None)
        self.assertTrue(lsp.use_fallback)
        self.assertEqual(lsp.resolution_confidence(), 0.0)

    def test_lsif_provider_fallback(self):
        # Unconfigured LSIFProvider should use fallback
        lsif = LSIFProvider("", "", None)
        self.assertTrue(lsif.use_fallback)
        self.assertEqual(lsif.resolution_confidence(), 0.0)

    def test_codegraph_provider_fallback(self):
        # Unconfigured CodeGraphProvider should use fallback
        cg = CodeGraphProvider("", "", None)
        self.assertTrue(cg.use_fallback)
        self.assertEqual(cg.resolution_confidence(), 0.0)

    def test_ctags_is_structural_fallback(self):
        self.assertEqual(CtagsProvider(".", None).capability_level(), "L1")

    def test_lsp_provider_performs_initialize_before_query(self):
        seen_methods = []

        class FakeSocket:
            def __init__(self):
                self.pending = b""

            def settimeout(self, timeout):
                pass

            def close(self):
                pass

            def sendall(self, payload):
                request = json.loads(payload.split(b"\r\n\r\n", 1)[1].decode())
                method = request.get("method")
                seen_methods.append(method)
                if method == "initialize":
                    response = {"jsonrpc": "2.0", "id": request["id"], "result": {"capabilities": {}}}
                elif method == "textDocument/definition":
                    response = {"jsonrpc": "2.0", "id": request["id"], "result": {"uri": "file:///tmp/app.py", "range": {"start": {"line": 0}, "end": {"line": 0}}}}
                else:
                    return
                body = json.dumps(response).encode()
                self.pending += f"Content-Length: {len(body)}\r\n\r\n".encode() + body

            def recv(self, count):
                chunk, self.pending = self.pending[:count], self.pending[count:]
                return chunk

        fake_socket = FakeSocket()
        repo_dir = tempfile.mkdtemp()
        try:
            with open(os.path.join(repo_dir, "app.py"), "w", encoding="utf-8") as source:
                source.write("def target():\n    pass\n")
            with patch("src_v3.providers.semantic.lsp_provider.socket.create_connection", return_value=fake_socket):
                lsp = LSPProvider("127.0.0.1:9999", repo_dir, None)
                definitions = lsp.find_definitions({"symbol": "target", "file": "app.py", "span": {"start": 1, "end": 1}})
            self.assertFalse(lsp.use_fallback)
            self.assertIn("initialize", seen_methods)
            self.assertIn("initialized", seen_methods)
            self.assertIn("textDocument/didOpen", seen_methods)
            self.assertEqual(definitions[0]["kind"], "definition")
        finally:
            shutil.rmtree(repo_dir)

    def test_openai_embedding_provider_fallback(self):
        # Unconfigured OpenAIProvider should return False for indexing and empty for search
        op = OpenAIProvider("")
        self.assertFalse(op.build_index([], ""))
        self.assertEqual(op.search("query", "", 5), [])

    def test_gemini_embedding_provider_fallback(self):
        gp = GeminiProvider("")
        self.assertFalse(gp.build_index([], ""))
        self.assertEqual(gp.search("query", "", 5), [])

    def test_cohere_embedding_provider_fallback(self):
        cp = CohereProvider("")
        self.assertFalse(cp.build_index([], ""))
        self.assertEqual(cp.search("query", "", 5), [])

    def test_fastembed_embedding_provider_fallback(self):
        fp = FastEmbedProvider()
        # Should behave gracefully if model is not loaded
        self.assertFalse(fp.build_index([], ""))
        self.assertEqual(fp.search("query", "", 5), [])

    def test_wasm_provider_is_transparent_native_shim(self):
        provider = TreeSitterWASMProvider()
        self.assertFalse(provider.is_real_wasm_runtime)
        self.assertEqual(provider.runtime_kind, "native-shim")
        self.assertEqual(provider.provider_version(), "1.0.0-native-shim")
        self.assertTrue(provider.is_fallback_for_lang("python"))

    def test_resolve_frameworks_preserves_multiple_matches(self):
        profile = RepoProfile(frameworks=["django", "fastapi"])
        providers = resolve_frameworks(profile, "python")
        names = [p.framework_name for p in providers]
        self.assertIn("DjangoPack", names)
        self.assertIn("GenericFrameworkProvider", names)

if __name__ == "__main__":
    unittest.main()
