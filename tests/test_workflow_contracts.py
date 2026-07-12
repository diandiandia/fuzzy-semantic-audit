import subprocess
import unittest
from unittest.mock import Mock, patch

from src_v3.cli import orchestrate_audit


class TestWorkflowContracts(unittest.TestCase):
    def test_run_stage_rejects_invalid_json_contract(self):
        completed = subprocess.CompletedProcess(
            args=["python", "stage.py"],
            returncode=0,
            stdout="not-json\n",
            stderr=""
        )
        with patch("src_v3.cli.orchestrate_audit.subprocess.run", return_value=completed):
            result = orchestrate_audit.run_stage("build_inventory", ["--workspace", "/tmp/ws"])

        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "build_inventory")
        self.assertIn("not valid JSON", result["message"])

    def test_run_stage_with_retry_recovers_after_transient_failure(self):
        calls = [
            {"ok": False, "stage": "build_ir", "message": "transient"},
            {"ok": True, "stage": "build_ir", "summary": {}}
        ]
        runner = Mock(side_effect=calls)

        with patch("src_v3.cli.orchestrate_audit.run_stage", runner), \
             patch("src_v3.cli.orchestrate_audit.time.sleep"):
            result = orchestrate_audit.run_stage_with_retry("build_ir", ["--workspace", "/tmp/ws"], max_retries=3)

        self.assertTrue(result["ok"])
        self.assertEqual(runner.call_count, 2)

    def test_run_stage_with_retry_returns_last_failure(self):
        runner = Mock(return_value={"ok": False, "stage": "verify_batch", "message": "still failing"})

        with patch("src_v3.cli.orchestrate_audit.run_stage", runner), \
             patch("src_v3.cli.orchestrate_audit.time.sleep"):
            result = orchestrate_audit.run_stage_with_retry("verify_batch", ["--workspace", "/tmp/ws"], max_retries=2)

        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "still failing")
        self.assertEqual(runner.call_count, 2)


if __name__ == "__main__":
    unittest.main()
