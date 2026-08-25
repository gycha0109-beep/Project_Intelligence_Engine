from __future__ import annotations

from pathlib import Path
import unittest

import yaml

from review_system.trust_prospective_evidence_cli import build_parser


WORKFLOW = Path(".github/workflows/operational-review-action.yml")


class OperationalReviewActionWorkflowTests(unittest.TestCase):
    def test_workflow_dispatch_exposes_only_human_review_inputs(self):
        data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        trigger = data.get("on") or data.get(True)
        self.assertIsInstance(trigger, dict)
        dispatch = trigger["workflow_dispatch"]
        inputs = dispatch["inputs"]
        self.assertEqual(
            {
                "target_repository",
                "pull_request_number",
                "decision",
                "reason",
                "confirmed_risk_band",
            },
            set(inputs),
        )
        self.assertEqual(
            ["APPROVE", "REQUEST_CHANGES", "HOLD", "REJECT", "RECLASSIFY"],
            inputs["decision"]["options"],
        )
        self.assertEqual("NONE", inputs["confirmed_risk_band"]["default"])
        self.assertEqual(
            ["NONE", "R0", "R1", "R2", "R3", "R4"],
            inputs["confirmed_risk_band"]["options"],
        )

    def test_workflow_permissions_are_read_only(self):
        data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        self.assertEqual(
            {"actions": "read", "contents": "read", "pull-requests": "read"},
            data["permissions"],
        )
        text = WORKFLOW.read_text(encoding="utf-8")
        forbidden = (
            "pull-requests: write",
            "contents: write",
            "actions: write",
            "gh pr merge",
            "gh pr review",
            "git push",
            "merge_pull_request",
        )
        for token in forbidden:
            self.assertNotIn(token, text)

    def test_workflow_binds_actor_and_explicit_action_command(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pie-trust-prospective \"${args[@]}\"", text)
        self.assertIn("submit-operational-review", text)
        self.assertIn("REVIEW_ACTOR: ${{ github.actor }}", text)
        self.assertIn("--actor \"${REVIEW_ACTOR}\"", text)
        self.assertIn("HUMAN_REVIEW_RECORDED", text)
        self.assertIn("human_review_recorded", text)
        self.assertIn("outcome_recorded", text)
        self.assertIn("merge_authorized", text)
        self.assertIn("deploy_authorized", text)
        self.assertIn("production_effect_authorized", text)

    def test_workflow_rechecks_live_head_and_uploads_orl4_evidence(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("refs/pull/${{ inputs.pull_request_number }}/head", text)
        self.assertIn('actual_head="$(git rev-parse HEAD)"', text)
        self.assertIn("pie-orl4-{safe_repo}-pr-", text)
        self.assertIn("shutil.copyfile(action_file, staging / \"action.json\")", text)
        self.assertIn("shutil.copytree(bridge_root, staging / \"bridge\")", text)
        self.assertIn("Human review: `RECORDED`", text)
        self.assertIn("Outcome: `NOT RECORDED`", text)
        self.assertIn("Merge / deploy / production-effect authority: `NOT GRANTED`", text)

    def test_cli_surface_does_not_require_packet_or_assessment_hashes(self):
        parser = build_parser()
        args = parser.parse_args([
            "submit-operational-review",
            "--target-repository", "demo/repo",
            "--pull-request", "7",
            "--repository-root", ".",
            "--artifact-cache-root", ".pie/cache",
            "--decision", "APPROVE",
            "--reason", "reviewed",
            "--actor", "alice",
            "--output", ".pie/action.json",
        ])
        self.assertEqual("submit-operational-review", args.command)
        self.assertFalse(hasattr(args, "packet"))
        self.assertFalse(hasattr(args, "assessment_id"))
        self.assertFalse(hasattr(args, "review_level"))
        self.assertEqual("APPROVE", args.decision)


if __name__ == "__main__":
    unittest.main()
