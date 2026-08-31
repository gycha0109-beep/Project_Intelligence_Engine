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
            "pie_signal_match_status",
            "pie_signal_next",
            "pie_level1_materialized",
            "pie_level2_item_count",
            "interface_artifact_name",
        ):
            self.assertIn(f"      {output}:", text)
        self.assertIn("`PIE_SIGNAL_V1`", text)
        self.assertIn("# PIE Signal", text)

    def test_progressive_disclosure_uses_separate_compact_full_and_calibration_artifacts(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Upload compact GPT operational interface", text)
        self.assertIn("Upload replayable evidence capsule", text)
        self.assertIn("Upload aggregate-ready calibration observation", text)
        self.assertIn('interface_artifact_name = f"{artifact_name}-interface"', text)
        self.assertIn('"interface_upload_path": str(interface_staging)', text)
        self.assertIn('"upload_path": str(staging)', text)
        self.assertIn('"calibration_upload_path": str(calibration_staging)', text)
        self.assertIn('"calibration_artifact_name": calibration_name', text)

    def test_calibration_observation_is_exposed_without_new_authority(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        for output in (
            "calibration_key_sha256",
            "calibration_record_sha256",
            "calibration_artifact_name",
        ):
            self.assertIn(f"      {output}:", text)
        self.assertIn("build_calibration_record", text)
        self.assertIn("calibration_artifact_name(calibration_record)", text)
        self.assertIn("PIE_CALIBRATION_RECORD_V1", text)
        self.assertIn('"pie_signal_match_status": signal.get("match_status") or "NONE"', text)
        self.assertIn('"pie_level1_materialized": "true" if lazy_interface["level1_materialized"] else "false"', text)
        self.assertIn('"pie_level2_item_count": str(lazy_interface["level2_item_count"])', text)

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
