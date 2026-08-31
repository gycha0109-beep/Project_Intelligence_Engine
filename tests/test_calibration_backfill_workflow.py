from __future__ import annotations

from pathlib import Path
import unittest


class CalibrationBackfillWorkflowTests(unittest.TestCase):
    def test_reusable_workflow_keeps_historical_downloads_caller_local_and_read_only(self):
        workflow = (
            Path(__file__).resolve().parents[1] / ".github" / "workflows" / "calibration-backfill.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("workflow_call:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("actions: read", workflow)
        self.assertIn('REPOSITORY: ${{ inputs.repository }}', workflow)
        self.assertIn('CALLER_REPOSITORY: ${{ github.repository }}', workflow)
        self.assertIn('[[ "$REPOSITORY" == "$CALLER_REPOSITORY" ]]', workflow)
        self.assertIn('--repository "$REPOSITORY"', workflow)
        self.assertIn('GITHUB_TOKEN: ${{ github.token }}', workflow)
        self.assertNotIn("pull_request:", workflow)
        for repository in (
            "gycha0109-beep/BuildMap",
            "gycha0109-beep/K_beauty",
            "gycha0109-beep/Saju",
            "gycha0109-beep/AnnoyingRadar",
            "gycha0109-beep/ranking",
            "gycha0109-beep/thought-drawer",
            "gycha0109-beep/journey-connect-backend",
        ):
            self.assertNotIn(repository, workflow)


if __name__ == "__main__":
    unittest.main()
