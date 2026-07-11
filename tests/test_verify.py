import unittest
import os
import shutil
import tempfile
import json
from src_v3.verify.verdict_policy import evaluate_verdict
from src_v3.verify.writeback import VerificationWriteback
from src_v3.core.models import CandidateRecord, VerificationResult, AuditPlan, RunManifest
from src_v3.storage.candidate_store import CandidateStore
from src_v3.storage.queue_store import QueueStore

class TestVerify(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_evaluate_verdict(self):
        # 1. Reachability or exploitability is NO -> false_positive
        v1, r1 = evaluate_verdict({"reachability": "NO", "guarded": "NO", "exploitability": "YES"})
        self.assertEqual(v1, "false_positive")
        
        # 2. Guarded is YES -> false_positive
        v2, r2 = evaluate_verdict({"reachability": "YES", "guarded": "YES", "exploitability": "YES"})
        self.assertEqual(v2, "false_positive")
        
        # 3. Reach=YES, Guard=NO, Exploit=YES -> verified
        v3, r3 = evaluate_verdict({"reachability": "YES", "guarded": "NO", "exploitability": "YES"})
        self.assertEqual(v3, "verified")
        
        # 4. Indeterminate -> needs_review
        v4, r4 = evaluate_verdict({"reachability": "MAYBE", "guarded": "NO", "exploitability": "YES"})
        self.assertEqual(v4, "needs_review")
        
        # 5. Degraded run capability check: cand_level L3, run_level L2, indeterminate votes -> deferred
        v5, r5 = evaluate_verdict(
            {"reachability": "MAYBE", "guarded": "NO", "exploitability": "YES"},
            candidate_capability="L3",
            run_capability="L2"
        )
        self.assertEqual(v5, "deferred")

    def test_verification_writeback(self):
        wb = VerificationWriteback(self.tmp_dir)
        cand = CandidateRecord(
            candidate_id="c1", identity_key="k1", shard_id="s1", lang="python",
            file="f1.py", symbol="s1", span={"start": 1, "end": 10}, priority_score=80.0,
            status="verified"
        )
        res = VerificationResult(
            candidate_id="c1",
            verdict="verified",
            reason="Path confirmed.",
            confidence=0.8
        )
        
        wb.perform_writeback(
            updated_candidates=[cand],
            new_results=[res],
            manual_review_list=[],
            deferred_list=[]
        )
        
        # Verify candidate status saved
        store = CandidateStore(self.tmp_dir)
        saved = store.get_candidate_by_id("c1", pruned=True)
        self.assertIsNotNone(saved)
        self.assertEqual(saved.status, "verified")
        
        # Verify verification result saved
        self.assertTrue(os.path.exists(wb.results_path))
        with open(wb.results_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 1)
        res_data = json.loads(lines[0].strip())
        self.assertEqual(res_data["candidate_id"], "c1")
        self.assertEqual(res_data["verdict"], "verified")

if __name__ == "__main__":
    unittest.main()
