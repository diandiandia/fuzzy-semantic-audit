import os
import unittest
import tempfile
import json
from src_v4.cli.orchestrate_audit import AuditOrchestrator

class TestIntegrationWorkflow(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.repo_path = self.test_dir.name
        
        # Create a mock repository structure matching fallback rules
        self.service_dir = os.path.join(self.repo_path, "service")
        os.makedirs(self.service_dir, exist_ok=True)
        
        self.java_file = os.path.join(self.service_dir, "BinderService.java")
        with open(self.java_file, "w", encoding="utf-8") as f:
            f.write("""package com.example;
            public class BinderService {
                public void onCommand(Binder binder) {
                    checkCallingOrSelfPermission("android.permission.DELETE");
                }
                
                public void main(String[] args) {
                    onCommand(null);
                }
            }
            """)
            
        self.orchestrator = AuditOrchestrator()

    def tearDown(self):
        self.test_dir.cleanup()

    def test_full_orchestration_run(self):
        # Run orchestrator
        self.orchestrator.execute(self.repo_path)
        
        # 1. Check repo_profile.json
        profile_path = os.path.join(self.repo_path, "repo_profile.json")
        self.assertTrue(os.path.exists(profile_path))
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = json.load(f)
            self.assertIn("java", profile["languages"])
            self.assertEqual(profile["languages"]["java"], ["service/BinderService.java"])
            
        # 2. Check scan_pack.json
        pack_path = os.path.join(self.repo_path, "scan_pack.json")
        self.assertTrue(os.path.exists(pack_path))
        with open(pack_path, "r", encoding="utf-8") as f:
            pack = json.load(f)
            self.assertIn("java", pack["rules"])
            
        # 3. Check verify_queue.json
        queue_path = os.path.join(self.repo_path, "verify_queue.json")
        self.assertTrue(os.path.exists(queue_path))
        with open(queue_path, "r", encoding="utf-8") as f:
            queue = json.load(f)
            self.assertTrue(len(queue) > 0)
            
            # Verify status is completed
            for cand in queue:
                self.assertEqual(cand["status"], "DONE")
            
        # 4. Check reports/review_queue.md
        report_path = os.path.join(self.repo_path, "reports", "review_queue.md")
        self.assertTrue(os.path.exists(report_path))
        with open(report_path, "r", encoding="utf-8") as f:
            report_text = f.read()
            self.assertIn("Fuzzy Semantic Audit V4 — Audit Findings Report", report_text)

if __name__ == "__main__":
    unittest.main()
