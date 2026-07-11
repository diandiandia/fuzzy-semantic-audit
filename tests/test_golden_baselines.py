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
        self.assertLessEqual(output.get("avg_candidates_after_prune"), 50)
        self.assertEqual(len(output.get("failures", [])), 0)

if __name__ == "__main__":
    unittest.main()
