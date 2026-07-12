import unittest
from src_v3.core.models import CandidateRecord
from src_v3.core.enums import CandidateStatus
from src_v3.prune.scorer import calculate_priority_score
from src_v3.prune.static_pruner import evaluate_pruning_against_labels, prune_candidates

class TestPruner(unittest.TestCase):
    def test_calculate_priority_score(self):
        features = {
            "signal_score": 1.0,
            "semantic_similarity_score": 0.8,
            "reachability_score": 0.5,
            "guard_conflict_score": 1.0,
            "framework_risk_score": 0.9,
            "code_quality_score": 0.8
        }
        score = calculate_priority_score(features, {})
        # Check that score is computed and stays in range [0, 100]
        self.assertTrue(0.0 <= score <= 100.0)

    def test_prune_candidates(self):
        cands = [
            CandidateRecord(
                candidate_id="c1", identity_key="k1", shard_id="s1", lang="python",
                file="f1.py", symbol="s1", span={"start": 1, "end": 10}, priority_score=80.0
            ),
            CandidateRecord(
                candidate_id="c2", identity_key="k2", shard_id="s1", lang="python",
                file="f1.py", symbol="s2", span={"start": 1, "end": 10}, priority_score=30.0
            )
        ]
        kept, metrics = prune_candidates(cands, threshold=45.0)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].candidate_id, "c1")
        self.assertEqual(metrics["recalled_total"], 2)
        self.assertEqual(metrics["pruned_total"], 1)
        self.assertEqual(metrics["dropped_total"], 1)
        self.assertEqual(metrics["compression_ratio"], 0.5)
        self.assertEqual(metrics["kept_ids"], ["c1"])
        self.assertEqual(metrics["dropped_ids"], ["c2"])
        self.assertEqual(cands[1].status, "discovered")
        self.assertNotEqual(cands[1].status, CandidateStatus.FALSE_POSITIVE.value)

    def test_labeled_pruning_fixture_metrics(self):
        cands = [
            CandidateRecord(
                candidate_id="must_keep", identity_key="k1", shard_id="s1", lang="python",
                file="api/auth.py", symbol="authorize", span={"start": 1, "end": 10}, priority_score=82.0
            ),
            CandidateRecord(
                candidate_id="low_signal", identity_key="k2", shard_id="s1", lang="python",
                file="docs/example.py", symbol="sample", span={"start": 1, "end": 10}, priority_score=18.0
            ),
            CandidateRecord(
                candidate_id="also_keep", identity_key="k3", shard_id="s1", lang="python",
                file="routes/pay.py", symbol="pay", span={"start": 1, "end": 10}, priority_score=61.0
            )
        ]
        metrics = evaluate_pruning_against_labels(cands, {"must_keep", "also_keep"}, threshold=45.0)
        self.assertEqual(metrics["fixture_recall"], 1.0)
        self.assertEqual(metrics["false_drop_total"], 0)
        self.assertEqual(metrics["unexpected_keep_total"], 0)

if __name__ == "__main__":
    unittest.main()
