import unittest

from review_system.merge import merge_findings
from tests.helpers import finding


class MergeTests(unittest.TestCase):
    def test_merges_evidence_and_promotes_stronger_state(self):
        low = finding()
        high = finding(
            confidence="CONFIRMED",
            evidence=[{
                "level": "E3", "type": "test", "command": "pytest", "result": "failed", "summary": "reproduced"
            }],
            reproduction={"steps": ["run"], "observed": "bad", "expected": "good"},
        )
        result = merge_findings([[low], [high]])
        self.assertEqual(1, len(result["findings"]))
        self.assertEqual(2, len(result["findings"][0]["evidence"]))
        self.assertEqual("CONFIRMED", result["findings"][0]["confidence"])

    def test_conflict_preserved(self):
        a = finding()
        b = finding(severity="P1")
        result = merge_findings([[a], [b]])
        self.assertEqual("identity_mismatch", result["merge_conflicts"][0]["reason"])

    def test_rejected_and_active_versions_conflict(self):
        active = finding()
        rejected = finding(confidence="REJECTED", status="REJECTED")
        result = merge_findings([[active], [rejected]])
        self.assertEqual("rejected_vs_active", result["merge_conflicts"][0]["reason"])

if __name__ == "__main__":
    unittest.main()
