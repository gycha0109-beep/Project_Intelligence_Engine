from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "prospective-pr.yml"


class CalibrationPolicyMatchExplanationWorkflowTests(unittest.TestCase):
    def test_prospective_workflow_materializes_optional_policy_match_sidecar(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "python -m review_system.calibration_policy_match_materialize",
            text,
        )
        self.assertIn('--result "${result_file}"', text)
        self.assertIn('--calibration-root "${RUNNER_TEMP}/pie-calibration"', text)
        self.assertIn('--workspace "${GITHUB_WORKSPACE}"', text)
        self.assertIn("Upload aggregate-ready calibration observation", text)

    def test_existing_reusable_workflow_permissions_do_not_widen(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        permissions_block = text.split("permissions:", 1)[1].split("concurrency:", 1)[0]
        self.assertIn("contents: read", permissions_block)
        self.assertIn("pull-requests: read", permissions_block)
        self.assertNotIn("write", permissions_block)
        self.assertNotIn("actions:", permissions_block)


if __name__ == "__main__":
    unittest.main()
