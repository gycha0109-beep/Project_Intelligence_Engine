import json
import unittest
from pathlib import Path

from review_system.workflow_semantics import analyze_workflow_patch


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "trust-risk-calibration"
    / "workflow-diff-semantics-d1-seen-v1.json"
)


class WorkflowDiffSemanticsTests(unittest.TestCase):
    def test_seen_d1_cases_replay_exactly(self):
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertFalse(data["authority"]["holdout_replayed"])
        for case in data["cases"]:
            with self.subTest(case=case["case_id"]):
                result = analyze_workflow_patch(case["path"], case["patch"])
                self.assertEqual(case["expected_classification"], result["classification"])
                self.assertEqual(case["expected_reason_ids"], result["reason_ids"])
                self.assertEqual(case["expected_patch_sha256"], result["patch_sha256"])

    def test_unknown_is_conservative_for_non_test_workflow_change(self):
        patch = """@@ -10,3 +10,4 @@ jobs:
+      timeout-minutes: 30
"""
        result = analyze_workflow_patch(".github/workflows/ci.yml", patch)
        self.assertEqual("UNKNOWN", result["classification"])
        self.assertEqual(["WORKFLOW_SEMANTICS_UNKNOWN"], result["reason_ids"])

    def test_removed_write_permission_is_still_authority_mutation(self):
        patch = """@@ -10,4 +10,3 @@ permissions:
-  statuses: write
"""
        result = analyze_workflow_patch(".github/workflows/ci.yml", patch)
        self.assertEqual("AUTHORITY_MUTATION", result["classification"])
        self.assertEqual(["WORKFLOW_WRITE_PERMISSION"], result["reason_ids"])
        self.assertEqual("REMOVED", result["authority_signals"][0]["direction"])

    def test_secret_reference_is_authority_mutation(self):
        patch = """@@ -20,3 +20,4 @@ steps:
+        run: deploy --token '${{ secrets.PRODUCTION_TOKEN }}'
"""
        result = analyze_workflow_patch(".github/workflows/release.yml", patch)
        self.assertEqual("AUTHORITY_MUTATION", result["classification"])
        self.assertEqual(["WORKFLOW_SECRET_REFERENCE"], result["reason_ids"])

    def test_non_workflow_path_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not a GitHub Actions workflow path"):
            analyze_workflow_patch("scripts/verify-ci.mjs", "+console.log('ok')\n")


if __name__ == "__main__":
    unittest.main()
