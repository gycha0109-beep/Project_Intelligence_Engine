from __future__ import annotations

from pathlib import Path
import unittest

import yaml


WORKFLOW = Path(".github/workflows/operational-outcome-context.yml")


class OperationalOutcomeContextWorkflowTests(unittest.TestCase):
    def test_dispatch_has_no_outcome_semantic_inputs(self):
        data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        trigger = data.get("on") or data.get(True)
        dispatch = trigger["workflow_dispatch"]
        self.assertEqual(
            {"target_repository", "pull_request_number"},
            set(dispatch["inputs"]),
        )

    def test_permissions_are_read_only(self):
        data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        self.assertEqual(
            {
                "actions": "read",
                "checks": "read",
                "contents": "read",
                "pull-requests": "read",
            },
            data["permissions"],
        )
        text = WORKFLOW.read_text(encoding="utf-8")
        for token in (
            "contents: write",
            "pull-requests: write",
            "checks: write",
            "gh pr merge",
            "gh pr review",
            "git push",
            "record-declared-prospective-outcome",
            "prepare-outcome-declaration",
        ):
            self.assertNotIn(token, text)

    def test_workflow_checks_non_authority_ceiling(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("prepare-operational-outcome-context", text)
        self.assertIn("human_outcome_declared", text)
        self.assertIn("automatic_outcome_inference", text)
        self.assertIn("merge_observation_is_outcome_authority", text)
        self.assertIn("ci_observation_is_outcome_authority", text)
        self.assertIn("selected_authority_type", text)
        self.assertIn("selected_verdict", text)
        self.assertIn("AUTO-3 authority/verdict selection: `NOT PERFORMED`", text)
        self.assertIn("Merge / CI observations are Outcome authority: `NO`", text)

    def test_artifact_preserves_context_and_review_action_source(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('shutil.copyfile(context_file, staging / "context.json")', text)
        self.assertIn('shutil.copytree(selected, staging / "review-action-source")', text)
        self.assertIn("pie-orl5-${safe_repo}-pr-", text)


if __name__ == "__main__":
    unittest.main()
