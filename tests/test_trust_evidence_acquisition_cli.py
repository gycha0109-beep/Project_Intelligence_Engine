from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from review_system.trust_cli import main as trust_main
from review_system.trust_evidence_acquisition_cli import main


class EvidenceAcquisitionCliTests(unittest.TestCase):
    def test_standalone_inspect_missing_workspace_inputs_is_valid_blocked_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "report.json"
            stream = io.StringIO()
            with redirect_stdout(stream):
                code = main([
                    "inspect-r0-evidence-acquisition",
                    "--workspace", str(root),
                    "--output", str(output),
                    "--generated-at", "2026-08-18T05:00:00Z",
                ])
            payload = json.loads(stream.getvalue())
            self.assertEqual(code, 0)
            self.assertTrue(payload["valid"])
            self.assertEqual(payload["status"], "BLOCKED_MISSING_INPUT")
            self.assertFalse(payload["package_published"])
            self.assertTrue(output.is_file())

    def test_delegated_pie_trust_command_is_registered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "report.json"
            stream = io.StringIO()
            with redirect_stdout(stream):
                code = trust_main([
                    "inspect-r0-evidence-acquisition",
                    "--workspace", str(root),
                    "--output", str(output),
                    "--generated-at", "2026-08-18T05:00:00Z",
                ])
            payload = json.loads(stream.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(payload["status"], "BLOCKED_MISSING_INPUT")


if __name__ == "__main__":
    unittest.main()
