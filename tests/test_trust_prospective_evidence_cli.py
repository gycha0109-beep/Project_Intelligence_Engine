from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout

from review_system.trust_cli import main as trust_main
from review_system.trust_prospective_evidence_cli import main as prospective_main
from test_trust_prospective_evidence import init_workspace


class ProspectiveEvidenceCliTests(unittest.TestCase):
    def test_standalone_progress_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = init_workspace(Path(temporary))
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = prospective_main([
                    "prospective-campaign-progress",
                    "--workspace", str(workspace),
                    "--generated-at", "2026-08-18T04:00:00Z",
                ])
            self.assertEqual(0, code)
            value = json.loads(stdout.getvalue())
            self.assertEqual("COLLECTING_EVIDENCE", value["status"])
            self.assertFalse(value["pilot_authorized"])

    def test_pie_trust_delegates_progress_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = init_workspace(Path(temporary))
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = trust_main([
                    "prospective-campaign-progress",
                    "--workspace", str(workspace),
                    "--generated-at", "2026-08-18T04:00:00Z",
                ])
            self.assertEqual(0, code)
            value = json.loads(stdout.getvalue())
            self.assertEqual("PROSPECTIVE_R0_EVIDENCE_CAMPAIGN_V1", value["campaign_contract"])


if __name__ == "__main__":
    unittest.main()
