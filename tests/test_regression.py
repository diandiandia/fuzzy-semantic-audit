import unittest
import os
import shutil
import tempfile
import json
import subprocess
import sys

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

    def run_pipeline(self):
        cli_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src_v3", "cli")
        orchestrate_script = os.path.join(cli_dir, "orchestrate_audit.py")
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        proc = subprocess.run([sys.executable, orchestrate_script, "--project", self.project_dir], capture_output=True, text=True, env=env)
        return proc.returncode == 0

    def test_regression_baseline_comparison(self):
        # 1. Run pipeline for the first time to establish Baseline
        success = self.run_pipeline()
        self.assertTrue(success)
        
        # Load baseline candidate count
        registry_path = os.path.join(self.workspace_dir, "candidates", "candidate_registry.jsonl")
        self.assertTrue(os.path.exists(registry_path))
        with open(registry_path, "r") as f:
            baseline_cands = [json.loads(l) for l in f if l.strip()]
        baseline_count = len(baseline_cands)
        
        # Load baseline reports
        report_path = os.path.join(self.workspace_dir, "reports", "coverage_report.md")
        self.assertTrue(os.path.exists(report_path))
        with open(report_path, "r") as f:
            baseline_report_content = f.read()

        # 2. Run pipeline for the second time (clean regression check)
        # Clear workspace but keep cache or do a fresh run
        shutil.rmtree(self.workspace_dir)
        success = self.run_pipeline()
        self.assertTrue(success)
        
        # Load new candidate count
        with open(registry_path, "r") as f:
            new_cands = [json.loads(l) for l in f if l.strip()]
        new_count = len(new_cands)
        
        # Load new report content
        with open(report_path, "r") as f:
            new_report_content = f.read()

        # 3. Assert regression equality (Candidate counts and reports should match baseline)
        self.maxDiff = None
        self.assertEqual(new_count, baseline_count, "Regression detected: candidate count changed!")
        self.assertEqual(new_report_content, baseline_report_content, "Regression detected: report content changed!")

if __name__ == "__main__":
    unittest.main()
