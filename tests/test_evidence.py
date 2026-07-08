import unittest
from src_v3.evidence.completeness import calculate_completeness_score

class TestEvidence(unittest.TestCase):
    def test_completeness_score(self):
        # 1. Base case: empty bundle
        bundle = {}
        score1 = calculate_completeness_score(bundle)
        self.assertEqual(score1, 10) # Base JID score

        # 2. Case with symbol body
        bundle2 = {"symbol_body": "def foo(): pass"}
        score2 = calculate_completeness_score(bundle2)
        self.assertEqual(score2, 40) # 10 + 30

        # 3. Case with full evidence
        bundle3 = {
            "symbol_body": "def foo(): pass",
            "caller_chain": [{"symbol": "bar"}],
            "upstream_entrypoints": [{"symbol": "api"}],
            "guard_snippets": [{"symbol": "guard"}],
            "resource_snippets": [{"symbol": "db"}],
            "state_transition_snippets": [{"symbol": "update"}]
        }
        score3 = calculate_completeness_score(bundle3)
        self.assertEqual(score3, 100) # Full completeness score (100)

if __name__ == "__main__":
    unittest.main()
