from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from review_system.trust_cli import main as trust_main
from review_system.trust_pilot_evidence_run import EXPECTED_FILES, run_r0_pilot_evidence, write_pilot_evidence_run_report
from review_system.trust_pilot_evidence_run_cli import main


class PilotEvidenceRunCliTests(unittest.TestCase):
    def _complete_package(self, root: Path) -> None:
        for index, (_, filename) in enumerate(EXPECTED_FILES, start=1):
            (root / filename).write_text(f"evidence-{index}\n", encoding="utf-8")

    def _eligible_pilot_report(self) -> dict:
        return {
            "review_id": "r0-pilot-safety-review-" + "1" * 32,
            "project_id": "demo",
            "report_sha256": "a" * 64,
            "status": "ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW",
            "next_step": "REQUEST_EXPLICIT_HUMAN_PILOT_AUTHORIZATION",
            "blockers": [],
            "source_replay": {
                "reconciliation_verified": True,
                "observation_verified": True,
            },
        }

    def test_missing_evidence_is_valid_not_eligible_exit_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "report.json"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main([
                    "run-r0-pilot-evidence",
                    "--evidence-root", str(root / "missing"),
                    "--output", str(output),
                    "--generated-at", "2026-08-18T05:00:00Z",
                ])
            self.assertEqual(0, code)
            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["valid"])
            self.assertEqual("NOT_ELIGIBLE", payload["status"])
            self.assertFalse(payload["pilot_authorized"])
            self.assertTrue(output.is_file())

    def test_pie_trust_delegates_stage10g_command(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = trust_main([
                    "run-r0-pilot-evidence",
                    "--evidence-root", str(root / "missing"),
                    "--output", str(root / "report.json"),
                    "--generated-at", "2026-08-18T05:00:00Z",
                ])
            self.assertEqual(0, code)
            self.assertEqual("NOT_ELIGIBLE", json.loads(stdout.getvalue())["status"])

    def test_eligible_report_verification_requires_exact_evidence_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "r0-pilot-evidence"
            evidence.mkdir()
            self._complete_package(evidence)
            with patch(
                "review_system.trust_pilot_evidence_run.review_r0_pilot",
                return_value=self._eligible_pilot_report(),
            ):
                report = run_r0_pilot_evidence(evidence, generated_at="2026-08-18T05:00:00Z")
            path = root / "eligible.json"
            write_pilot_evidence_run_report(path, report)
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = main(["verify-r0-pilot-evidence-run", "--report", str(path)])
            self.assertEqual(3, code)
            self.assertIn("requires --evidence-root", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
