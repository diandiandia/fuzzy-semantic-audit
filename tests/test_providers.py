import unittest
from src_v3.core.models import RepoProfile
from src_v3.core.provider_registry import resolve_parser, resolve_semantic, resolve_embedding
from src_v3.providers.parser.treesitter_native import TreeSitterNativeProvider
from src_v3.providers.semantic.null_provider import NullProvider
from src_v3.providers.embedding.keyword_provider import KeywordFallbackProvider

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

if __name__ == "__main__":
    unittest.main()
