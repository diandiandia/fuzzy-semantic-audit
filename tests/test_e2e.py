import os
import sys
import json
import shutil
import tempfile
import subprocess
import unittest

class TestE2E(unittest.TestCase):
    def setUp(self):
        # Create a temp directory inside the workspace for test project
        self.workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.test_project_dir = os.path.join(self.workspace_dir, "temp_test_project")
        if os.path.exists(self.test_project_dir):
            shutil.rmtree(self.test_project_dir)
        os.makedirs(self.test_project_dir, exist_ok=True)
        
        # 1. Create dummy Python files
        backend_dir = os.path.join(self.test_project_dir, "backend")
        os.makedirs(backend_dir, exist_ok=True)
        
        # Python file with IDOR/authz bypass and OS injection vulnerability
        self.py_code = """
def check_admin(user):
    # Dummy admin check
    return user.role == "admin"

def update_order(order_id, user_id, status_data):
    # Missing authorization/ownership check!
    # Direct access database
    db.execute(f"UPDATE orders SET status='{status_data}' WHERE id={order_id}")
    return {"status": "ok"}

def delete_user(user_id):
    # Danger: Command Injection
    import os
    cmd = f"rm -rf /data/users/{user_id}"
    os.system(cmd)
    return True
"""
        with open(os.path.join(backend_dir, "orders.py"), "w") as f:
            f.write(self.py_code)
            
        # 2. Create dummy JS files
        frontend_dir = os.path.join(self.test_project_dir, "frontend")
        os.makedirs(frontend_dir, exist_ok=True)
        
        self.js_code = """
function getProductDetails(productId) {
    // Standard access
    return db.query("SELECT * FROM products WHERE id = " + productId);
}

async function handleRequest(req, res) {
    const data = req.body;
    // Dangerous eval
    eval(data.code);
}
"""
        with open(os.path.join(frontend_dir, "api.js"), "w") as f:
            f.write(self.js_code)

    def tearDown(self):
        if os.path.exists(self.test_project_dir):
            shutil.rmtree(self.test_project_dir)

    def run_cmd(self, module, args):
        cmd = [sys.executable, "-m", module] + args
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=self.workspace_dir)
        return res

    def test_e2e_flow(self):
        # Step 1: Init Plan
        res = self.run_cmd("src_v2.cli.init_plan", ["--project", self.test_project_dir])
        self.assertEqual(res.returncode, 0, f"init_plan failed: {res.stderr}")
        
        last_line = res.stdout.strip().splitlines()[-1]
        init_data = json.loads(last_line)
        self.assertTrue(init_data["ok"])
        
        audit_workspace = init_data["workspace"]
        plan_path = init_data["plan"]
        
        self.assertTrue(os.path.exists(audit_workspace))
        self.assertTrue(os.path.exists(plan_path))
        
        # Verify tracks loaded dynamically (10 tracks)
        from src_v2.core.plan_io import load_plan
        plan_check = load_plan(plan_path)
        self.assertEqual(len(plan_check.audit_tracks), 10, "Failed to load 10 standard dynamic tracks!")
        
        # Step 2: Build Inventory
        res = self.run_cmd("src_v2.cli.build_inventory", ["--plan", plan_path])
        self.assertEqual(res.returncode, 0, f"build_inventory failed: {res.stderr}")
        
        last_line = res.stdout.strip().splitlines()[-1]
        inv_data = json.loads(last_line)
        self.assertTrue(inv_data["ok"])
        self.assertEqual(inv_data["shards_total"], 2)  # python, javascript (generic fallback is not added because all files are matched)
        
        # Check files
        repo_profile_path = os.path.join(audit_workspace, "repo_profile.json")
        self.assertTrue(os.path.exists(repo_profile_path))
        
        # Step 2.5: Build Index
        res = self.run_cmd("src_v2.cli.build_index", ["--plan", plan_path])
        self.assertEqual(res.returncode, 0, f"build_index failed: {res.stderr}")
        last_line = res.stdout.strip().splitlines()[-1]
        idx_data = json.loads(last_line)
        self.assertTrue(idx_data["ok"])
        self.assertEqual(idx_data["indexed_shards"], 2)
        
        # Verify shard statuses are "indexed"
        plan_check = load_plan(plan_path)
        self.assertTrue(all(s.status == "indexed" for s in plan_check.language_shards))
        
        # Step 3: Recall Candidates
        res = self.run_cmd("src_v2.cli.recall_candidates", ["--plan", plan_path])
        self.assertEqual(res.returncode, 0, f"recall_candidates failed: {res.stderr}")
        
        last_line = res.stdout.strip().splitlines()[-1]
        recall_data = json.loads(last_line)
        self.assertTrue(recall_data["ok"])
        self.assertGreater(recall_data["candidates_total"], 0)
        self.assertGreater(recall_data["queued_for_verify"], 0)
        
        # Verify shard statuses are "recalled"
        plan_check = load_plan(plan_path)
        self.assertTrue(all(s.status == "recalled" for s in plan_check.language_shards))
        
        # Check registry and queues
        registry_path = os.path.join(audit_workspace, "candidate_registry.jsonl")
        self.assertTrue(os.path.exists(registry_path))
        
        # Verify that graph and vector recall channels produced candidates
        from src_v2.core.candidate_registry import load_candidates
        cands_recalled = load_candidates(registry_path)
        recall_sources = set()
        for c in cands_recalled:
            recall_sources.update(c.recall_sources)
        self.assertTrue("graph" in recall_sources, "Graph recall channel did not produce any candidates!")
        self.assertTrue("vector" in recall_sources, "Vector recall channel did not produce any candidates!")
        
        verify_queue_path = os.path.join(audit_workspace, "queues", "verify_now.json")
        self.assertTrue(os.path.exists(verify_queue_path))
        with open(verify_queue_path, "r") as f:
            verify_q = json.load(f)
            self.assertEqual(len(verify_q["candidate_ids"]), recall_data["queued_for_verify"])

        # Step 4: Verify Batch (Get Batch)
        res = self.run_cmd("src_v2.cli.verify_batch", ["--plan", plan_path, "--get-batch", "--limit", "2"])
        self.assertEqual(res.returncode, 0, f"verify_batch get-batch failed: {res.stderr}")
        
        last_line = res.stdout.strip().splitlines()[-1]
        batch_data = json.loads(last_line)
        self.assertTrue(batch_data["ok"])
        self.assertEqual(len(batch_data["batch"]), 2)
        
        # Check packages directory and file packages
        packages_dir = os.path.join(audit_workspace, "packages")
        self.assertTrue(os.path.exists(packages_dir))
        for item in batch_data["batch"]:
            self.assertTrue(os.path.exists(item["pkg_path"]))
            with open(item["pkg_path"], "r") as pf:
                pkg_content = json.load(pf)
                self.assertEqual(pkg_content["candidate_id"], item["candidate_id"])
                self.assertTrue("code_snippet" in pkg_content)

        # Step 5: Verify Batch (Writeback verdicts)
        # Mock some referee decisions for the batch
        mock_verdicts = []
        for idx, item in enumerate(batch_data["batch"]):
            verdict = "verified" if idx == 0 else "needs_review"
            mock_verdicts.append({
                "candidate_id": item["candidate_id"],
                "verdict": verdict,
                "reason": f"Mock verification verdict: {verdict}",
                "referee_votes": [
                    {"lens": "reachability", "decision": "pass", "reason": "Mock pass"},
                    {"lens": "guard", "decision": "pass" if verdict == "verified" else "fail", "reason": "Mock guard"},
                    {"lens": "exploit", "decision": "pass", "reason": "Mock exploit"}
                ],
                "evidence": [
                    {"type": "mock_verdict", "value": "Mock path"}
                ]
            })
            
        temp_verdicts_file = os.path.join(audit_workspace, "temp_verdicts_test.json")
        with open(temp_verdicts_file, "w") as tf:
            json.dump(mock_verdicts, tf)
            
        res = self.run_cmd("src_v2.cli.verify_batch", ["--plan", plan_path, "--writeback", temp_verdicts_file])
        self.assertEqual(res.returncode, 0, f"verify_batch writeback failed: {res.stderr}")
        
        last_line = res.stdout.strip().splitlines()[-1]
        writeback_data = json.loads(last_line)
        self.assertTrue(writeback_data["ok"])
        self.assertEqual(writeback_data["consumed"], 2)
        self.assertEqual(writeback_data["verified"], 1)
        self.assertEqual(writeback_data["needs_review"], 1)
        
        # Verify remaining items remain in verify_now queue
        total_recalled = recall_data["queued_for_verify"]
        expected_remaining = total_recalled - 2
        from src_v2.core.queue_store import load_queue
        verify_now = load_queue(os.path.join(audit_workspace, "queues"), "verify_now")
        self.assertEqual(len(verify_now), expected_remaining)
        self.assertEqual(writeback_data["deferred"], 0)
        
        # Verify manual_review queue is updated and maintained as a first-class citizen
        manual_review = load_queue(os.path.join(audit_workspace, "queues"), "manual_review")
        self.assertEqual(len(manual_review), 1, "manual_review queue was not updated correctly!")
        
        # Step 6: Compile Reports
        res = self.run_cmd("src_v2.cli.compile_reports", ["--plan", plan_path])
        self.assertEqual(res.returncode, 0, f"compile_reports failed: {res.stderr}")
        
        last_line = res.stdout.strip().splitlines()[-1]
        reports_data = json.loads(last_line)
        self.assertTrue(reports_data["ok"])
        
        # Verify reports paths exist
        self.assertTrue(os.path.exists(reports_data["audit_report"]))
        self.assertTrue(os.path.exists(reports_data["coverage_report"]))
        self.assertTrue(os.path.exists(reports_data["review_queue"]))
        
        # Check coverage report content
        with open(reports_data["coverage_report"], "r") as crf:
            cr_content = crf.read()
            self.assertTrue("# Coverage Report" in cr_content)
            self.assertTrue("Run Summary" in cr_content)
            self.assertTrue("Shard Coverage" in cr_content)
            self.assertTrue("Track Coverage" in cr_content)
            self.assertTrue("Candidate Status" in cr_content)
            self.assertTrue("Phase Execution Durations" in cr_content)
            self.assertTrue("Language Shards Status" in cr_content)

    def test_edge_cases_and_failure_paths(self):
        """Test concurrent batch, partial writeback, lease timeout, and omitted votes writeback."""
        audit_workspace = os.path.join(self.test_project_dir, ".audit_workspace_v2")
        plan_path = os.path.join(audit_workspace, "audit_plan.json")

        # 1. Initialize and run recall
        self.run_cmd("src_v2.cli.init_plan", ["--project", self.test_project_dir])
        self.run_cmd("src_v2.cli.build_inventory", ["--plan", plan_path])
        self.run_cmd("src_v2.cli.build_index", ["--plan", plan_path])
        self.run_cmd("src_v2.cli.recall_candidates", ["--plan", plan_path])

        registry_path = os.path.join(audit_workspace, "candidate_registry.jsonl")
        queue_dir = os.path.join(audit_workspace, "queues")

        # 2. Test Concurrent Batch and Lease Timeout
        # Pull batch 1 of limit 1
        res1 = self.run_cmd("src_v2.cli.verify_batch", ["--plan", plan_path, "--get-batch", "--limit", "1"])
        self.assertEqual(res1.returncode, 0)
        batch1 = json.loads(res1.stdout.strip().splitlines()[-1])["batch"]
        self.assertEqual(len(batch1), 1)
        cid1 = batch1[0]["candidate_id"]

        # The item cid1 is now in "verifying" status.
        # Pull batch 2 of limit 1. Since cid1 is in verifying status (and its lease is NOT expired),
        # get-batch should NOT reissue cid1! It should pull a different candidate!
        res2 = self.run_cmd("src_v2.cli.verify_batch", ["--plan", plan_path, "--get-batch", "--limit", "1"])
        self.assertEqual(res2.returncode, 0)
        batch2 = json.loads(res2.stdout.strip().splitlines()[-1])["batch"]
        self.assertEqual(len(batch2), 1)
        cid2 = batch2[0]["candidate_id"]
        self.assertNotEqual(cid1, cid2, "Leased candidate was reissued concurrently!")

        # 3. Test Partial Writeback (other in-flight verifying items are NOT deferred)
        # Write back a verdict only for cid1
        mock_verdicts = [{
            "candidate_id": cid1,
            "verdict": "verified",
            "reason": "Mock verified",
            "referee_votes": [
                {"lens": "reachability", "decision": "pass", "reason": "Mock"},
                {"lens": "guard", "decision": "pass", "reason": "Mock"},
                {"lens": "exploit", "decision": "pass", "reason": "Mock"}
            ]
        }]
        temp_verdicts_file = os.path.join(audit_workspace, "temp_verdicts_partial.json")
        with open(temp_verdicts_file, "w") as tf:
            json.dump(mock_verdicts, tf)

        res_wb = self.run_cmd("src_v2.cli.verify_batch", ["--plan", plan_path, "--writeback", temp_verdicts_file])
        self.assertEqual(res_wb.returncode, 0)
        wb_data = json.loads(res_wb.stdout.strip().splitlines()[-1])
        # Verify that deferred is 0, meaning cid2 (which is still in-flight verifying) was NOT forcibly deferred!
        self.assertEqual(wb_data["deferred"], 0, "In-flight verifying candidate was incorrectly deferred on partial writeback!")

        # Reload registry and verify cid2 is still in "verifying" status
        from src_v2.core.candidate_registry import load_candidates
        cands = load_candidates(registry_path)
        cands_map = {c.candidate_id: c for c in cands}
        self.assertEqual(cands_map[cid2].status, "verifying")

        # 4. Test Omitted Votes Writeback (direct verdict injection is prohibited)
        mock_verdicts_bypass = [{
            "candidate_id": cid2,
            "verdict": "verified",
            "reason": "Attacker injecting directly",
            # referee_votes is omitted!
        }]
        temp_verdicts_bypass = os.path.join(audit_workspace, "temp_verdicts_bypass.json")
        with open(temp_verdicts_bypass, "w") as tf:
            json.dump(mock_verdicts_bypass, tf)

        res_wb_bypass = self.run_cmd("src_v2.cli.verify_batch", ["--plan", plan_path, "--writeback", temp_verdicts_bypass])
        self.assertEqual(res_wb_bypass.returncode, 0)

        # Verify that the registry status of cid2 is forced to needs_review, not verified!
        cands_bypass = load_candidates(registry_path)
        cands_bypass_map = {c.candidate_id: c for c in cands_bypass}
        self.assertEqual(cands_bypass_map[cid2].status, "needs_review")
        # Check verification_results.jsonl for the blocked reason
        results_file = os.path.join(audit_workspace, "verification_results.jsonl")
        with open(results_file, "r") as rf:
            results = [json.loads(line) for line in rf]
        cid2_result = [r for r in results if r["candidate_id"] == cid2][-1]
        self.assertTrue("Direct verdict injection is prohibited" in cid2_result["reason"])

        # 5. Test Lease Timeout Expiry
        # Manually backdate the updated_at timestamp of cid2 in the registry to simulate timeout
        from datetime import datetime, timedelta, timezone
        cands_to_backdate = load_candidates(registry_path)
        for c in cands_to_backdate:
            if c.candidate_id == cid2:
                # Set status back to verifying and backdate updated_at by 6 minutes
                c.status = "verifying"
                c.updated_at = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
        from src_v2.core.candidate_registry import save_candidates
        save_candidates(registry_path, cands_to_backdate)

        # Call get-batch again. This should trigger check_lease_expiry and defer the expired cid2!
        res_timeout = self.run_cmd("src_v2.cli.verify_batch", ["--plan", plan_path, "--get-batch", "--limit", "1", "--lease-timeout", "300"])
        self.assertEqual(res_timeout.returncode, 0)

        # Reload registry and verify cid2 is now in "deferred" status
        cands_post_timeout = load_candidates(registry_path)
        cands_post_timeout_map = {c.candidate_id: c for c in cands_post_timeout}
        self.assertEqual(cands_post_timeout_map[cid2].status, "deferred")

        # 6. Test Lease Renewal (heartbeat)
        # Reset cid2 to verifying and backdate updated_at by 6 minutes
        cands_renew = load_candidates(registry_path)
        for c in cands_renew:
            if c.candidate_id == cid2:
                c.status = "verifying"
                c.updated_at = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
        save_candidates(registry_path, cands_renew)
        
        # Run --renew-lease to heartbeat
        res_renew = self.run_cmd("src_v2.cli.verify_batch", ["--plan", plan_path, "--renew-lease", cid2])
        self.assertEqual(res_renew.returncode, 0)
        renew_data = json.loads(res_renew.stdout.strip().splitlines()[-1])
        self.assertTrue(renew_data["ok"])
        
        # Call get-batch again with --lease-timeout 300. Since we renewed, cid2 should NOT be deferred!
        res_timeout_post_renew = self.run_cmd("src_v2.cli.verify_batch", ["--plan", plan_path, "--get-batch", "--limit", "1", "--lease-timeout", "300"])
        self.assertEqual(res_timeout_post_renew.returncode, 0)
        
        # Reload registry and verify cid2 is still in "verifying" status because of heartbeat renewal!
        cands_post_renew = load_candidates(registry_path)
        cands_post_renew_map = {c.candidate_id: c for c in cands_post_renew}
        self.assertEqual(cands_post_renew_map[cid2].status, "verifying")

        # 7. Test error packaging cleanup
        from src_v2.core.models import CandidateRecord
        from src_v2.core.queue_store import load_queue, save_queue
        
        dummy_cand = CandidateRecord(
            candidate_id="cand_python-backend_non_existent_file_py_dummy_0_0\x00",
            identity_key="python-backend|non_existent_file.py|dummy|0|0\x00",
            shard_id="python-backend",
            lang="python",
            file="non_existent_file.py",
            symbol="dummy",
            span={"start": 0, "end": 0},
            source_tracks=["authz"],
            matched_rules=["generic.resource.access"],
            recall_sources=["rule"],
            priority=100,
            status="queued_for_verify"
        )
        # Save to registry
        cands_err = load_candidates(registry_path)
        cands_err.append(dummy_cand)
        save_candidates(registry_path, cands_err)
        
        # Add only dummy_cand to verify_now queue to isolate failed packaging test
        verify_now_err = [dummy_cand.candidate_id]
        save_queue(queue_dir, "verify_now", verify_now_err)
        
        # Run get-batch. It will try to package dummy_cand, which will raise FileNotFoundError.
        # It will set dummy_cand status to error and remove it from verify_now!
        res_err = self.run_cmd("src_v2.cli.verify_batch", ["--plan", plan_path, "--get-batch", "--limit", "1"])
        self.assertEqual(res_err.returncode, 0)
        
        # Verify dummy_cand is in error status in registry and removed from verify_now queue!
        cands_post_err = load_candidates(registry_path)
        cands_post_err_map = {c.candidate_id: c for c in cands_post_err}
        self.assertEqual(cands_post_err_map[dummy_cand.candidate_id].status, "error")
        
        verify_now_post_err = load_queue(queue_dir, "verify_now")
        self.assertNotIn(dummy_cand.candidate_id, verify_now_post_err, "Failed packaging candidate was not cleaned up from verify_now queue!")

if __name__ == "__main__":
    unittest.main()
