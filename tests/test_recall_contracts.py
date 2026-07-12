import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from src_v3.core.models import CandidateRecord, IREdge, LanguageShard, SymbolNode
from src_v3.recall.graph_recall import expand_by_graph
from src_v3.recall.orchestrator import orchestrate_recall
from src_v3.recall.vector_recall import recall_by_vector
from src_v3.storage.ir_store import IRStore


class TestRecallContracts(unittest.TestCase):
    def setUp(self):
        self.workspace_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.workspace_dir)

    def test_channel_failure_is_logged_and_other_channels_continue(self):
        shard = LanguageShard(
            shard_id="python-root",
            lang="python",
            paths=["app.py"],
            capability="L1"
        )
        rule_candidate = CandidateRecord(
            candidate_id="",
            identity_key="",
            shard_id=shard.shard_id,
            lang=shard.lang,
            file="app.py",
            symbol="handle_auth",
            span={"start": 1, "end": 3},
            source_tracks=["authz"],
            matched_rules=["rule.authz.test"],
            recall_sources=["rule"],
            provider_trace=["test"],
            priority_score=42.0,
            candidate_capability="L1",
            status="discovered"
        )

        with patch("src_v3.recall.orchestrator.recall_by_rules", return_value=[rule_candidate]), \
             patch("src_v3.recall.orchestrator.recall_by_vector", side_effect=RuntimeError("vector index missing")), \
             patch("src_v3.recall.orchestrator.recall_by_resources", return_value=[]), \
             patch("src_v3.recall.orchestrator.recall_by_framework", return_value=[]), \
             patch("src_v3.recall.orchestrator.expand_by_graph", return_value=[]):
            candidates = orchestrate_recall(self.workspace_dir, shard, ["authz"], {})

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].symbol, "handle_auth")

        event_path = os.path.join(self.workspace_dir, "event_log.jsonl")
        with open(event_path, "r", encoding="utf-8") as f:
            events = [json.loads(line) for line in f if line.strip()]
        degradation_events = [e for e in events if e["event_type"] == "degradation"]
        self.assertEqual(len(degradation_events), 1)
        self.assertEqual(degradation_events[0]["metadata"]["channel"], "vector")

        metrics_path = os.path.join(self.workspace_dir, "metrics", "stage_metrics.json")
        with open(metrics_path, "r", encoding="utf-8") as f:
            metrics = json.load(f)
        self.assertEqual(metrics["recall"]["python-root.normalized_count"], 1)
        self.assertEqual(metrics["recall"]["python-root.channel_errors"][0]["channel"], "vector")

    def test_graph_recall_filters_neighbors_outside_shard(self):
        store = IRStore(self.workspace_dir)
        seed = SymbolNode("sym_app.py_seed_1_2", "symbol", "python", "app.py", "seed", {"start": 1, "end": 2}, {})
        in_shard = SymbolNode("sym_app.py_target_4_5", "symbol", "python", "app.py", "target", {"start": 4, "end": 5}, {})
        out_shard = SymbolNode("sym_other.py_external_1_2", "symbol", "python", "other.py", "external", {"start": 1, "end": 2}, {})
        store.save([
            seed,
            in_shard,
            out_shard
        ], [
            IREdge("e1", "call", seed.node_id, in_shard.node_id, provider_trace=["LSPProvider"]),
            IREdge("e2", "call", seed.node_id, out_shard.node_id, provider_trace=["LSPProvider"])
        ])
        shard = LanguageShard("python-root", "python", ["app.py"], capability="L2")
        seed_candidate = CandidateRecord("", "", shard.shard_id, shard.lang, "app.py", "seed", {"start": 1, "end": 2})

        candidates = expand_by_graph(self.workspace_dir, shard, "authz", [seed_candidate])

        self.assertEqual([cand.symbol for cand in candidates], ["target"])
        self.assertEqual(candidates[0].provider_trace, ["LSPProvider"])

    def test_vector_recall_marks_keyword_fallback_trace(self):
        class FakeKeywordProvider:
            provider_name = "KeywordFallbackProvider"

            def search(self, query, index_dir, top_k=10):
                return [{"id": "sym_app.py_authorize_1_2", "score": 0.7}]

        os.makedirs(os.path.join(self.workspace_dir, "indices", "lexical", "python-root"), exist_ok=True)
        store = IRStore(self.workspace_dir)
        store.save([
            SymbolNode("sym_app.py_authorize_1_2", "symbol", "python", "app.py", "authorize", {"start": 1, "end": 2}, {})
        ], [])
        shard = LanguageShard("python-root", "python", ["app.py"], capability="L1")

        with patch("src_v3.recall.vector_recall.resolve_embedding", return_value=FakeKeywordProvider()):
            candidates = recall_by_vector(self.workspace_dir, shard, "authz", {})

        self.assertEqual(len(candidates), 1)
        self.assertIn("KeywordFallbackProvider", candidates[0].provider_trace)
        self.assertIn("embedding_fallback: lexical keyword search", candidates[0].provider_trace)


if __name__ == "__main__":
    unittest.main()
