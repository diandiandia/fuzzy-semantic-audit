import unittest
import os
import sys
import subprocess
import json

class TestGoldenBaselines(unittest.TestCase):
    def test_synthetic_fixture_baseline(self):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        eval_script = os.path.join(project_root, "scripts", "evaluate_baseline.py")
        
        env = os.environ.copy()
        env["PYTHONPATH"] = project_root
        
        proc = subprocess.run([
            sys.executable, eval_script
        ], capture_output=True, text=True, env=env)
        
        self.assertEqual(proc.returncode, 0, f"evaluate_baseline.py failed with stderr: {proc.stderr}\nstdout: {proc.stdout}")
        
        # Load and parse output JSON
        try:
            output = json.loads(proc.stdout.strip())
        except json.JSONDecodeError:
            self.fail(f"Failed to parse JSON output: {proc.stdout}")
            
        self.assertEqual(output.get("baseline_id"), "synthetic_fixture")
        self.assertEqual(output.get("cases"), 1)
        self.assertEqual(output.get("passed"), 1)
        self.assertEqual(output.get("failed"), 0)
        self.assertGreaterEqual(output.get("recall_at_20"), 0.8)
        self.assertGreaterEqual(output.get("candidate_total"), 2)
        self.assertIn("fallback_ratio", output)
        self.assertIn("coverage_report_digest", output["results"][0])
        self.assertLessEqual(output.get("avg_candidates_after_prune"), 50)
        self.assertEqual(len(output.get("failures", [])), 0)

    def test_all_baselines_report_missing_real_repos_as_skipped(self):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        eval_script = os.path.join(project_root, "scripts", "evaluate_baseline.py")
        
        env = os.environ.copy()
        env["PYTHONPATH"] = project_root
        env.pop("FSA_BASELINE_AIRFLOW_DIR", None)
        env.pop("FSA_BASELINE_GRAFANA_DIR", None)
        env.pop("FSA_BASELINE_SUPABASE_DIR", None)
        env.pop("FSA_BASELINE_REPO_ROOT", None)

        proc = subprocess.run([
            sys.executable, eval_script, "--all", "--include-disabled"
        ], capture_output=True, text=True, env=env)
        
        self.assertEqual(proc.returncode, 0, f"evaluate_baseline.py failed with stderr: {proc.stderr}\nstdout: {proc.stdout}")
        output = json.loads(proc.stdout.strip())
        self.assertEqual(output.get("baseline_id"), "all")
        self.assertEqual(output.get("cases"), 1)
        self.assertEqual(output.get("passed"), 1)
        self.assertEqual(output.get("failed"), 0)
        self.assertGreaterEqual(output.get("skipped"), 3)
        skipped_repo_ids = {item.get("repo_id") for item in output.get("skipped_cases", [])}
        self.assertTrue({"airflow", "grafana", "supabase"}.issubset(skipped_repo_ids))

    def test_fail_on_skipped_makes_missing_real_baselines_fail(self):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        eval_script = os.path.join(project_root, "scripts", "evaluate_baseline.py")
        
        env = os.environ.copy()
        env["PYTHONPATH"] = project_root
        env.pop("FSA_BASELINE_AIRFLOW_DIR", None)
        env.pop("FSA_BASELINE_GRAFANA_DIR", None)
        env.pop("FSA_BASELINE_SUPABASE_DIR", None)
        env.pop("FSA_BASELINE_REPO_ROOT", None)

        proc = subprocess.run([
            sys.executable, eval_script, "--all", "--include-disabled", "--fail-on-skipped"
        ], capture_output=True, text=True, env=env)
        
        self.assertNotEqual(proc.returncode, 0)
        output = json.loads(proc.stdout.strip())
        self.assertGreaterEqual(output.get("skipped"), 3)

if __name__ == "__main__":
    unittest.main()
