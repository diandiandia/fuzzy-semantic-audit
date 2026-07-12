import unittest

from scripts.benchmark_incremental_cache import run_benchmark
from scripts.evaluate_provider_matrix import run_matrix
from src_v3.core.models import LanguageShard, RepoProfile
from src_v3.core.provider_registry import resolve_provider_set


class TestProviderMatrixAndPerformance(unittest.TestCase):
    def test_semantic_provider_compatibility_matrix(self):
        result = run_matrix()
        self.assertTrue(result["ok"])
        rows = {row["provider"]: row for row in result["matrix"]}
        self.assertEqual(set(rows), {"lsif", "codegraph", "lsp"})
        for row in rows.values():
            self.assertFalse(row["fallback"])
            self.assertGreaterEqual(row["definitions"], 1)
            self.assertGreaterEqual(row["references"], 1)

    def test_incremental_cache_benchmark_contract(self):
        result = run_benchmark(files=4, min_speedup=0.0)
        self.assertTrue(result["cache_reuse_passed"])
        self.assertTrue(result["reports_consistent"])
        self.assertEqual(result["warm"]["build_ir"]["cache_misses"], 0)
        self.assertEqual(result["warm"]["build_index"]["rebuilt_count"], 0)
        self.assertGreater(result["speedup"], 0.0)

    def test_provider_set_embedding_trace_includes_model_and_version(self):
        shard = LanguageShard(shard_id="python-root", lang="python", paths=["app.py"])
        provider_set = resolve_provider_set(
            RepoProfile(),
            shard,
            {
                "embedding": {
                    "provider": "openai",
                    "api_key": "test-key",
                    "model": "text-embedding-3-large"
                }
            }
        )
        embedding_trace = next(item for item in provider_set["selector_trace"] if item["kind"] == "embedding")
        self.assertEqual(embedding_trace["metadata"]["provider_name"], "OpenAIProvider")
        self.assertEqual(embedding_trace["metadata"]["model"], "text-embedding-3-large")


if __name__ == "__main__":
    unittest.main()
