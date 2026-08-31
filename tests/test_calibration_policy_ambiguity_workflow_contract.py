from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "calibration-policy-ambiguity.yml"


class HistoricalPolicyAmbiguityWorkflowContractTests(unittest.TestCase):
    def test_reusable_workflow_is_caller_local_and_read_only(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_call:", text)
        self.assertIn("contents: read", text)
        self.assertIn("actions: read", text)
        self.assertIn('[[ "$REPOSITORY" == "$CALLER_REPOSITORY" ]]', text)
        self.assertIn("github.token", text)
        self.assertNotIn("pull-requests: write", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("secrets:", text)

    def test_exact_revision_and_no_policy_resolution_action(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("DIAGNOSTIC_REVISION", text)
        self.assertIn("git+https://github.com/gycha0109-beep/Project_Intelligence_Engine.git@${DIAGNOSTIC_REVISION}", text)
        self.assertIn("pie-calibration-policy-ambiguity", text)
        self.assertNotIn("merge", text.lower())
        self.assertNotIn("approve", text.lower())
        self.assertNotIn("resolve-policy", text.lower())


if __name__ == "__main__":
    unittest.main()
