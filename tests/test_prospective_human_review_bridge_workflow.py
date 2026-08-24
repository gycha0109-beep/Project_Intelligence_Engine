from __future__ import annotations

from pathlib import Path
import unittest


class HumanReviewBridgeWorkflowTests(unittest.TestCase):
    def test_workflow_preserves_manual_report_only_boundary(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "prospective-human-review-bridge.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("workflow_call:", workflow)
        self.assertNotIn("pull_request_target:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("pull-requests: read", workflow)
        self.assertIn('EVENT_REF"] != "refs/heads/main"', workflow)
        self.assertIn("run-github-pr-trusted", workflow)
        self.assertIn("evidence/trust/requests/", workflow)
        self.assertIn("READY_FOR_HUMAN_REVIEW", workflow)
        self.assertIn("human_review_recorded", workflow)
        self.assertIn("outcome_recorded", workflow)
        self.assertIn("production_effect_authorized", workflow)
        self.assertNotIn("submit-prospective-review", workflow)
        self.assertNotIn("record-prospective-outcome", workflow)
        self.assertNotIn("enable-auto-merge", workflow)
        self.assertNotIn("pull_request_review", workflow)
        self.assertNotIn("secrets:", workflow)


if __name__ == "__main__":
    unittest.main()
