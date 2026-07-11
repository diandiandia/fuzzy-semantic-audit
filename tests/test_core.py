import unittest
import os
import shutil
import tempfile
from src_v3.core.models import AuditPlan, RunManifest, LanguageShard
from src_v3.core.enums import ShardStatus, CandidateStatus
from src_v3.core.state_machine import can_transition, transition
from src_v3.core.plan_io import save_plan, load_plan

class TestCore(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_run_manifest_serialization(self):
        manifest = RunManifest(
            run_id="test-run",
            run_mode="rule_only",
            run_capability="L0",
            providers={"parser": "TreeSitterNativeProvider"},
            degradation_reasons=["test reason"]
        )
        d = manifest.to_dict()
        self.assertEqual(d["run_id"], "test-run")
        self.assertEqual(d["providers"]["parser"], "TreeSitterNativeProvider")
        
        manifest2 = RunManifest.from_dict(d)
        self.assertEqual(manifest2.run_id, "test-run")
        self.assertEqual(manifest2.degradation_reasons, ["test reason"])

    def test_state_machine_shard_transitions(self):
        # Valid: discovered -> parsed
        self.assertTrue(can_transition("shard", ShardStatus.DISCOVERED, ShardStatus.PARSED))
        # Invalid: parsed -> recalled
        self.assertFalse(can_transition("shard", ShardStatus.PARSED, ShardStatus.RECALLED))
        
        shard = LanguageShard(shard_id="test", lang="python", status=ShardStatus.DISCOVERED.value)
        transition(shard, ShardStatus.PARSED.value)
        self.assertEqual(shard.status, ShardStatus.PARSED.value)

    def test_state_machine_candidate_transitions(self):
        # Invalid: deferred -> verified
        self.assertFalse(can_transition("candidate", CandidateStatus.DEFERRED, CandidateStatus.VERIFIED))
        # Valid: verifying -> verified
        self.assertTrue(can_transition("candidate", CandidateStatus.VERIFYING, CandidateStatus.VERIFIED))
        
        # Test backward transition metadata constraints
        from src_v3.core.models import CandidateRecord
        cand = CandidateRecord(
            candidate_id="c1", identity_key="k1", shard_id="s1", lang="python",
            file="app.py", symbol="foo", span={"start": 1, "end": 10}, priority_score=80.0,
            status=CandidateStatus.VERIFIED.value
        )
        
        # Should raise error without override_reason
        with self.assertRaises(ValueError):
            transition(cand, CandidateStatus.QUEUED_FOR_VERIFY.value)
            
        # Should succeed with override_reason
        transition(cand, CandidateStatus.QUEUED_FOR_VERIFY.value, metadata={"override_reason": "Re-run verify"})
        self.assertEqual(cand.status, CandidateStatus.QUEUED_FOR_VERIFY.value)

    def test_plan_io(self):
        plan_path = os.path.join(self.tmp_dir, "audit_plan.json")
        plan = AuditPlan(
            version="3",
            repo_path="/repo",
            workspace_dir=self.tmp_dir,
            repo_profile_path="repo_profile.json",
            audit_tracks=["authz"],
            created_at="",
            updated_at=""
        )
        save_plan(plan, plan_path)
        
        loaded = load_plan(plan_path)
        self.assertEqual(loaded.version, "3")
        self.assertEqual(loaded.repo_path, "/repo")
        self.assertEqual(loaded.audit_tracks, ["authz"])
        self.assertTrue(loaded.created_at != "")

if __name__ == "__main__":
    unittest.main()
