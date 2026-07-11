import unittest
import os
import json
from src_v3.core.models import RepoProfile, LanguageShard
from src_v3.core.provider_registry import resolve_parser, resolve_semantic, resolve_embedding
from src_v3.providers.parser.treesitter_native import TreeSitterNativeProvider
from src_v3.providers.semantic.null_provider import NullProvider
from src_v3.providers.semantic.lsp_provider import LSPProvider
from src_v3.providers.semantic.lsif_provider import LSIFProvider
from src_v3.providers.semantic.codegraph_provider import CodeGraphProvider
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
        self.assertEqual(pack["route_patterns"], [])

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

if __name__ == "__main__":
    unittest.main()
