from pathlib import Path
import unittest

from review_system.calibration_trust_gap_zero_cli import _empty_diagnostic
from review_system.identity import canonical_json_sha256


class HistoricalTrustGapWorkflowTests(unittest.TestCase):
    def test_workflow_is_caller_local_and_read_only(self):
        text = Path('.github/workflows/calibration-trust-gap.yml').read_text(encoding='utf-8')
        self.assertIn('contents: read', text)
        self.assertIn('actions: read', text)
        self.assertIn('CALLER_REPOSITORY: ${{ github.repository }}', text)
        self.assertIn('GITHUB_TOKEN: ${{ github.token }}', text)
        self.assertIn('[[ "$REPOSITORY" == "$CALLER_REPOSITORY" ]]', text)
        self.assertIn('python -m review_system.calibration_trust_gap_zero_cli', text)
        self.assertNotIn('contents: write', text)
        self.assertNotIn('pull-requests: write', text)
        self.assertNotIn('secrets: inherit', text)

    def test_command_is_exposed(self):
        text = Path('pyproject.toml').read_text(encoding='utf-8')
        self.assertIn('pie-calibration-trust-gap = "review_system.calibration_trust_gap_cli:main"', text)

    def test_zero_target_is_valid_empty_diagnostic(self):
        diagnostic = _empty_diagnostic()
        self.assertEqual(0, diagnostic['input_observation_count'])
        self.assertEqual(0, diagnostic['unique_calibration_count'])
        self.assertEqual(0, diagnostic['duplicate_observation_count'])
        self.assertEqual({}, diagnostic['histograms']['missing_field'])
        self.assertEqual(0, diagnostic['targeted']['missing_item_total'])
        self.assertTrue(diagnostic['authority']['calibration_only'])
        self.assertFalse(diagnostic['authority']['trust_fact_inferred'])
        body = dict(diagnostic)
        recorded = body.pop('diagnostic_sha256')
        self.assertEqual(recorded, canonical_json_sha256(body))


if __name__ == '__main__':
    unittest.main()
