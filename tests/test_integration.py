import unittest
import os
import shutil
import tempfile
import json
import subprocess
import sys

class TestIntegration(unittest.TestCase):
    def setUp(self):
        # Create a temp directory for the project and workspace
        self.tmp_dir = tempfile.mkdtemp()
        self.project_dir = os.path.join(self.tmp_dir, "mock_project")
        os.makedirs(self.project_dir, exist_ok=True)
        
        # Create a mock python view file with entrypoint, guard, database access
        self.py_code = """
# django views example
from django.contrib.auth.decorators import login_required

def user_has_perm(request):
    pass

def query_db_objects():
    pass

def update_user_profile(request):
    user_has_perm(request)
    query_db_objects()
    return "success"

def public_status_check(request):
    status = get_system_status()
    return status
"""
        with open(os.path.join(self.project_dir, "views.py"), "w") as f:
            f.write(self.py_code)
            
        # Create package.json to trigger frameworks
        with open(os.path.join(self.project_dir, "package.json"), "w") as f:
            f.write('{"dependencies": {"express": "4.18.2"}}')
            
        with open(os.path.join(self.project_dir, "manage.py"), "w") as f:
            f.write("# django manage.py stub")
            
        self.workspace_dir = os.path.join(self.project_dir, ".audit_workspace_v3")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def run_cmd(self, command_args: list) -> dict:
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        cmd = [sys.executable] + command_args
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, f"CMD failed: {' '.join(cmd)}\nStderr: {proc.stderr}\nStdout: {proc.stdout}")
        
        # Parse last JSON line from stdout
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        if not lines:
            raise ValueError(f"No output returned from command: {' '.join(cmd)}")
        return json.loads(lines[-1])

    def test_e2e_pipeline_and_cache(self):
        cli_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src_v3", "cli")
        
        # 1. Run E2E Orchestrated Audit
        orchestrate_script = os.path.join(cli_dir, "orchestrate_audit.py")
        res = self.run_cmd([orchestrate_script, "--project", self.project_dir])
        self.assertTrue(res["ok"])
        
        # 2. Check workspace structure
        self.assertTrue(os.path.exists(self.workspace_dir))
        self.assertTrue(os.path.exists(os.path.join(self.workspace_dir, "audit_plan.json")))
        self.assertTrue(os.path.exists(os.path.join(self.workspace_dir, "repo_profile.json")))
        
        # Verify candidate count (should find candidates due to keywords/framework tags)
        candidate_registry = os.path.join(self.workspace_dir, "candidates", "candidate_registry.jsonl")
        self.assertTrue(os.path.exists(candidate_registry))
        with open(candidate_registry, "r") as f:
            cands = [json.loads(l) for l in f if l.strip()]
        self.assertTrue(len(cands) > 0)
        
        # 3. Verify that verification results and reports were compiled during the orchestrated run
        
        # Verify verification results output file
        results_path = os.path.join(self.workspace_dir, "evidence", "verification_results.jsonl")
        self.assertTrue(os.path.exists(results_path))
        with open(results_path, 'r', encoding='utf-8') as f:
            results = [json.loads(line.strip()) for line in f if line.strip()]
        self.assertTrue(len(results) > 0)
        
        # Verify compiled reports
        reports_dir = os.path.join(self.workspace_dir, "reports")
        self.assertTrue(os.path.exists(os.path.join(reports_dir, "coverage_report.md")))
        self.assertTrue(os.path.exists(os.path.join(reports_dir, "audit_report.md")))
        self.assertTrue(os.path.exists(os.path.join(reports_dir, "review_queue.md")))
        self.assertTrue(os.path.exists(os.path.join(reports_dir, "metrics_report.md")))
        
        # 5. Incremental run: re-run build_ir and check cache hits (should have 100% hits)
        build_ir_script = os.path.join(cli_dir, "build_ir.py")
        res_ir = self.run_cmd([build_ir_script, "--workspace", self.workspace_dir])
        self.assertTrue(res_ir["ok"])
        # In a mock repository, cache hits should be at least 1 for the files
        self.assertTrue(res_ir["summary"]["cache_hits"] >= 1)
        self.assertEqual(res_ir["summary"]["cache_misses"], 0)

if __name__ == "__main__":
    unittest.main()
