from __future__ import annotations

from pathlib import Path
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "prospective-pr.yml"


class ProspectiveReusableWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_is_workflow_call_only_and_read_only(self):
        text = self.text
        self.assertIn("workflow_call:", text)
        self.assertNotIn("pull_request_target", text)
        self.assertNotIn("secrets:", text)
        self.assertIn("contents: read", text)
        self.assertIn("pull-requests: read", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("pull-requests: write", text)

    def test_exact_workflow_and_pr_head_binding_is_explicit(self):
        text = self.text
        self.assertIn("WORKFLOW_SHA: ${{ job.workflow_sha }}", text)
        self.assertIn("WORKFLOW_REPOSITORY: ${{ job.workflow_repository }}", text)
        self.assertIn("pie_revision != workflow_sha", text)
        self.assertIn("event_head != caller_head", text)
        self.assertIn("refs/pull/${{ inputs.pull_request_number }}/head", text)
        self.assertIn('actual_head="$(git rev-parse HEAD)"', text)
        self.assertIn("persist-credentials: false", text)

    def test_workflow_runs_only_read_only_orchestration_path(self):
        text = self.text
        self.assertIn("pie-trust-prospective run-github-pr", text)
        self.assertNotIn("--request", text)
        self.assertNotIn("--workspace", text)
        for forbidden in (
            "pull_request_review",
            "record-prospective-outcome",
            "submit-prospective-review",
            "merge_pull_request",
            "gh pr merge",
            "git push",
            "npm install",
            "pnpm install",
            "pytest",
            "./gradlew",
            "mvn test",
        ):
            self.assertNotIn(forbidden, text)

    def test_transport_metadata_does_not_mutate_canonical_bundle(self):
        text = self.text
        self.assertIn('shutil.copytree(bundle, staging / "bundle")', text)
        self.assertIn('staging / "workflow-context.json"', text)
        self.assertIn("Transport metadata is outside the canonical evidence manifest", text)
        self.assertIn("actions/upload-artifact@v4", text)

    def test_risk_result_is_not_a_failure_gate(self):
        text = self.text
        self.assertIn('risk = result.get("risk_band") or "NOT_ASSESSED"', text)
        self.assertIn('f"- Status: `{result[\'status\']}`', text)
        self.assertIn("Human review: `NOT RECORDED`", text)
        self.assertIn("Merge / deploy / production effect authority: `NOT GRANTED`", text)


if __name__ == "__main__":
    unittest.main()
