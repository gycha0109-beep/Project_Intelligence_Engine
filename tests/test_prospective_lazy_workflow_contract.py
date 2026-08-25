from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "prospective-pr.yml"


class ProspectiveLazyWorkflowContractTests(unittest.TestCase):
    def test_level_zero_is_exposed_as_reusable_workflow_outputs(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        for output in (
            "pie_signal_status",
            "pie_signal_reason",
            "pie_signal_next",
            "interface_artifact_name",
        ):
            self.assertIn(f"      {output}:", text)
        self.assertIn("`PIE_SIGNAL_V1`", text)
        self.assertIn("# PIE Signal", text)

    def test_progressive_disclosure_uses_separate_compact_and_full_artifacts(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Upload compact GPT operational interface", text)
        self.assertIn("Upload replayable evidence capsule", text)
        self.assertIn('interface_artifact_name = f"{artifact_name}-interface"', text)
        self.assertIn('"interface_upload_path": str(interface_staging)', text)
        self.assertIn('"upload_path": str(staging)', text)

    def test_permissions_remain_read_only_and_no_comment_authority_is_added(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read\n  pull-requests: read\n", text)
        self.assertNotIn("pull-requests: write", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("checks: write", text)
        self.assertNotIn("statuses: write", text)
        self.assertNotIn("pull_request_target", text)
        self.assertIn("persist-credentials: false", text)

    def test_operational_signal_does_not_turn_action_required_into_workflow_failure(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('"pie_signal_status": signal["status"]', text)
        self.assertIn('"pie_signal_reason": signal["reason"]', text)
        self.assertIn('"pie_signal_next": signal["next"]', text)
        self.assertNotIn('signal["status"] == "ACTION_REQUIRED"', text)
        self.assertNotIn('signal["status"] != "CLEAR"', text)
        self.assertNotIn("operational_trust_facts:", text)


if __name__ == "__main__":
    unittest.main()
