import os
import unittest
import tempfile
import json
from src_v4.filter.coarse_scanner import ASTCoarseScanner
from src_v4.filter.severity_scorer import SeverityScorer

class TestCoarseScannerAndScorer(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.repo_path = self.test_dir.name
        self.scanner = ASTCoarseScanner()
        self.scorer = SeverityScorer()

    def tearDown(self):
        self.test_dir.cleanup()

    def test_scanner_regex_fallback_and_scorer(self):
        # Create a mock java file with various potential findings
        java_content = """package com.example;
        
        public class MyService {
            // Critical finding: Entrypoint + Privilege + Risk Key + Density all on one line
            public void onCommand(Binder binder) { deletePermission(); }
            
            // High finding: Entrypoint + Privilege
            public void onTransact(AttributionSource source) {
                // do nothing
            }
            
            // Low finding: just keyword
            public void exec() {
                // dummy
            }
        }
        """
        file_path = "MyService.java"
        abs_path = os.path.join(self.repo_path, file_path)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(java_content)
            
        # Mock pack
        pack = {
            "scanned_languages": ["java"],
            "rules": {
                "java": {
                    "keywords": ["onCommand", "onTransact", "exec"],
                    "regex_patterns": ["deletePermission"],
                    "ast_queries": []
                }
            }
        }
        
        candidates = self.scanner.scan([file_path], pack, self.repo_path)
        
        # Run scorer
        scored_queue = self.scorer.score_and_queue(candidates, self.repo_path)
        
        # Verify sorting and scoring
        first = scored_queue[0]
        self.assertEqual(first["severity"], "Critical")
        self.assertEqual(first["score"], 100.0) # 30(onCommand) + 30(Binder) + 20(deletePermission/delete) + 20(density) = 100
        
        # Verify persistence
        queue_path = os.path.join(self.repo_path, "verify_queue.json")
        self.assertTrue(os.path.exists(queue_path))
        with open(queue_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(data[0]["candidate_id"], first["candidate_id"])
            self.assertEqual(data[0]["severity"], "Critical")

if __name__ == "__main__":
    unittest.main()
