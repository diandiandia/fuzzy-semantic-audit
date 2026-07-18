import os
import unittest
import tempfile
import json
from src_v4.verify.tools import AgentTools
from src_v4.verify.agentic_triage import VerifierAgent, TokenBudgetGuard, BudgetExceededException

class TestAgenticTriage(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.repo_path = self.test_dir.name
        
        # Create some mock project files
        self.java_service = "com/example/MyService.java"
        self.java_impl = "com/example/MyServiceImpl.java"
        
        os.makedirs(os.path.join(self.repo_path, "com/example"), exist_ok=True)
        
        with open(os.path.join(self.repo_path, self.java_service), "w") as f:
            f.write("""package com.example;
            public interface MyService {
                void execute();
            }
            """)
            
        with open(os.path.join(self.repo_path, self.java_impl), "w") as f:
            f.write("""package com.example;
            public class MyServiceImpl implements MyService {
                public void execute() {
                    // entry point calls sink
                    sinkCall();
                }
                
                public void sinkCall() {
                    System.out.println("sink");
                }
                
                public void main(String[] args) {
                    execute();
                }
            }
            """)
            
        self.tools = AgentTools(self.repo_path)
        self.agent = VerifierAgent()

    def tearDown(self):
        self.test_dir.cleanup()

    def test_read_file_segment(self):
        segment = self.tools.read_file_segment(self.java_service, 2, 4)
        self.assertIn("MyService", segment)
        self.assertIn("2:", segment)
        self.assertIn("3:", segment)

    def test_find_callers(self):
        callers = self.tools.find_callers("sinkCall")
        self.assertEqual(len(callers), 1)
        self.assertEqual(callers[0]["symbol"], "MyServiceImpl.execute")
        self.assertEqual(callers[0]["file"], self.java_impl)

    def test_find_implementations(self):
        impls = self.tools.find_implementations("MyService")
        self.assertEqual(len(impls), 1)
        self.assertEqual(impls[0]["class"], "MyServiceImpl")
        self.assertEqual(impls[0]["file"], self.java_impl)

    def test_parse_action(self):
        tool, args = self.agent.parse_action('Thought: testing\nAction: find_callers(symbol="onCommand", file_path="foo.java")')
        self.assertEqual(tool, "find_callers")
        self.assertEqual(args.get("symbol"), "onCommand")
        self.assertEqual(args.get("file_path"), "foo.java")

    def test_parse_verdict(self):
        verdict, path = self.agent.parse_verdict('Thought: done\nVerdict: YES\nPath: ["sinkCall", "execute", "main"]')
        self.assertEqual(verdict, "YES")
        self.assertEqual(path, ["sinkCall", "execute", "main"])

    def test_budget_guard(self):
        guard = TokenBudgetGuard(max_turns=2, max_tokens=100)
        # First turn (50 characters ~ 12 tokens)
        guard.check_and_record(10, 40)
        # Second turn (150 characters ~ 37 tokens)
        guard.check_and_record(50, 100)
        
        # Third turn should raise budget exception
        with self.assertRaises(BudgetExceededException):
            guard.check_and_record(10, 10)

    def test_local_fallback_triage(self):
        # We start from sinkCall candidate, the local fallback trace should trace backwards:
        # sinkCall -> MyServiceImpl.execute -> MyServiceImpl.main (contains 'main' so it is YES)
        candidate = {
            "candidate_id": "cand_001",
            "symbol": "sinkCall",
            "file_path": self.java_impl,
            "line_number": 8
        }
        res = self.agent.verify_candidate(candidate, self.tools)
        self.assertEqual(res["verdict"], "YES")
        self.assertEqual(res["reasoning_path"], ["sinkCall", "MyServiceImpl.execute", "MyServiceImpl.main"])

if __name__ == "__main__":
    unittest.main()
