import unittest
import os
import shutil
import tempfile
import json
import subprocess
import sys
import time

# Fixed Golden Baseline representing the stable expectations of the mock project scan.
GOLDEN_BASELINE = {
    "candidate_count": 3,
    "candidates": [
        {"symbol": "authenticate_user", "file": "app.py"},
        {"symbol": "query_database", "file": "app.py"},
        {"symbol": "request", "file": "app.py"}
    ]
}

class TestRegression(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.project_dir = os.path.join(self.tmp_dir, "mock_project")
        os.makedirs(self.project_dir, exist_ok=True)
        
        # Simple codebase to trigger rules & framework
        self.py_code = """
def authenticate_user(request):
    # authz pattern
    return True

def query_database(query):
    # injection sink
    pass
"""
        with open(os.path.join(self.project_dir, "app.py"), "w") as f:
            f.write(self.py_code)
            
        with open(os.path.join(self.project_dir, "package.json"), "w") as f:
            f.write('{"dependencies": {"express": "4.18.2"}}')
            
        self.workspace_dir = os.path.join(self.project_dir, ".audit_workspace_v3")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def run_pipeline(self) -> float:
        """
        Runs E2E orchestrated pipeline and returns wall clock duration.
        """
        cli_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src_v3", "cli")
        orchestrate_script = os.path.join(cli_dir, "orchestrate_audit.py")
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        t0 = time.time()
        proc = subprocess.run([sys.executable, orchestrate_script, "--project", self.project_dir], capture_output=True, text=True, env=env)
        duration = time.time() - t0
        
        if proc.returncode != 0:
            raise RuntimeError(f"Pipeline execution failed. Returncode: {proc.returncode}. Stderr: {proc.stderr}")
            
        return duration

    def load_regression_snapshot(self):
        registry_path = os.path.join(self.workspace_dir, "candidates", "candidate_registry.jsonl")
        with open(registry_path, "r", encoding="utf-8") as f:
            candidates = [json.loads(line) for line in f if line.strip()]
        plan_path = os.path.join(self.workspace_dir, "audit_plan.json")
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
        coverage_path = os.path.join(self.workspace_dir, "reports", "coverage_report.md")
        with open(coverage_path, "r", encoding="utf-8") as f:
            coverage = f.read()
        fallback_shards = sum(1 for shard in plan["language_shards"] if shard["status"] in ["indexed_fallback", "recalled_fallback", "failed"])
        return {
            "candidates": sorted((c["symbol"], c["file"]) for c in candidates),
            "fallback_ratio": fallback_shards / max(1, len(plan["language_shards"])),
            "coverage": coverage
        }

    def test_regression_baseline_comparison(self):
        # 1. Run pipeline and measure wall clock performance
        duration = self.run_pipeline()
        
        # 2. Performance benchmark threshold check: mock project should complete within 5.0 seconds
        self.assertLess(duration, 5.0, f"Performance Benchmark Failed: Pipeline took {duration:.2f}s (threshold: 5.0s)")

        # 3. Load generated candidates from candidates/candidate_registry.jsonl
        registry_path = os.path.join(self.workspace_dir, "candidates", "candidate_registry.jsonl")
        self.assertTrue(os.path.exists(registry_path), "Candidate registry was not generated.")
        
        candidates = []
        with open(registry_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    candidates.append(json.loads(line.strip()))
                    
        print("GENERATED CANDIDATES:", [c["symbol"] for c in candidates])
        self.assertEqual(
            len(candidates), 
            GOLDEN_BASELINE["candidate_count"], 
            f"Regression detected: Candidate count {len(candidates)} mismatch with Golden Baseline count {GOLDEN_BASELINE['candidate_count']}."
        )
        
        # Match candidates symbols and files
        symbols_found = {c["symbol"]: c["file"] for c in candidates}
        for expected in GOLDEN_BASELINE["candidates"]:
            self.assertIn(expected["symbol"], symbols_found, f"Missing expected candidate: {expected['symbol']}")
            self.assertEqual(symbols_found[expected["symbol"]], expected["file"], f"Location mismatch for: {expected['symbol']}")

        first_snapshot = self.load_regression_snapshot()

        # A second complete pipeline run must preserve candidates, fallback
        # visibility, and the user-facing coverage report.
        warm_duration = self.run_pipeline()
        second_snapshot = self.load_regression_snapshot()
        self.assertEqual(second_snapshot, first_snapshot)
        self.assertLessEqual(warm_duration, duration * 1.5, "Warm full run regressed unexpectedly.")

        # 5. Incremental Build Cache Hit/Miss Validation
        # Re-run build_ir and assert that we hit cache for all files and have zero misses
        cli_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src_v3", "cli")
        build_ir_script = os.path.join(cli_dir, "build_ir.py")
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        t_inc_start = time.time()
        proc = subprocess.run([sys.executable, build_ir_script, "--workspace", self.workspace_dir], capture_output=True, text=True, env=env)
        inc_duration = time.time() - t_inc_start
        
        self.assertEqual(proc.returncode, 0, f"Incremental build_ir failed: {proc.stderr}")
        res = json.loads(proc.stdout.strip())
        
        # Verify cache hits and misses contract
        cache_hits = res["summary"].get("cache_hits", 0)
        cache_misses = res["summary"].get("cache_misses", 0)
        self.assertGreaterEqual(cache_hits, 1, f"Expected at least 1 cache hit for app.py, got {cache_hits}")
        self.assertEqual(cache_misses, 0, f"Expected 0 cache misses on incremental run, got {cache_misses}")
        
        # Incremental build should be significantly faster (benchmark threshold: < 1.0s)
        self.assertLess(inc_duration, 1.0, f"Incremental build was too slow: took {inc_duration:.2f}s")

if __name__ == "__main__":
    unittest.main()
