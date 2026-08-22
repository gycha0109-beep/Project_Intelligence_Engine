from __future__ import annotations

import json
from pathlib import Path
import unittest

from review_system.trust_execution_isolation_boundary import assess_isolation_boundary


EVIDENCE_PATH = (
    Path(__file__).resolve().parents[1]
    / "evidence"
    / "trust"
    / "peb3r-b-isolation-boundary-20260822.json"
)


class TrustExecutionIsolationBoundaryEvidenceTests(unittest.TestCase):
    def test_frozen_current_evidence_replays_expected_blockers(self) -> None:
        evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
        expected = evidence.pop("expected_assessment")
        evidence.pop("observed_connector_capability", None)
        evidence.pop("generated_at", None)
        evidence.pop("source_main_sha", None)

        assessment = assess_isolation_boundary(evidence)

        self.assertEqual(assessment["status"], expected["status"])
        self.assertEqual(assessment["blockers"], expected["blockers"])
        self.assertEqual(assessment["next_step"], expected["next_step"])
        self.assertEqual(
            assessment["formal_dispatch_permitted"],
            expected["formal_dispatch_permitted"],
        )
        self.assertFalse(assessment["production_execution_authorized"])
        self.assertFalse(assessment["automation_authorized"])
        self.assertFalse(assessment["pilot_authorized"])


if __name__ == "__main__":
    unittest.main()
