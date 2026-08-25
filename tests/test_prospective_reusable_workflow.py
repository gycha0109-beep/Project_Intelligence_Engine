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
        self.assertIn('pie-trust-prospective "${args[@]}"', text)
        self.assertNotIn("--request", text)
        self.assertNotIn("--workspace", text)
        self.assertNotIn("--operational-trust-facts", text)
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

    def test_optional_operational_policy_is_fail_closed_and_report_only(self):
        text = self.text
        self.assertIn("operational_policy:", text)
        self.assertIn('default: ""', text)
        self.assertIn("INPUT_OPERATIONAL_POLICY: ${{ inputs.operational_policy }}", text)
        self.assertIn('if operational_policy:', text)
        self.assertIn("policy_path.is_absolute()", text)
        self.assertIn('".." in policy_path.parts', text)
        self.assertIn('if [[ -n "${INPUT_OPERATIONAL_POLICY}" ]]; then', text)
        self.assertIn('args+=(--operational-policy "${INPUT_OPERATIONAL_POLICY}")', text)
        self.assertNotIn("operational_trust_facts:", text)
        self.assertNotIn("--operational-trust-facts", text)

    def test_transport_and_raw_observation_are_separate_from_replay_authority(self):
        text = self.text
        self.assertIn('shutil.copytree(bundle, staging / "bundle")', text)
        self.assertIn('staging / "workflow-context.json"', text)
        self.assertIn("deterministic_result_sha256", text)
        self.assertIn("raw_observation_manifest_sha256", text)
        self.assertIn("Run-specific transport metadata and raw provider observation hashes are separate", text)
        self.assertIn("actions/upload-artifact@v4", text)

    def test_missing_replay_hash_is_integrity_failure(self):
        text = self.text
        self.assertIn('result.get("deterministic_replay_bound") is not True', text)
        self.assertIn("NON_DETERMINISTIC_REPLAY: AUTO-1B requires a deterministic replay-bound result", text)
        self.assertIn("NON_DETERMINISTIC_REPLAY: deterministic_result_sha256 is missing or invalid", text)
        self.assertIn("deterministic-result.json", text)

    def test_risk_result_is_not_a_failure_gate(self):
        text = self.text
        self.assertIn('risk = result.get("risk_band") or "NOT_ASSESSED"', text)
        self.assertIn('operational_binding = result.get("operational_binding_status") or "NOT_ENABLED"', text)
        self.assertIn('f"- Status: `{result[\'status\']}`', text)
        self.assertIn("Human review: `NOT RECORDED`", text)
        self.assertIn("Merge / deploy / production effect authority: `NOT GRANTED`", text)


if __name__ == "__main__":
    unittest.main()
