from pathlib import Path
import unittest


class HistoricalTrustGapWorkflowTests(unittest.TestCase):
    def test_workflow_is_caller_local_and_read_only(self):
        text = Path('.github/workflows/calibration-trust-gap.yml').read_text(encoding='utf-8')
        self.assertIn('contents: read', text)
        self.assertIn('actions: read', text)
        self.assertIn('CALLER_REPOSITORY: ${{ github.repository }}', text)
        self.assertIn('GITHUB_TOKEN: ${{ github.token }}', text)
        self.assertIn('[[ "$REPOSITORY" == "$CALLER_REPOSITORY" ]]', text)
        self.assertNotIn('contents: write', text)
        self.assertNotIn('pull-requests: write', text)
        self.assertNotIn('secrets: inherit', text)

    def test_command_is_exposed(self):
        text = Path('pyproject.toml').read_text(encoding='utf-8')
        self.assertIn('pie-calibration-trust-gap = "review_system.calibration_trust_gap_cli:main"', text)


if __name__ == '__main__':
    unittest.main()
