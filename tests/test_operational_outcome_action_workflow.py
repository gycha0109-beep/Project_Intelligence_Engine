from __future__ import annotations

from pathlib import Path
import unittest

import yaml


WORKFLOW = Path(".github/workflows/operational-outcome-action.yml")


class OperationalOutcomeActionWorkflowTests(unittest.TestCase):
    def test_dispatch_requires_explicit_outcome_semantics_and_source_locator(self):
        data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        trigger = data.get("on") or data.get(True)
        dispatch = trigger["workflow_dispatch"]
        inputs = dispatch["inputs"]
        self.assertEqual(
            {
                "target_repository",
                "pull_request_number",
                "authority_type",
                "verdict",
                "source_run_id",
                "source_artifact_name",
                "primary_source_path",
                "secondary_source_path",
                "defect_id",
                "evidence_refs",
            },
            set(inputs),
        )
        self.assertEqual(
            ["PRODUCTION_DEFECT", "CONTROLLED_EVALUATION", "INDEPENDENT_AUDIT"],
            inputs["authority_type"]["options"],
        )
        self.assertEqual(
            ["SAFE", "UNSAFE", "INCONCLUSIVE"],
            inputs["verdict"]["options"],
        )
        self.assertNotIn("actor", inputs)
        self.assertNotIn("assessment_id", inputs)
        self.assertNotIn("review_packet_sha256", inputs)
        self.assertNotIn("evaluation_report_sha256", inputs)

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
            "actions: write",
            "contents: write",
            "pull-requests: write",
            "checks: write",
            "gh pr merge",
            "gh pr review",
            "git push",
            "deployment",
        ):
            self.assertNotIn(token, text)

    def test_actor_is_bound_to_github_actor(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("OUTCOME_ACTOR: ${{ github.actor }}", text)
        self.assertIn('--actor "${OUTCOME_ACTOR}"', text)

    def test_source_must_come_from_exact_authority_artifact(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('gh run download "${INPUT_SOURCE_RUN_ID}"', text)
        self.assertIn('--repo "${AUTHORITY_REPOSITORY}"', text)
        self.assertIn('--name "${INPUT_SOURCE_ARTIFACT_NAME}"', text)
        self.assertIn('relative.is_absolute() or ".." in relative.parts', text)
        self.assertIn("current.is_symlink()", text)
        self.assertIn("resolved.relative_to(root)", text)

    def test_authority_specific_files_are_mapped_without_hash_inputs(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('--defect-registry "${PRIMARY_SOURCE}" --ledger "${SECONDARY_SOURCE}"', text)
        self.assertIn('--evaluation-report "${PRIMARY_SOURCE}"', text)
        self.assertIn('--audit-artifact "${PRIMARY_SOURCE}" --audit-authority-registry "${SECONDARY_SOURCE}"', text)
        self.assertNotIn("--evaluation-report-sha256", text)
        self.assertNotIn("--audit-artifact-sha256", text)
        self.assertNotIn("--defect-registry-sha256", text)

    def test_workflow_invokes_existing_auto3_adapter_and_checks_authority_ceiling(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("submit-operational-outcome", text)
        self.assertIn('result.get("status") != "EXPLICIT_OUTCOME_RECORDED"', text)
        self.assertIn('(\"human_outcome_declared\", True)', text)
        self.assertIn('(\"outcome_recorded\", True)', text)
        self.assertIn('(\"automatic_outcome_inference\", False)', text)
        self.assertIn('(\"merge_authorized\", False)', text)
        self.assertIn('(\"deploy_authorized\", False)', text)
        self.assertIn('(\"production_effect_authorized\", False)', text)
        self.assertIn('auto3.get("reconciliation_status") != "RECONCILED"', text)
        self.assertIn('auto3.get("idempotent") is not False', text)

    def test_output_is_preserved_as_orl6_artifact(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('f"pie-orl6-{safe_repo}-pr-', text)
        self.assertIn("actions/upload-artifact@v4", text)
        self.assertIn("path: ${{ steps.outcome.outputs.upload_path }}", text)
        self.assertIn("Automatic Outcome inference: `NO`", text)
        self.assertIn("Merge / deploy / production-effect authority: `NOT GRANTED`", text)


if __name__ == "__main__":
    unittest.main()
