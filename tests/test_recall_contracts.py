import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from src_v3.core.models import CandidateRecord, LanguageShard
from src_v3.recall.orchestrator import orchestrate_recall


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


if __name__ == "__main__":
    unittest.main()
